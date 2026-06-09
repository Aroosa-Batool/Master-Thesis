"""Re-Consent policy demo.

Same sensing pipeline as ``demo_cache_memory.py``, but every elevated-HR
encounter with a bystander triggers a fresh watch prompt - the user's
previous answer is never reused. This is the thesis brief's "Re-Consent"
baseline: the difference from the Cache-Memory script is literally just
the absence of the cache lookup.

Bystander ID is still auto-detected from the camera frame (YuNet+SFace,
same face gallery as the Cache-Memory demo) for logging parity, but
it has no effect on the decision - this policy always asks.

Run:
    python interface/presence/demo_reconsent.py
Press 'q' in the camera window to quit.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import traceback
from collections import deque
from pathlib import Path

import cv2

try:
    from ohbot import ohbot
except ModuleNotFoundError as exc:
    raise SystemExit("Missing dependency: install with `pip install ohbot`.") from exc

from face_db import FaceDB
from face_id import (
    FaceIdentifier,
    SFACE_COSINE_SAME_PERSON,
    SFACE_OWNER_THRESHOLD,
    ensure_models,
)
from owner import OwnerStore
from policy import BangleClient


OHBOT_PORT_HINT = os.environ.get("OHBOT_PORT", "Pico")
# Set NO_OHBOT=1 to skip Ohbot init/use entirely. Useful when the robot
# isn't plugged in - the consent flow on the watch still runs and the
# disclose/withhold decisions are printed instead of spoken.
NO_OHBOT = os.environ.get("NO_OHBOT") == "1"

if sys.platform == "darwin":
    _silence_wav = os.path.join(os.path.dirname(ohbot.__file__), "Silence1.wav")

    def _say_speech_macos(addSilence):
        try:
            if addSilence:
                subprocess.run(
                    ["afplay", _silence_wav], timeout=5, check=False
                )
            subprocess.run(
                ["afplay", "ohbotspeech.wav"], timeout=30, check=False
            )
        except subprocess.TimeoutExpired:
            print("[ohbot] afplay timed out; continuing.")
        except FileNotFoundError:
            print("[ohbot] afplay not found; skipping audio.")

    ohbot.saySpeech = _say_speech_macos


# Shared state for thread-safe Ohbot access and shutdown coordination.
# See demo_cache_memory.py for the rationale.
shutting_down = threading.Event()
ohbot_lock = threading.Lock()


def _speak_fallback(text: str) -> None:
    """OS-native TTS fallback when NO_OHBOT=1. See demo_cache_memory.py."""

    if not text:
        return
    cmd: list[str] | None = None
    if sys.platform == "darwin":
        cmd = ["say", text]
    elif sys.platform.startswith("linux"):
        cmd = ["espeak", text]
    if cmd is None:
        print(f"[tts] no TTS available on {sys.platform}; would say: {text!r}")
        return
    try:
        subprocess.run(cmd, timeout=30, check=False)
    except FileNotFoundError:
        print(f"[tts] {cmd[0]} not found; would say: {text!r}")
    except subprocess.TimeoutExpired:
        print("[tts] TTS timed out.")


DISCLOSE_TEMPLATE = (
    "I noticed your heart rate has been a bit elevated, around {bpm}. "
    "Would you like to take a few deep breaths together?"
)
WITHHOLD_LINE = "Hello there."


OBSERVATION_WINDOW_S = 15.0
# Same semantics as demo_cache_memory.py:
#   >= FACE_VISIBLE_FRACTION_HIGH -> verdict "FACE_IN_VIEW"
#   <= FACE_VISIBLE_FRACTION_LOW  -> verdict "NO_FACES"
# Owner presence is BLE-driven; the camera detects bystander candidates.
FACE_VISIBLE_FRACTION_HIGH = 0.7
FACE_VISIBLE_FRACTION_LOW = 0.3
ELEVATED_BPM = 100
MIN_ELEVATED_DWELL_S = 5.0
HR_STALE_S = 10.0
CONSENT_TIMEOUT_S = 30.0

PROMPT_MESSAGE = (
    "I have noticed that someone is present with you. "
    "Do you want me to send private reminders in front of them?"
)

# Shared with demo_cache_memory.py - the face identity gallery is global,
# not policy-specific. A person recognised in one demo is the same person
# in the other.
FACE_DB_PATH = Path(__file__).resolve().parent / "face_db.json"
OWNER_FACE_PATH = Path(__file__).resolve().parent / "owner_face.json"


def behavior_disclose(bpm: int) -> None:
    msg = DISCLOSE_TEMPLATE.format(bpm=bpm)
    print(f">>> disclose ({bpm} bpm) -> {msg!r}")
    if NO_OHBOT:
        print("[ohbot] NO_OHBOT=1; speaking via OS TTS instead.")
        _speak_fallback(msg)
        return
    with ohbot_lock:
        if shutting_down.is_set():
            return
        try:
            ohbot.move(ohbot.HEADTURN, 5)
            ohbot.move(ohbot.HEADNOD, 5)
            ohbot.say(msg, untilDone=True, lipSync=True)
        except Exception as exc:
            print(f"[ohbot] disclose failed: {exc}")


def behavior_withhold() -> None:
    print(f">>> withhold -> {WITHHOLD_LINE!r}")
    if NO_OHBOT:
        print("[ohbot] NO_OHBOT=1; speaking via OS TTS instead.")
        _speak_fallback(WITHHOLD_LINE)
        return
    with ohbot_lock:
        if shutting_down.is_set():
            return
        try:
            ohbot.move(ohbot.HEADTURN, 5)
            ohbot.say(WITHHOLD_LINE, untilDone=True, lipSync=True)
        except Exception as exc:
            print(f"[ohbot] withhold failed: {exc}")


def identify_people_in_frame(
    face_identifier: FaceIdentifier,
    face_db: FaceDB,
    owner_store: OwnerStore,
    frame_bgr,
) -> tuple[str, list[tuple[str, float, bool, bool]], bool]:
    """Return (bystander_id, per_face_info, owner_detected).

    Same semantics as ``demo_cache_memory.py``'s helper. See that
    module's docstring for why "owner not detected" is no longer an
    abort: BLE establishes owner presence in the room, so the camera
    is free to see only the bystander.
    """

    faces = face_identifier.detect_and_embed(frame_bgr)
    faces.sort(key=lambda f: f.area, reverse=True)
    if not faces:
        return "", [], False

    owner_scores = [
        owner_store.matches(face.embedding, threshold=SFACE_OWNER_THRESHOLD)
        for face in faces
    ]
    owner_idx = -1
    best_sim = SFACE_OWNER_THRESHOLD
    for i, (is_owner, sim) in enumerate(owner_scores):
        if is_owner and sim >= best_sim:
            best_sim = sim
            owner_idx = i

    per_face: list[tuple[str, float, bool, bool]] = []
    bystanders: list[str] = []
    for i, face in enumerate(faces):
        if i == owner_idx:
            per_face.append(("owner", owner_scores[i][1], False, True))
            continue
        pid, sim, is_new = face_db.identify(face.embedding)
        per_face.append((pid, sim, is_new, False))
        bystanders.append(pid)

    return ":".join(sorted(set(bystanders))), per_face, owner_idx >= 0


def run_policy(
    watch: BangleClient,
    face_identifier: FaceIdentifier,
    face_db: FaceDB,
    owner_store: OwnerStore,
    bpm: int,
    frame_bgr,
) -> str:
    bystander_id, per_face, owner_detected = identify_people_in_frame(
        face_identifier, face_db, owner_store, frame_bgr
    )
    if not per_face:
        print("[policy] trial aborted (no faces detected by YuNet).")
        return "aborted (no faces)"
    if owner_store.has_owner() and not owner_detected:
        # Owner is in the room (BLE-connected) but not in the camera.
        # Every face we see is a bystander.
        sims = ", ".join(f"sim={sim:.2f}" for _, sim, _, _ in per_face)
        print(
            f"[policy] owner not in camera frame "
            f"(BLE confirms in-room). Treating all faces as bystanders. "
            f"owner-sim per face = [{sims}]."
        )
    if not bystander_id:
        print("[policy] trial aborted (only owner detected; no bystanders).")
        return "aborted (only owner)"

    def _fmt(entry):
        pid, sim, is_new, is_owner = entry
        tag = "[OWNER] " if is_owner else ("*" if is_new else "")
        return f"{tag}{pid} (sim={sim:.2f})"

    pretty = ", ".join(_fmt(e) for e in per_face)
    print(f"[policy] people in frame: {pretty}  -> log key '{bystander_id}'")

    print("[policy] asking the watch (re-consent always re-asks).")
    answer = watch.ask_consent(PROMPT_MESSAGE, timeout=CONSENT_TIMEOUT_S)
    if answer is None:
        print("[policy] no answer from watch; withholding (safe default).")
        behavior_withhold()
        return f"no-reply -> withhold ({bystander_id})"

    if answer:
        print(f"[policy] watch -> YES; disclosing for {bystander_id}.")
        behavior_disclose(bpm)
        return f"asked YES ({bystander_id})"
    print(f"[policy] watch -> NO; withholding for {bystander_id}.")
    behavior_withhold()
    return f"asked NO ({bystander_id})"


def main() -> None:
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)
    if face_cascade.empty():
        raise SystemExit(f"Could not load face detector from {cascade_path}.")

    print("[startup] opening webcam...", flush=True)
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise SystemExit(
            "Could not open webcam. Close any app using the camera "
            "(Zoom, Teams, browser tabs) and try again."
        )
    print("[startup] webcam open.", flush=True)

    if NO_OHBOT:
        print("[startup] NO_OHBOT=1 set; skipping Ohbot.", flush=True)
    else:
        print(
            f"[startup] initialising Ohbot (port hint='{OHBOT_PORT_HINT}'). "
            "If this hangs, the robot is likely not plugged in - rerun "
            "with NO_OHBOT=1 to skip it.",
            flush=True,
        )
        with ohbot_lock:
            ohbot.setSynthesizer("espeak")
            ohbot.init(OHBOT_PORT_HINT)
            ohbot.reset()
            ohbot.setVoice("-v en-gb+f3")
        print("[startup] Ohbot ready.", flush=True)

    print("[startup] preparing face detector + recogniser (YuNet + SFace)...", flush=True)
    yunet_path, sface_path = ensure_models()
    face_identifier = FaceIdentifier(yunet_path, sface_path)
    face_db = FaceDB(FACE_DB_PATH, match_threshold=SFACE_COSINE_SAME_PERSON)
    print(
        f"[face] gallery has {face_db.count()} known person(s); "
        f"new faces auto-IDed at cosine sim < {SFACE_COSINE_SAME_PERSON:.3f}.",
        flush=True,
    )

    owner_store = OwnerStore(OWNER_FACE_PATH)
    if not owner_store.has_owner():
        raise SystemExit(
            "[startup] No owner enrolled. Run this first:\n"
            "    python interface/presence/enroll_owner.py\n"
            "Then re-run this demo."
        )
    print(
        f"[owner] enrolled at {owner_store.enrolled_at()} "
        f"({owner_store.samples()} sample(s)).",
        flush=True,
    )

    print("[startup] starting watch BLE link...", flush=True)
    watch = BangleClient()
    if not watch.start():
        print("[ble] proceeding without watch link; all trials will withhold.")

    print(
        f"Re-Consent demo running. Observing for ~{int(OBSERVATION_WINDOW_S)}s "
        "before reacting. Press 'q' in the camera window to quit."
    )

    observations: deque[tuple[float, bool]] = deque()
    elevated_since: float | None = None
    armed_for_trial = True
    # Re-arm cadence for transient-failure aborts. See demo_cache_memory.py
    # for full discussion - "only owner" is intentionally NOT in this set;
    # the face-count-rose re-arm handles bystander arrivals.
    ABORT_RE_ARM_S = 3.0
    last_abort_re_arm_at: float = 0.0
    RETRYABLE_ABORT_STATUSES = {"aborted (no faces)"}
    face_count_at_last_trial: int = 0
    count_dropped_since_last_trial: bool = False

    trial_lock = threading.Lock()
    trial_state: dict[str, object] = {
        "in_trial": False,
        "last_status": "(none)",
    }

    def fire_trial_async(bpm_snapshot: int, frame_snapshot) -> bool:
        """Atomically claim the in_trial slot and start a worker.

        ``frame_snapshot`` is a deep copy of the frame at trial time;
        the worker runs face detection + embedding on it so the main
        loop's live capture buffer isn't being overwritten under us.

        Returns True if a worker was started, False if a trial was
        already in flight.
        """

        def worker() -> None:
            try:
                status = run_policy(
                    watch, face_identifier, face_db, owner_store,
                    bpm_snapshot, frame_snapshot,
                )
            except Exception as exc:
                traceback.print_exc()
                status = f"error: {exc}"
            finally:
                with trial_lock:
                    trial_state["last_status"] = status
                    trial_state["in_trial"] = False

        with trial_lock:
            if trial_state["in_trial"]:
                return False
            trial_state["in_trial"] = True
            trial_state["last_status"] = "identifying faces..."
            threading.Thread(
                target=worker, daemon=True, name="trial-worker"
            ).start()
            return True

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue

            now = time.monotonic()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.2,
                minNeighbors=5,
                minSize=(60, 60),
            )
            count = len(faces)
            face_visible = count >= 1

            observations.append((now, face_visible))
            while observations and observations[0][0] < now - OBSERVATION_WINDOW_S:
                observations.popleft()

            duration = observations[-1][0] - observations[0][0]
            fraction_face_visible = (
                sum(1 for _, v in observations if v) / len(observations)
            )
            have_full_window = duration >= OBSERVATION_WINDOW_S * 0.9

            bpm, last_hr_ts = watch.latest_bpm()
            fresh = (now - last_hr_ts) < HR_STALE_S
            if fresh and bpm > ELEVATED_BPM:
                if elevated_since is None:
                    elevated_since = now
            else:
                elevated_since = None
            elevated_stable = (
                elevated_since is not None
                and (now - elevated_since) >= MIN_ELEVATED_DWELL_S
            )
            # TEST-ONLY: force-elevated so trials fire on bystander presence
            # alone. Remove this line to restore the real HR gate.
            elevated_stable = True

            presence_verdict: str | None = None
            if have_full_window:
                if fraction_face_visible >= FACE_VISIBLE_FRACTION_HIGH:
                    presence_verdict = "FACE_IN_VIEW"
                elif fraction_face_visible <= FACE_VISIBLE_FRACTION_LOW:
                    presence_verdict = "NO_FACES"

            ble_up = watch.is_connected()
            if (
                presence_verdict == "NO_FACES"
                or not elevated_stable
                or not ble_up
            ):
                armed_for_trial = True

            with trial_lock:
                in_trial = bool(trial_state["in_trial"])
                last_trial_status = str(trial_state["last_status"])

            if (
                not in_trial
                and not armed_for_trial
                and last_trial_status in RETRYABLE_ABORT_STATUSES
                and (now - last_abort_re_arm_at) >= ABORT_RE_ARM_S
            ):
                armed_for_trial = True
                last_abort_re_arm_at = now
                print(
                    f"[trial] re-arming after abort ('{last_trial_status}')",
                    flush=True,
                )

            if count < face_count_at_last_trial:
                count_dropped_since_last_trial = True

            count_grew = count > face_count_at_last_trial
            count_recovered = (
                count_dropped_since_last_trial
                and count >= face_count_at_last_trial
                and face_count_at_last_trial > 0
            )
            if (
                not in_trial
                and not armed_for_trial
                and (count_grew or count_recovered)
            ):
                armed_for_trial = True
                count_dropped_since_last_trial = False
                reason = "grew" if count_grew else "recovered after a drop"
                print(
                    f"[trial] re-arming: face count {reason} to {count} "
                    f"(was {face_count_at_last_trial} at last trial)",
                    flush=True,
                )

            should_trial = (
                armed_for_trial
                and not in_trial
                and have_full_window
                and presence_verdict == "FACE_IN_VIEW"
                and elevated_stable
                and ble_up
            )
            if should_trial:
                armed_for_trial = False
                face_count_at_last_trial = count
                count_dropped_since_last_trial = False
                print(
                    "[trial] starting on worker thread. Face IDs will be "
                    "auto-assigned from the current frame; the camera "
                    "window stays open and quittable with 'q'.",
                    flush=True,
                )
                fire_trial_async(bpm, frame.copy())

            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            raw_label = "face visible" if face_visible else "no face"
            line1 = (
                f"raw: {raw_label}  faces={count}  "
                f"bpm={bpm if fresh else '--'}  "
                f"watch={'OK' if ble_up else 'OFFLINE'}"
            )
            if have_full_window:
                line2 = (
                    f"window {duration:.0f}s  "
                    f"{fraction_face_visible:.0%} face-in-view  "
                    f"verdict={presence_verdict or 'ambiguous'}  "
                    f"elevated={elevated_stable}"
                )
            else:
                line2 = (
                    f"observing... {duration:.0f}/{int(OBSERVATION_WINDOW_S)}s"
                )
            trial_tag = "[TRIAL IN PROGRESS] " if in_trial else ""
            line3 = f"{trial_tag}last trial: {last_trial_status}"
            for i, line in enumerate((line1, line2, line3)):
                cv2.putText(
                    frame,
                    line,
                    (20, 40 + i * 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2,
                )
            cv2.imshow("Re-Consent demo", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                shutting_down.set()
                break
    finally:
        shutting_down.set()
        cap.release()
        cv2.destroyAllWindows()
        watch.close()
        if not NO_OHBOT:
            acquired = ohbot_lock.acquire(timeout=10.0)
            if not acquired:
                print(
                    "[shutdown] ohbot_lock busy after 10s; skipping "
                    "reset/close. The serial port will be released by "
                    "process exit."
                )
            try:
                if acquired:
                    try:
                        ohbot.reset()
                    finally:
                        ohbot.close()
            finally:
                if acquired:
                    ohbot_lock.release()


if __name__ == "__main__":
    main()
