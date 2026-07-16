"""Presence-aware consent demo - camera modality, reminder-triggered.

The camera twin of ``mic_remember.py`` (the voice runner). A reminder is added ahead of time
(``add_reminder.py``) with a due time; when that time arrives this demo
delivers it, gated by **who the webcam can see**:

  - Watch the webcam for faces; the owner (watch-wearer) is told apart from
    bystanders with SFace, having been enrolled once via ``enroll_face.py``.
  - When a reminder becomes due, deliver it:
      * non-sensitive reminder -> just speak it (no consent);
      * sensitive reminder, no bystander face in view -> owner alone -> speak it;
      * sensitive reminder, a bystander is in view -> ask the watch first
        ("...do you want me to send private reminders in front of them?").
        Yes -> the Ohbot speaks the reminder; No / no-reply -> the reminder is
        pushed privately to the wrist and the Ohbot only greets neutrally.
  - The decision is cached keyed by ``(bystander_id, "reminder")``, so the next
    time the *same* bystander is present the robot reuses the stored choice.

The heart-rate trigger was removed - reminders are now the only trigger.
Owner presence in the room is established by the watch's BLE link (so the owner
need not be on camera); the watch is also the private-disclosure + consent
channel, so a due reminder is held until the watch is connected.

Bystander identity is assigned automatically from the camera frame (YuNet +
SFace, persisted in ``face_db.json``); no labels are typed. The face consent
cache (``consent_cache.json``) is a separate namespace from the voice one.

Run:
    python -m robot.apps.camera_remember
Press 'q' in the camera window to quit.
"""

from __future__ import annotations

import datetime
import os
import subprocess
import sys
import threading
import time
import traceback

import cv2

try:
    from ohbot import ohbot
except ModuleNotFoundError as exc:
    raise SystemExit("Missing dependency: install with `pip install ohbot`.") from exc

from robot.perception.face_db import FaceDB
from robot.perception.face_id import (
    FaceIdentifier,
    SFACE_COSINE_SAME_PERSON,
    SFACE_OWNER_THRESHOLD,
    ensure_models,
)
from robot.core.owner import OwnerStore
from robot.core.policy import BangleClient, ConsentKey, ConsentStore
from robot.core.reminders import Reminder, ReminderStore


OHBOT_PORT_HINT = os.environ.get("OHBOT_PORT", "Pico")
# Set NO_OHBOT=1 to skip Ohbot init/use entirely. Useful when the robot isn't
# plugged in - the consent flow on the watch still runs and the disclose/withhold
# decisions are spoken via the OS voice.
NO_OHBOT = os.environ.get("NO_OHBOT") == "1"

# macOS shim for the ohbot SDK: it shells out to `aplay` which doesn't exist on
# Darwin. Use subprocess.run with a timeout (not os.system) so a hung afplay
# can't block the trial worker thread indefinitely.
if sys.platform == "darwin":
    _silence_wav = os.path.join(os.path.dirname(ohbot.__file__), "Silence1.wav")

    def _say_speech_macos(addSilence):
        try:
            if addSilence:
                subprocess.run(["afplay", _silence_wav], timeout=5, check=False)
            subprocess.run(["afplay", "ohbotspeech.wav"], timeout=30, check=False)
        except subprocess.TimeoutExpired:
            print("[ohbot] afplay timed out; continuing.")
        except FileNotFoundError:
            print("[ohbot] afplay not found; skipping audio.")

    ohbot.saySpeech = _say_speech_macos


# Shared state for thread-safe Ohbot access and shutdown coordination.
# - shutting_down: main thread sets this on 'q' or in finally so the worker
#   thread can abort promptly (watch round-trip, ohbot calls).
# - ohbot_lock:    serialises every call into the (non-thread-safe) ohbot SDK.
shutting_down = threading.Event()
ohbot_lock = threading.Lock()


def _speak_fallback(text: str) -> None:
    """Speak ``text`` via the OS-native TTS instead of the Ohbot (NO_OHBOT=1)."""

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


CONSENT_TIMEOUT_S = 30.0
# How often (s) to re-read reminders.json from the frame loop. The camera runs at
# frame rate; re-reading the store every frame would be wasteful, so throttle it.
REMINDER_POLL_S = 1.0

# Reminders share ONE content type so a bystander's Yes/No is remembered across
# every reminder, not re-asked for each.
REMINDER_CONTENT_TYPE = "reminder"
from robot.paths import (
    CONSENT_CACHE_PATH as CACHE_PATH,
    FACE_DB_PATH,
    OWNER_FACE_PATH,
    REMINDERS_PATH,
)

PROMPT_MESSAGE = (
    "I have noticed that someone is present with you. "
    "Do you want me to send private reminders in front of them?"
)
# Neutral line spoken when a reminder is withheld from disclosure.
WITHHOLD_LINE = "Hello there."
# Reminder content. Spoken aloud on a Yes or when the owner is alone; pushed
# privately to the wrist on a No.
REMINDER_DISCLOSE_TEMPLATE = "Here is your reminder. {text}."
REMINDER_PRIVATE_TEMPLATE = "Reminder: {text}"


def deliver_reminder_spoken(text: str) -> None:
    """Speak a reminder out loud - owner-alone delivery, or a consented Yes."""

    msg = REMINDER_DISCLOSE_TEMPLATE.format(text=text)
    print(f">>> reminder disclose -> {msg!r}")
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
            print(f"[ohbot] reminder disclose failed: {exc}")


def behavior_withhold() -> None:
    """Reminder withheld from disclosure - Ohbot stays neutral."""

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


def sensitivity_for(rem: Reminder) -> tuple[bool, str]:
    """Whether a reminder is sensitive (stored at add time, else classified live)."""

    if rem.sensitive is not None:
        return rem.sensitive, "stored at add time"
    from robot.core.sensitivity import classify

    res = classify(rem.text)
    return res.sensitive, f"classified live - {res.backend}: {res.reason}"


def identify_people_in_frame(
    face_identifier: FaceIdentifier,
    face_db: FaceDB,
    owner_store: OwnerStore,
    frame_bgr,
) -> tuple[str, list[tuple[str, float, bool, bool]], bool]:
    """Run YuNet+SFace on the frame.

    Returns ``(bystander_id, per_face_info, owner_detected)``.

    Identity model: the owner's presence in the room is established by the
    watch's BLE link (see ``BangleClient.is_connected``), not by the camera. So
    the owner may or may not be visible. If they happen to be in frame and the
    SFace embedding matches the owner template, they are filtered out of the
    cache key; otherwise every detected face is treated as a bystander.

    - ``bystander_id`` is the cache-store key: a colon-joined sorted set of
      person IDs for the NON-OWNER faces in the frame.
    - ``per_face_info`` is one tuple ``(person_id, similarity, is_new, is_owner)``
      per detected face, sorted by face area desc.
    - ``owner_detected`` is True iff some face matched the owner template above
      ``SFACE_OWNER_THRESHOLD``.
    """

    faces = face_identifier.detect_and_embed(frame_bgr)
    # Larger face = closer to camera. Sort order also gives the HUD a stable
    # rendering; the cache key sorts by ID separately.
    faces.sort(key=lambda f: f.area, reverse=True)
    if not faces:
        return "", [], False

    # Score every face against the owner template once. Pick the face with the
    # highest similarity *above* the owner threshold as the owner.
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


def run_reminder_policy(
    watch: BangleClient,
    store: ConsentStore,
    face_identifier: FaceIdentifier,
    face_db: FaceDB,
    owner_store: OwnerStore,
    reminder: Reminder,
    frame_bgr,
    sensitive: bool,
) -> str:
    """Deliver one due reminder, gated by camera face presence + watch consent.

    Non-sensitive -> speak it. Sensitive with no bystander in view -> owner alone
    -> speak it. Sensitive with a bystander in view -> reuse their remembered
    Yes/No, or ask the watch: Yes discloses aloud; No / no-reply pushes the
    reminder privately to the wrist while the robot greets neutrally. Returns a
    short status string for the HUD.
    """

    text = reminder.text
    private = REMINDER_PRIVATE_TEMPLATE.format(text=text)

    if not sensitive:
        print(f"[reminder] {reminder.id}: non-sensitive -> speaking normally.")
        deliver_reminder_spoken(text)
        return f"delivered, non-sensitive [{reminder.id}]"

    bystander_id, per_face, owner_detected = identify_people_in_frame(
        face_identifier, face_db, owner_store, frame_bgr
    )
    if owner_store.has_owner() and per_face and not owner_detected:
        sims = ", ".join(f"sim={sim:.2f}" for _, sim, _, _ in per_face)
        print(
            f"[reminder] {reminder.id}: owner enrolled but not in frame (BLE "
            f"confirms in-room). Treating all faces as bystanders. "
            f"owner-sim per face = [{sims}], threshold = {SFACE_OWNER_THRESHOLD:.2f}."
        )
    if not bystander_id:
        print(f"[reminder] {reminder.id}: no bystander in view -> owner alone.")
        deliver_reminder_spoken(text)
        return f"delivered, owner alone [{reminder.id}]"

    def _fmt(entry):
        pid, sim, is_new, is_owner = entry
        tag = "[OWNER] " if is_owner else ("*" if is_new else "")
        return f"{tag}{pid} (sim={sim:.2f})"

    print(f"[reminder] {reminder.id}: people in frame: "
          f"{', '.join(_fmt(e) for e in per_face)} -> bystander key '{bystander_id}'")

    key = ConsentKey(bystander_id=bystander_id, content_type=REMINDER_CONTENT_TYPE)
    cached = store.get(key)
    if cached is True:
        print(f"[reminder] {reminder.id}: cache YES for {bystander_id} -> disclose.")
        deliver_reminder_spoken(text)
        return f"cache-hit YES ({bystander_id}) [{reminder.id}]"
    if cached is False:
        print(f"[reminder] {reminder.id}: cache NO for {bystander_id} -> private note.")
        watch.notify(private)
        behavior_withhold()
        return f"cache-hit NO ({bystander_id}) [{reminder.id}]"

    print(f"[reminder] {reminder.id}: cache miss for {bystander_id}; asking watch...")
    answer = watch.ask_consent(PROMPT_MESSAGE, timeout=CONSENT_TIMEOUT_S)
    if answer is None:
        print("[reminder] no answer from watch; delivering privately to the wrist.")
        watch.notify(private)
        return f"no-reply -> private ({bystander_id}) [{reminder.id}]"
    store.put(key, answer)
    if answer:
        print(f"[reminder] {reminder.id}: watch YES -> disclose aloud.")
        deliver_reminder_spoken(text)
        return f"asked YES ({bystander_id}) [{reminder.id}]"
    print(f"[reminder] {reminder.id}: watch NO -> private note on wrist.")
    watch.notify(private)
    behavior_withhold()
    return f"asked NO ({bystander_id}) [{reminder.id}]"


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
            "    python -m robot.apps.enroll_face\n"
            "Then re-run this demo. The owner's face is used to distinguish the "
            "watch-wearer from bystanders so the consent cache is keyed by "
            "bystanders only."
        )
    print(
        f"[owner] enrolled at {owner_store.enrolled_at()} "
        f"({owner_store.samples()} sample(s)).",
        flush=True,
    )

    print("[startup] starting watch BLE link...", flush=True)
    watch = BangleClient()
    if not watch.start():
        print("[ble] proceeding without watch link; reminders are held until the "
              "owner (watch) is back in range.", flush=True)

    pending = ReminderStore(REMINDERS_PATH).pending()
    if pending:
        print(f"[reminders] {len(pending)} pending; next due {pending[0].remind_at} "
              f"({pending[0].text!r}).", flush=True)
    else:
        print("[reminders] none pending. Add one with add_reminder.py.",
              flush=True)
    print(
        "Cache-Memory demo running (reminder-triggered). A due reminder is "
        "delivered based on who the camera sees. Press 'q' to quit."
    )

    # Trial state shared with the worker thread that runs the blocking bits
    # (watch round-trip + Ohbot speech). Keeping the main loop free of blocking
    # calls is what keeps the camera window responsive.
    trial_lock = threading.Lock()
    trial_state: dict[str, object] = {"in_trial": False, "last_status": "(none)"}
    last_reminder_poll = 0.0
    next_reminder_info = "checking..."

    def fire_delivery_async(reminder: Reminder, frame_snapshot, sensitive: bool) -> bool:
        def worker() -> None:
            try:
                status = run_reminder_policy(
                    watch, store, face_identifier, face_db, owner_store,
                    reminder, frame_snapshot, sensitive,
                )
            except Exception as exc:
                traceback.print_exc()
                status = f"error: {exc}"
            finally:
                # A due reminder fires once, even if delivery hit an error.
                ReminderStore(REMINDERS_PATH).mark_delivered(reminder.id)
                with trial_lock:
                    trial_state["last_status"] = status
                    trial_state["in_trial"] = False

        with trial_lock:
            if trial_state["in_trial"]:
                return False
            trial_state["in_trial"] = True
            trial_state["last_status"] = f"delivering {reminder.id}..."
            threading.Thread(target=worker, daemon=True, name="delivery-worker").start()
            return True

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue

            now = time.monotonic()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(
                gray, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60),
            )
            count = len(faces)
            ble_up = watch.is_connected()

            with trial_lock:
                in_trial = bool(trial_state["in_trial"])
                last_trial_status = str(trial_state["last_status"])

            # Reminder trigger: throttled poll of the store. When a reminder is
            # due, deliver it (once) based on who the camera currently sees. Hold
            # it if the owner (watch) is not in range.
            if not in_trial and (now - last_reminder_poll) >= REMINDER_POLL_S:
                last_reminder_poll = now
                reminder_store = ReminderStore(REMINDERS_PATH)
                due = reminder_store.due(datetime.datetime.now())
                pend = reminder_store.pending()
                next_reminder_info = (
                    f"next {pend[0].remind_at} ({pend[0].text})" if pend
                    else "none pending"
                )
                if due:
                    rem = due[0]
                    if not ble_up:
                        print(f"[reminder] {rem.id} due but owner not present "
                              "(watch offline); holding.", flush=True)
                    else:
                        sensitive, note = sensitivity_for(rem)
                        print(f"\n[reminder] {rem.id} due: {rem.text!r} - "
                              f"{'SENSITIVE' if sensitive else 'non-sensitive'} "
                              f"({note}). Delivering on worker thread.", flush=True)
                        # Snapshot the frame so the worker isn't racing the live
                        # capture buffer (cv2 overwrites it on the next .read()).
                        fire_delivery_async(rem, frame.copy(), sensitive)

            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            line1 = (
                f"faces={count}  watch={'OK' if ble_up else 'OFFLINE'}"
            )
            line2 = f"reminders: {next_reminder_info}"
            trial_tag = "[DELIVERING] " if in_trial else ""
            line3 = f"{trial_tag}last: {last_trial_status}"
            for i, line in enumerate((line1, line2, line3)):
                cv2.putText(
                    frame, line, (20, 40 + i * 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2,
                )
            cv2.imshow("Camera - remember (reminder-triggered)", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                shutting_down.set()
                break
    finally:
        shutting_down.set()
        cap.release()
        cv2.destroyAllWindows()
        # Tear down the BLE link next: this cancels any pending consent future
        # inside BangleClient so a worker stuck in ask_consent unwinds promptly.
        watch.close()
        if not NO_OHBOT:
            acquired = ohbot_lock.acquire(timeout=10.0)
            if not acquired:
                print(
                    "[shutdown] ohbot_lock busy after 10s; skipping reset/close. "
                    "The serial port will be released by process exit."
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
