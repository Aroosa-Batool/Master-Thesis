"""Cache-Memory policy demo.

Same sensing pipeline as ``demo_with_watch.py`` (webcam face count +
heart rate from the Bangle.js), but the disclosure decision goes
through a consent cache keyed by ``(bystander_id, content_type)``:

  - First time we see a bystander while the user's heart rate is
    elevated: ask the watch ("I have noticed someone is present with
    you - do you want me to send private reminders in front of them?").
    Whatever the user taps is stored in the cache.
  - Next time we see the *same* bystander: skip the watch prompt
    entirely and reuse the stored decision.

This is the script the thesis brief calls the "Cache-Memory" policy.
The companion ``demo_reconsent.py`` always asks; the difference between
the two is exactly the cache lookup added here.

Bystander identification is a stand-in: the operator types a label
(e.g. "anna", "stranger_1") at the CLI when the trigger fires.
FaceNet-based re-identification (planned for week 2-3 of the thesis
schedule) will drop into this same slot later.

Run:
    python interface/presence/demo_cache_memory.py
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
from policy import BangleClient, ConsentKey, ConsentStore


OHBOT_PORT_HINT = os.environ.get("OHBOT_PORT", "Pico")
# Set NO_OHBOT=1 to skip Ohbot init/use entirely. Useful when the robot
# isn't plugged in - the consent flow on the watch still runs and the
# disclose/withhold decisions are printed instead of spoken.
NO_OHBOT = os.environ.get("NO_OHBOT") == "1"

# macOS shim for the ohbot SDK: it shells out to `aplay` which doesn't
# exist on Darwin. Use subprocess.run with a timeout (not os.system) so
# a hung afplay can't block the trial worker thread indefinitely.
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
# - shutting_down: main thread sets this on 'q' or in finally so the
#   worker thread can abort promptly (cancellable_input, ohbot calls).
# - ohbot_lock:    serialises every call into the (non-thread-safe)
#   ohbot SDK. Worker holds it during behavior_disclose/withhold;
#   main holds it during the finally reset/close path.
shutting_down = threading.Event()
ohbot_lock = threading.Lock()


def _speak_fallback(text: str) -> None:
    """Speak ``text`` via the OS-native TTS instead of the Ohbot.

    Used when ``NO_OHBOT=1`` so the disclose/withhold flow is still
    audible while you test without the robot plugged in. Blocking
    (waits for speech to finish) - this runs on the trial worker
    thread, never the main thread, so the camera window stays
    responsive. Best-effort: silently skips on platforms without
    a usable TTS binary.
    """

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


OBSERVATION_WINDOW_S = 15.0
# Window-vote thresholds: fraction of frames in the sliding window
# that contain at least one detected face.
#   >= FACE_VISIBLE_FRACTION_HIGH -> presence verdict "FACE_IN_VIEW"
#   <= FACE_VISIBLE_FRACTION_LOW  -> presence verdict "NO_FACES"
#   in between                    -> ambiguous; no verdict
# Owner-vs-bystander disambiguation happens at trial time via SFace.
# Owner presence in the room is established by BLE (watch link up),
# not by the camera - so this verdict no longer means "alone" vs
# "with a bystander", just "is the camera seeing anyone".
FACE_VISIBLE_FRACTION_HIGH = 0.7
FACE_VISIBLE_FRACTION_LOW = 0.3
ELEVATED_BPM = 100
MIN_ELEVATED_DWELL_S = 5.0
HR_STALE_S = 10.0
CONSENT_TIMEOUT_S = 30.0

CONTENT_TYPE = "elevated_hr"
CACHE_PATH = Path(__file__).resolve().parent / "consent_cache.json"
FACE_DB_PATH = Path(__file__).resolve().parent / "face_db.json"
OWNER_FACE_PATH = Path(__file__).resolve().parent / "owner_face.json"

PROMPT_MESSAGE = (
    "I have noticed that someone is present with you. "
    "Do you want me to send private reminders in front of them?"
)


DISCLOSE_TEMPLATE = (
    "I noticed your heart rate has been a bit elevated, around {bpm}. "
    "Would you like to take a few deep breaths together?"
)
WITHHOLD_LINE = "Hello there."


def behavior_disclose(bpm: int) -> None:
    """User has consented to share the wellbeing message out loud.

    Runs in the trial worker thread. With Ohbot present, holds
    ``ohbot_lock`` for the whole SDK conversation (move + say) so
    cleanup in main()'s finally never races us on the serial port.
    With ``NO_OHBOT=1`` set, falls back to the OS TTS so the operator
    still HEARS the disclosure - useful for testing the cache-memory
    flow end-to-end without the robot plugged in.
    """

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
    """User declined disclosure - Ohbot stays neutral."""

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
    """Run YuNet+SFace on the frame.

    Returns ``(bystander_id, per_face_info, owner_detected)``.

    Identity model: the owner's presence in the room is established
    by the watch's BLE link (see ``BangleClient.is_connected``), not
    by the camera. So the owner may or may not be visible. If they
    happen to be in frame and the SFace embedding matches the owner
    template, they are filtered out of the cache key; otherwise every
    detected face is treated as a bystander.

    Trade-off: if the owner IS in the frame but SFace fails to match
    them (bad angle, lighting, glasses), their face gets a stable
    ``person_NNN`` ID minted in the face gallery as if they were a
    bystander. Re-enroll if this happens often. We chose the simple
    behavior over the previous "abort trial when owner not detected"
    rule because the user wants trials to fire when only a bystander
    is in camera and the owner is in the room but not visible.

    - ``bystander_id`` is the cache-store key: a colon-joined sorted
      set of person IDs for the NON-OWNER faces in the frame.
    - ``per_face_info`` is one tuple ``(person_id, similarity, is_new,
      is_owner)`` per detected face, sorted by face area desc.
    - ``owner_detected`` is True iff some face matched the owner
      template above ``SFACE_OWNER_THRESHOLD``.
    """

    faces = face_identifier.detect_and_embed(frame_bgr)
    # Larger face = closer to camera. Sort order also gives the HUD a
    # stable rendering; the cache key sorts by ID separately.
    faces.sort(key=lambda f: f.area, reverse=True)
    if not faces:
        return "", [], False

    # Score every face against the owner template once. Pick the face
    # with the highest similarity *above* the owner threshold as the
    # owner - "max sim" is more defensible than "first match" because
    # it can survive a bystander whose face happens to score above the
    # threshold as long as the real owner scores higher.
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

    bystander_id = ":".join(sorted(set(bystanders)))
    return bystander_id, per_face, owner_idx >= 0


def run_policy(
    watch: BangleClient,
    store: ConsentStore,
    face_identifier: FaceIdentifier,
    face_db: FaceDB,
    owner_store: OwnerStore,
    bpm: int,
    frame_bgr,
) -> str:
    """Run one Cache-Memory trial. Returns a short status string for the HUD."""

    bystander_id, per_face, owner_detected = identify_people_in_frame(
        face_identifier, face_db, owner_store, frame_bgr
    )
    if not per_face:
        print("[policy] trial aborted (no faces detected by YuNet).")
        return "aborted (no faces)"
    if owner_store.has_owner() and not owner_detected:
        # New model: owner presence is BLE-driven, not camera-driven.
        # Owner is in the room (BLE-connected) but isn't currently in
        # the camera frame. Every visible face is therefore a bystander.
        sims = ", ".join(f"sim={sim:.2f}" for _, sim, _, _ in per_face)
        print(
            f"[policy] owner enrolled but not in camera frame "
            f"(BLE confirms in-room presence). Treating all faces as "
            f"bystanders. owner-sim per face = [{sims}], "
            f"threshold = {SFACE_OWNER_THRESHOLD:.2f}."
        )
    if not bystander_id:
        # Only the owner was visible. Trial doesn't apply.
        print("[policy] trial aborted (only owner detected; no bystanders).")
        return "aborted (only owner)"

    def _fmt(entry):
        pid, sim, is_new, is_owner = entry
        tag = "[OWNER] " if is_owner else ("*" if is_new else "")
        return f"{tag}{pid} (sim={sim:.2f})"

    pretty = ", ".join(_fmt(e) for e in per_face)
    print(f"[policy] people in frame: {pretty}  -> bystander key '{bystander_id}'")
    print("  (* = newly minted ID; [OWNER] = enrolled watch-wearer)")

    key = ConsentKey(bystander_id=bystander_id, content_type=CONTENT_TYPE)
    cached = store.get(key)
    if cached is True:
        print(f"[policy] cache hit for {bystander_id}: YES -> disclose without prompt")
        behavior_disclose(bpm)
        return f"cache-hit YES ({bystander_id})"
    if cached is False:
        print(f"[policy] cache hit for {bystander_id}: NO -> withhold without prompt")
        behavior_withhold()
        return f"cache-hit NO ({bystander_id})"

    print(f"[policy] cache miss for {bystander_id}: asking the watch...")
    answer = watch.ask_consent(PROMPT_MESSAGE, timeout=CONSENT_TIMEOUT_S)
    if answer is None:
        # Privacy-safe default: behave as if the user declined. Don't
        # cache this - the watch may have been unreachable, and a
        # no-reply isn't a real preference.
        print("[policy] no answer from watch; withholding (safe default).")
        behavior_withhold()
        return f"no-reply -> withhold ({bystander_id})"

    store.put(key, answer)
    if answer:
        print(f"[policy] watch -> YES; stored for {bystander_id} and disclosing.")
        behavior_disclose(bpm)
        return f"asked YES ({bystander_id})"
    print(f"[policy] watch -> NO; stored for {bystander_id} and withholding.")
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
        # Hold ohbot_lock for the whole init sequence too. No worker
        # thread can be running yet (BangleClient hasn't started), but
        # this keeps the contract uniform: every ohbot.* call lives
        # under the lock.
        with ohbot_lock:
            ohbot.setSynthesizer("espeak")
            ohbot.init(OHBOT_PORT_HINT)
            ohbot.reset()
            ohbot.setVoice("-v en-gb+f3")
        print("[startup] Ohbot ready.", flush=True)

    store = ConsentStore(CACHE_PATH)
    print(
        f"[cache] loaded {len(store.dump())} bystander record(s) from {CACHE_PATH}",
        flush=True,
    )

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
            "Then re-run this demo. The owner's face is used to "
            "distinguish the watch-wearer from bystanders so the consent "
            "cache is keyed by bystanders only."
        )
    print(
        f"[owner] enrolled at {owner_store.enrolled_at()} "
        f"({owner_store.samples()} sample(s)).",
        flush=True,
    )

    print("[startup] starting watch BLE link...", flush=True)
    watch = BangleClient()
    if not watch.start():
        print("[ble] proceeding without watch link; cache-miss trials will withhold.")

    print(
        f"Cache-Memory demo running. Observing for ~{int(OBSERVATION_WINDOW_S)}s "
        "before reacting. Press 'q' in the camera window to quit."
    )

    observations: deque[tuple[float, bool]] = deque()
    elevated_since: float | None = None
    # Track the verdict we last acted on so we only fire once per
    # encounter and re-arm when the situation changes.
    armed_for_trial = True
    # If a trial aborts in a transient way (YuNet didn't find a face
    # that Haar saw), re-arm at this cadence so a single detector miss
    # doesn't hard-lock the demo. Stable-state aborts like "only owner"
    # are intentionally NOT in this set - they re-arm only when the
    # camera count changes (see below).
    ABORT_RE_ARM_S = 3.0
    last_abort_re_arm_at: float = 0.0
    RETRYABLE_ABORT_STATUSES = {"aborted (no faces)"}
    # Snapshot of the Haar face count at the moment the last trial
    # fired. We re-arm when the current count exceeds this (someone
    # new walked in) OR when the count had dropped below it and then
    # come back to it (someone left and a different bystander joined
    # at the same headcount). Initialised to 0 so the very first
    # trial can fire as soon as the verdict stabilises.
    face_count_at_last_trial: int = 0
    count_dropped_since_last_trial: bool = False

    # Trial state shared with the worker thread that runs the blocking
    # bits (CLI prompt + watch round-trip + Ohbot speech). Keeping the
    # main loop free of blocking calls is what keeps the camera window
    # responsive and avoids the SIGTERM-on-frozen-window failure mode.
    trial_lock = threading.Lock()
    trial_state: dict[str, object] = {
        "in_trial": False,
        "last_status": "(none)",
    }

    def fire_trial_async(bpm_snapshot: int, frame_snapshot) -> bool:
        """Atomically claim the in_trial slot and start a worker.

        ``frame_snapshot`` is a deep copy of the frame at trial time;
        the worker runs face detection + embedding on it instead of
        racing the main loop's live capture buffer.

        Returns True if a worker was started, False if a trial was
        already in flight. Keeping the slot-claim and the thread spawn
        under the same ``trial_lock`` is what prevents a TOCTOU race
        where two consecutive main-loop iterations could spawn two
        workers before either had set in_trial=True.
        """

        def worker() -> None:
            try:
                status = run_policy(
                    watch, store, face_identifier, face_db, owner_store,
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
            # daemon=True: a worker stuck in watch.ask_consent must not
            # block process exit. The shutting_down event still lets
            # the worker wind down gracefully when we have time.
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

            # Re-arm when the camera goes empty, the HR gate clears, or
            # the watch link drops - any of these signals the start of a
            # new encounter for the next trial.
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

            # Re-arm after a transient-failure abort (rate-limited so a
            # broken detector can't spin spawning workers). "Only owner"
            # is intentionally excluded - it's a stable state, not a
            # transient one, so the count-change re-arm below handles
            # it instead.
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

            # Track whether the face count has dropped below the
            # last-trial floor at any point since the last fire. If it
            # has, then bouncing back up to the floor counts as a new
            # arrival (someone left and a different person joined at
            # the same headcount).
            if count < face_count_at_last_trial:
                count_dropped_since_last_trial = True

            # Re-arm if either (a) the count exceeds the last-trial
            # floor (someone strictly new joined), or (b) the count
            # dipped below the floor and has now recovered.
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
                # Snapshot the frame so the worker isn't racing the main
                # loop's live capture buffer (cv2 will overwrite it on
                # the next .read() call).
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
            cv2.imshow("Cache-Memory demo", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                # Signal the worker (if any) to abort its input()/ohbot
                # calls before we tear down BLE/Ohbot in the finally block.
                shutting_down.set()
                break
    finally:
        shutting_down.set()
        cap.release()
        cv2.destroyAllWindows()
        # Tear down the BLE link next: this cancels any pending consent
        # future inside BangleClient so a worker stuck in ask_consent
        # unwinds promptly.
        watch.close()
        if not NO_OHBOT:
            # Wait for any in-flight ohbot SDK call in the worker to
            # release ohbot_lock; the upper bound is one full
            # behavior_disclose worth of speech (~5-7s for the wellbeing
            # line), so 10s leaves margin. If we still can't get the
            # lock, log and skip cleanup - the worker is a daemon thread
            # and the process exit will release the serial port.
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
