"""Re-Consent policy demo: always ask, never remember - reminder-triggered.

Same sensing pipeline as ``camera_remember.py`` (webcam presence, owner-vs-
bystander via SFace) and the same reminder trigger, but the disclosure decision
is taken **fresh every time**. There is no consent cache: every due reminder
with a bystander present triggers a new Yes/No prompt on the watch, even if the
same person answered a moment ago for a previous reminder.

This is the privacy "Re-Consent" baseline that the cache-memory demo is compared
against; the only difference is the absence of the stored-decision lookup. The
bystander is still **recognised** - IDs are minted and logged via the shared
``face_db.json`` gallery, and the owner is filtered out via ``owner_face.json`` -
but that identity is used only for logging here; it never short-circuits the
prompt.

The heart-rate trigger was removed - reminders are now the only trigger. As in
the main demo, the laptop terminal never takes input: every answer is given on
the watch, and the only laptop interaction is pressing 'q' in the camera window.

Run:
    python -m robot.apps.camera_reask
In the camera window: 'q' quits, 't' fires a TEST reminder immediately (a
sensitive one, so it exercises the head sweep and the consent flow) without
scheduling anything or waiting for the watch to be in range.
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

from robot.perception.camera_device import open_camera
from robot.perception.face_db import FaceDB
from robot.perception.face_id import (
    FaceIdentifier,
    SFACE_COSINE_SAME_PERSON,
    SFACE_OWNER_THRESHOLD,
    ensure_models,
)
from robot.perception.presence import identify_people_in_frames
from robot.core.head_scan import HeadScanner, LatestFrame, SCAN_SPEED
from robot.core.owner import OwnerStore
from robot.core.policy import BangleClient
from robot.core.reminders import Reminder, ReminderStore
from robot.core.logsetup import setup_logging, logcall, get_logger

log = get_logger(__name__)


OHBOT_PORT_HINT = os.environ.get("OHBOT_PORT", "Pico")
# Text spoken by the 't' test reminder (see fire_test_reminder in main).
TEST_REMINDER_TEXT = os.environ.get(
    "TEST_REMINDER_TEXT", "your doctor's appointment"
)
# Set NO_OHBOT=1 to skip Ohbot init/use entirely - the consent flow on the watch
# still runs and disclose/withhold are spoken via the OS voice.
NO_OHBOT = os.environ.get("NO_OHBOT") == "1"

if sys.platform == "darwin":
    _silence_wav = os.path.join(os.path.dirname(ohbot.__file__), "Silence1.wav")

    @logcall
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
shutting_down = threading.Event()
ohbot_lock = threading.Lock()


@logcall
def _speak_fallback(text: str) -> None:
    """OS-native TTS fallback when NO_OHBOT=1."""

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
REMINDER_POLL_S = 1.0     # how often (s) to re-read reminders.json from the loop

PROMPT_MESSAGE = (
    "I have noticed that someone is present with you. "
    "Do you want me to send private reminders in front of them?"
)
WITHHOLD_LINE = "Hello there."
REMINDER_DISCLOSE_TEMPLATE = "Here is your reminder for {text}."
REMINDER_PRIVATE_TEMPLATE = "Reminder: {text}"

# Shared with camera_remember.py - the face identity gallery and the reminder
# list are global, not policy-specific. There is deliberately NO consent cache.
from robot.paths import FACE_DB_PATH, OWNER_FACE_PATH, REMINDERS_PATH


@logcall
def deliver_reminder_spoken(text: str) -> None:
    """Speak a reminder out loud - owner-alone delivery, or a consented Yes."""

    msg = REMINDER_DISCLOSE_TEMPLATE.format(text=text)
    print(f">>> reminder disclose -> {msg!r}")
    log.info("reminder disclosed aloud: %r", msg, extra={"event": "delivered"})
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


@logcall
def behavior_withhold() -> None:
    """Reminder withheld from disclosure - Ohbot stays neutral."""

    print(f">>> withhold -> {WITHHOLD_LINE!r}")
    log.info("reminder withheld; neutral greeting only", extra={"event": "withheld"})
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


@logcall
def sensitivity_for(rem: Reminder) -> tuple[bool, str]:
    """Whether a reminder is sensitive (stored at add time, else classified live)."""

    if rem.sensitive is not None:
        return rem.sensitive, "stored at add time"
    from robot.core.sensitivity import classify

    res = classify(rem.text)
    return res.sensitive, f"classified live - {res.backend}: {res.reason}"


@logcall
def look_around(
    scanner: HeadScanner,
    face_identifier: FaceIdentifier,
    face_db: FaceDB,
    owner_store: OwnerStore,
    frame_bgr,
) -> tuple[str, list[tuple[str, float, bool, bool]], bool]:
    """Sweep the head, then identify everyone seen across the sweep.

    Identical sensing to ``camera_remember.py`` - the two apps differ only in
    whether the answer is remembered - so both call the shared
    ``robot.perception.presence.identify_people_in_frames``.
    """

    if scanner.enabled:
        print("[info-status] Before I say anything private, I will look around the "
              "room to check whether anyone else is here.")
    shots = scanner.scan(fallback_frame=frame_bgr)
    if not shots:
        print("[scan] no usable view captured; falling back to the frame in hand.")
        shots_frames = [frame_bgr]
    else:
        shots_frames = [s.frame for s in shots]
        if scanner.enabled:
            seen = ", ".join(f"{s.position:g}/10" for s in shots)
            print(f"[scan] looked at {len(shots)} head position(s): {seen}.")
    return identify_people_in_frames(
        face_identifier, face_db, owner_store, shots_frames
    )


@logcall
def run_reminder_policy(
    watch: BangleClient,
    face_identifier: FaceIdentifier,
    face_db: FaceDB,
    owner_store: OwnerStore,
    reminder: Reminder,
    frame_bgr,
    sensitive: bool,
    scanner: HeadScanner,
) -> str:
    """Deliver one due reminder - ALWAYS re-asking (no consent cache).

    Non-sensitive -> speak it. Sensitive with no bystander in view -> owner alone
    -> speak it. Sensitive with a bystander in view -> ask the watch fresh every
    time (the recognised id is only logged, never used to skip the prompt):
    Yes discloses aloud; No / no-reply pushes the reminder privately to the wrist.
    """

    text = reminder.text
    private = REMINDER_PRIVATE_TEMPLATE.format(text=text)

    if not sensitive:
        print("[info-status] Not sensitive - skipping the who-is-around check and "
              "disclosing to the owner now.")
        print(f"[reminder] {reminder.id}: non-sensitive -> speaking normally.")
        deliver_reminder_spoken(text)
        return f"delivered, non-sensitive [{reminder.id}]"

    print("[info-status] Sensitive - checking the camera to see whether the owner "
          "is alone or with someone else...")
    bystander_id, per_face, owner_detected = look_around(
        scanner, face_identifier, face_db, owner_store, frame_bgr
    )
    if owner_store.has_owner() and per_face and not owner_detected:
        sims = ", ".join(f"sim={sim:.2f}" for _, sim, _, _ in per_face)
        print(
            f"[reminder] {reminder.id}: owner not in camera frame (BLE confirms "
            f"in-room). Treating all faces as bystanders. owner-sim = [{sims}]."
        )
    if not bystander_id:
        print("[info-status] The owner is alone - nobody else anywhere I looked, so "
              "I can say the reminder out loud.")
        print(f"[reminder] {reminder.id}: no bystander in view -> owner alone.")
        log.info("reminder %s: no bystander in view -> owner alone", reminder.id,
                 extra={"event": "no_presence"})
        deliver_reminder_spoken(text)
        return f"delivered, owner alone [{reminder.id}]"

    def _fmt(entry):
        pid, sim, is_new, is_owner = entry
        tag = "[OWNER] " if is_owner else ("*" if is_new else "")
        return f"{tag}{pid} (sim={sim:.2f})"

    print("[info-status] I saw someone with the owner.")
    for pid, sim, is_new, is_owner in per_face:
        if is_owner:
            continue
        if is_new:
            print(f"[info-status] I have not seen this person before. I turned their "
                  f"face into a numeric embedding (a faceprint) and gave them the "
                  f"anonymous id {pid}. I do NOT keep the image or any personal data "
                  "- only the embedding.")
        else:
            print(f"[info-status] I recognise this person as {pid}: their faceprint "
                  f"matches a stored one (cosine similarity {sim:.2f} >= threshold "
                  f"{SFACE_COSINE_SAME_PERSON:.2f}).")
    print(f"[reminder] {reminder.id}: people in frame: "
          f"{', '.join(_fmt(e) for e in per_face)} -> log key '{bystander_id}'")
    log.info("reminder %s: bystander(s) in view -> key %r", reminder.id, bystander_id,
             extra={"event": "bystander_detected"})

    print("[info-status] Re-ask policy: I ask the owner every time and never save "
          "the answer.")
    print("[info-status] Asking the owner on the watch: may I say this reminder out "
          "loud in front of this person?")
    print(f"[reminder] {reminder.id}: asking the watch (re-consent always re-asks).")
    log.info("reminder %s: re-consent -> asking watch", reminder.id,
             extra={"event": "consent_asked"})
    answer = watch.ask_consent(PROMPT_MESSAGE, timeout=CONSENT_TIMEOUT_S)
    log.info("reminder %s: watch consent answer = %s", reminder.id, answer,
             extra={"event": "consent_answer"})
    if answer is None:
        print("[info-status] No answer from the watch - to stay safe I will NOT say "
              "it aloud; sending it privately.")
        print("[reminder] no answer from watch; delivering privately to the wrist.")
        watch.notify(private)
        return f"no-reply -> private ({bystander_id}) [{reminder.id}]"
    if answer:
        print("[info-status] The owner said YES - saying the reminder out loud.")
        print(f"[reminder] {reminder.id}: watch YES -> disclose aloud.")
        deliver_reminder_spoken(text)
        return f"asked YES ({bystander_id}) [{reminder.id}]"
    print("[info-status] The owner said NO - sending the reminder privately to the "
          "watch and greeting neutrally.")
    print(f"[reminder] {reminder.id}: watch NO -> private note on wrist.")
    watch.notify(private)
    behavior_withhold()
    return f"asked NO ({bystander_id}) [{reminder.id}]"


@logcall
def main() -> None:
    setup_logging(run_name="camera_reask")
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)
    if face_cascade.empty():
        raise SystemExit(f"Could not load face detector from {cascade_path}.")

    print("[startup] opening webcam...", flush=True)
    # Prefers the external head-mounted camera; CAMERA_DEVICE pins another one.
    cap = open_camera()
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
            "    python -m robot.apps.enroll_face\n"
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
        "Camera RE-ASK app running (reminder-triggered; always re-asks, never "
        "remembers).\n"
        "Keys (in the camera window): 'q' quit, 't' fire a TEST reminder now "
        "(sensitive; runs the head sweep + consent flow without scheduling "
        "anything or needing the watch in range)."
    )

    trial_lock = threading.Lock()
    trial_state: dict[str, object] = {"in_trial": False, "last_status": "(none)"}
    last_reminder_poll = 0.0
    next_reminder_info = "checking..."

    # Head sweep. The camera rides the head, so turning it is how the robot sees
    # more of the room than the owner's seat; the worker thread drives it while
    # this loop keeps capturing, and the two meet at `latest`.
    latest = LatestFrame()

    def move_head(position: float) -> None:
        if NO_OHBOT:
            return
        with ohbot_lock:
            if shutting_down.is_set():
                return
            try:
                ohbot.move(ohbot.HEADTURN, position, SCAN_SPEED)
            except Exception as exc:
                print(f"[scan] head move to {position:g} failed: {exc}")

    def set_scan_status(message: str) -> None:
        with trial_lock:
            trial_state["last_status"] = f"scanning - {message}"

    scanner = HeadScanner(
        latest,
        None if NO_OHBOT else move_head,
        on_status=set_scan_status,
        should_abort=shutting_down.is_set,
    )
    if scanner.enabled:
        positions = ", ".join(f"{p:g}" for p in scanner.positions)
        print(f"[scan] head sweep ON - checking for bystanders at HEADTURN {positions} "
              "before each sensitive reminder. Disable with HEAD_SCAN=0.", flush=True)
    else:
        print("[scan] head sweep OFF (no robot, or HEAD_SCAN=0); presence is judged "
              "from the straight-ahead view only.", flush=True)

    def fire_delivery_async(
        reminder: Reminder, frame_snapshot, sensitive: bool, persist: bool = True,
    ) -> bool:
        def worker() -> None:
            try:
                status = run_reminder_policy(
                    watch, face_identifier, face_db, owner_store,
                    reminder, frame_snapshot, sensitive, scanner,
                )
            except Exception as exc:
                traceback.print_exc()
                status = f"error: {exc}"
            finally:
                # A test reminder was never in the store, so leave it untouched.
                if persist:
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

    test_counter = {"n": 0}

    def fire_test_reminder(frame_snapshot) -> None:
        """Deliver a made-up sensitive reminder now ('t' in the camera window).

        Runs the real delivery path - head sweep, identification, consent - so
        the behaviour can be rehearsed without scheduling a reminder or waiting
        for one to fall due. It is marked sensitive so the sweep always runs,
        never touches ``reminders.json``, and skips the watch-in-range hold that
        gates a genuine reminder, so it works with the Bangle.js switched off.
        """

        test_counter["n"] += 1
        rem = Reminder(
            id=f"test_{test_counter['n']}",
            text=TEST_REMINDER_TEXT,
            remind_at=datetime.datetime.now().isoformat(timespec="seconds"),
            sensitive=True,
        )
        print(f"\n[test] firing test reminder {rem.id}: {rem.text!r} (sensitive). "
              "Nothing is written to reminders.json.", flush=True)
        if not fire_delivery_async(rem, frame_snapshot.copy(), True, persist=False):
            print("[test] a delivery is already running; ignoring.", flush=True)

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue
            # Offer every frame to a running head sweep (a no-op otherwise).
            latest.set(frame)

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
                    print(f"\n[info-status] Reminder found: {rem.text!r} "
                          f"(scheduled {rem.remind_at}).", flush=True)
                    print("[info-status] Checking if the owner is in the room "
                          "(via the watch's Bluetooth link)...", flush=True)
                    if not ble_up:
                        print("[info-status] The owner is not in the room yet - "
                              "holding the reminder until they are back.", flush=True)
                        print(f"[reminder] {rem.id} due but owner not present "
                              "(watch offline); holding.", flush=True)
                    else:
                        print("[info-status] The owner is in the room.", flush=True)
                        sensitive, note = sensitivity_for(rem)
                        print(f"[reminder] {rem.id} due: {rem.text!r} - "
                              f"{'SENSITIVE' if sensitive else 'non-sensitive'} "
                              f"({note}). Delivering on worker thread.", flush=True)
                        print("[info-status] " + (
                            "This reminder is SENSITIVE - I must check who is around "
                            "before saying it out loud." if sensitive else
                            "This reminder is NOT sensitive - it is safe to say out "
                            "loud even if someone else is nearby."), flush=True)
                        log.info("reminder %s due: %r (%s)", rem.id, rem.text,
                                 "sensitive" if sensitive else "non-sensitive",
                                 extra={"event": "reminder_due"})
                        fire_delivery_async(rem, frame.copy(), sensitive)

            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            line1 = f"faces={count}  watch={'OK' if ble_up else 'OFFLINE'}"
            line2 = f"reminders: {next_reminder_info}"
            trial_tag = "[DELIVERING] " if in_trial else ""
            line3 = f"{trial_tag}last: {last_trial_status}"
            line4 = "q=quit  t=test reminder (sensitive)"
            for i, line in enumerate((line1, line2, line3, line4)):
                cv2.putText(
                    frame, line, (20, 40 + i * 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2,
                )
            cv2.imshow("Camera - re-ask (reminder-triggered)", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                shutting_down.set()
                break
            if key == ord("t"):
                fire_test_reminder(frame)
    finally:
        shutting_down.set()
        cap.release()
        cv2.destroyAllWindows()
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
