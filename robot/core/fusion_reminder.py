"""Fused reminder engine - ONE pipeline that uses the mic first and the camera second.

Not run directly; it is the engine behind the two fused entry points, which
differ only in whether a bystander's consent decision is remembered:
  - ``robot.apps.fusion_remember`` -> ``run(remember=True)``  (cache-memory policy)
  - ``robot.apps.fusion_reask``    -> ``run(remember=False)`` (re-consent policy)

Where ``voice_reminder`` asks "who can I HEAR?" and the camera apps ask "who can
I SEE?", this one asks both, in a fixed priority order, and only escalates when
the cheaper/less invasive sensor says nobody is there. Both sensors stay OFF
until a sensitive reminder is actually due:

  1. a reminder has a due time (e.g. 18:42);
  2. a configurable lead (~5 min) before that time - detected by polling the
     clock, no mic and no camera - the reminder "wakes up";
  3. the AI sensitivity classifier (``sensitivity.py``) decides HOW to deliver it:
       - non-sensitive (an errand, "buy milk") -> just speak it at its time. No
         presence check, no consent; neither sensor ever opens. Done.
       - sensitive (health/finance/personal) -> run the gated flow below;
  4. IS THE OWNER PRESENT? The watch's BLE link is up == the owner is in ~the
     same room. If not, nothing opens at all and the reminder is held until they
     are back in range - the mic and camera are never used on an empty room;
  5. SENSOR 1, the MIC. From now until the due time the mic records CONTINUOUSLY
     (no on/off gaps) and the whole window is analysed once, at the due time. A
     non-owner HUMAN VOICE heard ANYWHERE in the window means a bystander is
     present - "human voice" being enforced by a neural VAD, so a grinder, fan or
     vacuum is loud but is not a person;
  6. SENSOR 2, the CAMERA - only reached when the mic heard nobody but the owner
     (or silence). The camera is opened for a few seconds, the robot turns its
     head through the sweep positions to look around the room, everyone seen is
     identified, and the camera is closed again. A preview window opens with the
     device and closes with it (``CAMERA_PREVIEW=0`` to suppress), so the time
     the camera is actually recording is visible rather than merely claimed.
     This stage catches the case the mic structurally cannot: a bystander who is
     present but never speaks;
  7. NOBODY FOUND by either sensor -> the owner is alone -> the sensitive
     information is revealed aloud;
  8. A BYSTANDER FOUND by either sensor -> only NOW is the decision taken. In
     REMEMBER mode a bystander with a stored Yes/No is reused (unknown -> asked
     once on the watch and stored); in RE-ASK mode the watch is asked EVERY time.
     Yes -> speak aloud; No / no-reply -> deliver privately to the wrist.

Why this order (the "priority"): the mic answers the question while the reminder
is still ripening - it uses the whole 5-minute window that would otherwise be
spent idle - and it needs no camera to be pointed anywhere. The camera is the
more invasive and slower sensor (it opens a video device and physically moves the
robot's head), so it runs only as a *double-check* on the mic's one blind spot, a
silent bystander. In the common owner-alone case the camera never opens at all.

Sensor priority is fixed and explicit in ``SENSOR_PRIORITY``; ``--no-camera``
drops stage 2 (a voice-only ablation) without touching anything else.

Everything here composes the EXISTING standalone pieces unchanged - the mic
window and its analysis come from ``robot.core.voice_reminder``, the head sweep
from ``robot.core.head_scan``, the face clustering/identification from
``robot.perception.presence``, and the speech + consent behaviours from
``robot.core.robot_io``. Nothing in those modules is modified or re-implemented,
so the four single-modality apps behave exactly as before.

Identity and consent memory:
  - the mic reuses the voice gallery (``voice_db.json``) + owner voice print;
  - the camera reuses the face gallery (``face_db.json``) + owner face print;
  - a consent decision is stored in its OWN cache (``consent_cache_fusion.json``)
    under a modality-prefixed key - ``voice:person_001`` / ``face:person_001`` -
    because a voice ``person_001`` and a face ``person_001`` are different people
    in different namespaces and must not collide in one cache.

Limitations, stated plainly:
  - NO CROSS-MODAL IDENTITY. The same human recognised by voice on Monday and by
    face on Tuesday is two different consent keys, so in REMEMBER mode they are
    asked about once per modality. Linking the two would need a joint
    audio-visual embedding, which this prototype does not have.
  - The camera double-check runs AFTER the due time (the mic window ends there),
    so a reminder that reaches stage 2 is spoken a few seconds late - the cost of
    the sweep. A mic hit costs nothing extra.
  - A silent bystander who is also out of every head-sweep position is still
    missed; presence sensing is best-effort, and the disclosure gate is only as
    good as the sensors.

Run (via the thin app wrappers):
    python -m robot.apps.fusion_remember                  # cache-memory policy
    python -m robot.apps.fusion_reask                     # re-consent policy
    NO_OHBOT=1 python -m robot.apps.fusion_remember       # OS voice, no robot
    python -m robot.apps.fusion_remember --no-camera      # mic only (ablation)

The unified ``robot.apps.reminder_app`` drives this same engine programmatically
via :class:`FusionReminderConfig` / :func:`run_config` with the split timing
(wake at T-7 min, mic T-7 -> T-2 min, camera fallback scheduled to finish close
to T) and ``camera_fail_safe=True`` (an inconclusive camera check withholds
privately instead of counting as "owner alone").
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
import threading
import time
import traceback
from dataclasses import dataclass

import cv2

try:
    import sounddevice as sd
except (ModuleNotFoundError, OSError) as exc:
    raise SystemExit(
        "Missing dependency: install with `pip install sounddevice` "
        "(needs the PortAudio library; on Linux: `apt install libportaudio2`)."
    ) from exc

# The mic window, its dual voiced/peak detector, the sensitivity lookup and the
# idle clock wait are taken from the standalone voice engine rather than copied,
# so the fused pipeline hears exactly what `mic_remember` hears.
from robot.core import voice_reminder as vr

# The consent/disclosure policy, the reminder paths, and the Ohbot glue
# (shim + lock + NO_OHBOT) all live in robot_io (imported as `demo`), shared with
# the voice engine - so a fused reminder is spoken by the same code path.
import robot.core.robot_io as demo

from robot.core.head_scan import (
    DEFAULT_FRAME_TIMEOUT_S,
    SCAN_SPEED,
    HeadScanner,
    LatestFrame,
    ScanShot,
    _positions_from_env,
    _settle_from_env,
)
from robot.core.logsetup import get_logger, logcall, setup_logging
from robot.core import presentation_telemetry as telemetry
from robot.core.owner import OwnerStore
from robot.core.policy import BangleClient, ConsentKey, ConsentStore
from robot.core.reminders import Reminder, ReminderStore
from robot.paths import (
    FACE_DB_PATH,
    FUSION_CONSENT_CACHE_PATH,
    OWNER_FACE_PATH,
    OWNER_VOICE_PATH,
    REMINDERS_PATH,
    VOICE_DB_PATH,
)
from robot.perception.audio_device import pick_input_device
from robot.perception.camera_device import open_camera
from robot.perception.face_db import FaceDB
from robot.perception.face_id import (
    SFACE_COSINE_SAME_PERSON,
    SFACE_OWNER_THRESHOLD,
    FaceIdentifier,
    ensure_models,
)
from robot.perception.presence import identify_people_in_frames
from robot.perception.speech_vad import MIN_SPEECH_S, get_speech_detector
from robot.perception.voice_id import VOICE_SAME_SPEAKER, VoiceIdentifier

log = get_logger(__name__)


# The two sensing stages, in the order they are tried. The camera stage runs ONLY
# if the mic stage found nobody, so in the owner-alone case (the common one) the
# camera is never opened - see the module docstring for why this order.
MODALITY_MIC = "mic"
MODALITY_CAMERA = "camera"
SENSOR_PRIORITY: tuple[str, ...] = (MODALITY_MIC, MODALITY_CAMERA)

# Consent-key namespace per modality. A voice `person_001` and a face
# `person_001` are different people from different galleries; without this prefix
# they would share one cache entry and one person's Yes would answer for another.
CONSENT_ID_PREFIX = {MODALITY_MIC: "voice", MODALITY_CAMERA: "face"}

# How long the capture loop naps after a failed read before trying again, so a
# camera that stalls mid-sweep cannot turn that loop into a busy-wait. The sweep
# itself is bounded by head_scan's own per-position frame timeout.
CAMERA_GRAB_IDLE_S = 0.01

# Budget estimate for the whole camera stage (open + warm up the device, then
# sweep the head and grab a frame per position). Used ONLY to schedule the
# fallback scan: when the mic window closes early (the unified app records
# T-7min -> T-2min), the scan is delayed so it finishes close to the reminder's
# time - the freshest practical look at the room - instead of running minutes
# early and going stale. Overestimating just starts the scan a little earlier.
CAMERA_OPEN_BUDGET_S = 8.0     # device open + auto-exposure warm-up, typical
SCAN_MARGIN_S = 5.0            # identification + slack

# Live preview while the camera stage runs. The single-modality camera apps keep
# a window open for their whole session; this pipeline cannot, because the point
# of the mic-first priority is that the camera device stays closed unless the mic
# came up empty. So the window opens WITH the device and closes WITH it - what is
# on screen is exactly the interval the camera is actually recording, which is
# also what makes the "camera stays closed" claim visible rather than asserted.
# Set CAMERA_PREVIEW=0 for a headless run (no HighGUI window at all).
CAMERA_PREVIEW_ENV = "CAMERA_PREVIEW"
CAMERA_PREVIEW_WINDOW = "Reminder - camera presence check"

# How long to wait for the sweep thread to unwind if the capture loop breaks out
# early (a camera that raised mid-check). The sweep is bounded by head_scan's own
# per-position timeouts, so this only has to cover the last position.
SCAN_JOIN_TIMEOUT_S = 10.0


def _preview_enabled() -> bool:
    """Whether the camera stage should show what it sees (CAMERA_PREVIEW=0 off)."""

    return os.environ.get(CAMERA_PREVIEW_ENV) != "0"


@logcall
def _camera_stage_budget_s() -> float:
    """Estimated seconds the camera stage needs, from open to identified."""

    positions = _positions_from_env()
    per_position = _settle_from_env() + DEFAULT_FRAME_TIMEOUT_S
    return CAMERA_OPEN_BUDGET_S + len(positions) * per_position + SCAN_MARGIN_S


@dataclass
class FusionReminderConfig:
    """Programmatic configuration for :func:`run_config`.

    Same lead/record split as ``voice_reminder.VoiceReminderConfig``: the legacy
    CLI uses one ``--lead`` for both the wake-up lead and the recording window
    (``record_s=None`` records right up to the due time); the unified
    ``robot.apps.reminder_app`` wakes at T - ``lead_s`` and records for exactly
    ``record_s`` seconds, leaving the remaining pre-reminder interval for the
    camera double-check when the mic heard nobody.

    ``camera_fail_safe`` controls what an INCONCLUSIVE camera stage (no usable
    frame, failed open, failed scan/identification) means for a sensitive
    reminder: ``True`` withholds it and delivers privately to the wrist (a
    sensor failure must never read as "the owner is alone"); ``False`` keeps
    the legacy fusion apps' documented fail-open (fall back to the mic result,
    which was "nobody heard", and disclose).
    """

    remember: bool
    poll_s: float = vr.DEFAULT_POLL_S
    lead_s: float = vr.DEFAULT_LEAD_S
    record_s: float | None = None
    gate: float = vr.DEFAULT_RMS_GATE
    min_voiced: float = vr.DEFAULT_VOICED_FRACTION_MIN
    peak: float = vr.DEFAULT_PEAK_RMS
    min_speech: float = MIN_SPEECH_S
    no_camera: bool = False
    camera_fail_safe: bool = True
    target_reminder_id: str | None = None


@dataclass(frozen=True)
class Bystander:
    """One non-owner person found by one of the sensors.

    ``consent_id`` is what the consent cache is keyed by (modality-prefixed);
    ``raw_id`` is the gallery id as minted by ``face_db`` / ``voice_db``, kept for
    the operator-facing lines and the logs.
    """

    raw_id: str
    modality: str

    @property
    def consent_id(self) -> str:
        return f"{CONSENT_ID_PREFIX[self.modality]}:{self.raw_id}"

    @property
    def found_by(self) -> str:
        return "heard on the mic" if self.modality == MODALITY_MIC else "seen on the camera"


class _CameraSession:
    """Open the webcam for exactly as long as one presence check needs it.

    The camera apps keep a live preview loop running for their whole session; the
    fused pipeline must not, because the point of the mic-first priority is that
    the camera stays closed unless the mic came up empty. So the device is opened
    here, driven for the length of one sweep, and released again.

    The split of work is the one ``head_scan`` documents: THIS thread owns the
    capture and the preview window, the blocking sweep runs on a worker, and the
    two meet only at ``LatestFrame`` (which is what the sweep waits on for a
    picture newer than the head movement). Capture stays on the caller's thread
    because cv2's HighGUI is only reliable on the main thread on macOS.

    Used as a context manager so an exception mid-sweep still releases the camera
    and closes the window:

        with _CameraSession() as cam:
            shots = cam.run_scan()
    """

    @logcall
    def __init__(self, preview_identifier: FaceIdentifier | None = None) -> None:
        self._cap = None
        self.latest = LatestFrame()
        self.scanner: HeadScanner | None = None
        self._preview = _preview_enabled()
        self._status_lock = threading.Lock()
        self._status = "looking around the room..."
        self._preview_identifier = preview_identifier
        self._last_preview_detect = 0.0
        self._preview_faces = []

    def __enter__(self) -> "_CameraSession":
        self._cap = open_camera()
        self.scanner = HeadScanner(
            self.latest,
            None if demo.NO_OHBOT else _move_head,
            on_status=self._set_status,
            should_abort=demo.shutting_down.is_set,
        )
        telemetry.sensor("camera", True)
        telemetry.stage("camera", "active", "Robot-eye camera opened for the fallback head scan.")
        return self

    def __exit__(self, *_exc) -> None:
        self._close_preview()
        if self._cap is not None:
            self._cap.release()
        telemetry.sensor("camera", False)
        telemetry.clear_frame()
        print("[camera] closed again (it is only open during a presence check).",
              flush=True)
        log.info("camera released", extra={"event": "camera_closed"})

    def run_scan(self) -> list[ScanShot]:
        """Sweep the head on a worker while this thread captures and previews.

        Returns what :meth:`HeadScanner.scan` returned; an exception raised
        inside the sweep is re-raised here, so the caller sees it exactly as if
        the scan had run inline.
        """

        result: dict[str, object] = {}
        done = threading.Event()

        def worker() -> None:
            try:
                result["shots"] = self.scanner.scan()
            except BaseException as exc:      # noqa: BLE001 - re-raised below
                result["exc"] = exc
            finally:
                done.set()

        thread = threading.Thread(target=worker, daemon=True,
                                  name="fusion-head-scan")
        thread.start()
        try:
            while not done.is_set():
                ok, frame = self._cap.read()
                if ok and frame is not None:
                    # A cheap no-op except while the sweep is waiting for a
                    # frame at a settled head position.
                    self.latest.set(frame)
                    self._show(frame)
                else:
                    time.sleep(CAMERA_GRAB_IDLE_S)
        finally:
            thread.join(timeout=SCAN_JOIN_TIMEOUT_S)
        exc = result.get("exc")
        if exc is not None:
            raise exc
        return result.get("shots") or []

    def _set_status(self, message: str) -> None:
        """Head-sweep progress, shown on the preview (called from the worker)."""

        with self._status_lock:
            self._status = message
        telemetry.metric("head_position", message)

    def _show(self, frame) -> None:
        """Draw one preview frame; a display-less build just turns it off."""

        if not self._preview and not telemetry.enabled():
            return
        with self._status_lock:
            status = self._status
        hud = frame.copy()
        now = time.monotonic()
        if self._preview_identifier is not None and now - self._last_preview_detect >= 0.20:
            try:
                self._preview_faces = self._preview_identifier.detect_and_embed(frame)
            except Exception:
                self._preview_faces = []
            self._last_preview_detect = now
        for face in self._preview_faces:
            x, y, fw, fh = face.bbox
            cv2.rectangle(hud, (x, y), (x + fw, y + fh), (45, 210, 90), 2)
            cv2.putText(
                hud, f"face {face.confidence:.2f}", (x, max(22, y - 7)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.58, (45, 210, 90), 2,
            )
        lines = (
            "Camera check: the mic heard no one - looking for a quiet bystander",
            status,
            "the camera closes again as soon as this check finishes",
        )
        for i, line in enumerate(lines):
            cv2.putText(hud, line, (20, 40 + i * 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        telemetry.frame(hud)
        if not self._preview:
            return
        try:
            cv2.imshow(CAMERA_PREVIEW_WINDOW, hud)
            cv2.waitKey(1)
        except cv2.error as exc:
            # Headless OpenCV build or no display: the check itself is unaffected,
            # so drop the window rather than failing the presence check.
            print(f"[camera] no preview window available ({exc}); the check "
                  "continues without it.", flush=True)
            self._preview = False

    def _close_preview(self) -> None:
        if not self._preview:
            return
        try:
            cv2.destroyWindow(CAMERA_PREVIEW_WINDOW)
            cv2.waitKey(1)     # macOS needs a pump for the window to actually go
        except cv2.error:
            pass


@logcall
def _move_head(position: float) -> None:
    """Turn the Ohbot's head for the sweep (no-op without a robot).

    Injected into ``HeadScanner`` rather than imported by it, so the scanner stays
    free of the Ohbot SDK and of this app's lock. Same guard as the camera apps:
    every SDK call goes through ``demo.ohbot_lock``, and a shutdown aborts.
    """

    if demo.NO_OHBOT:
        return
    bot = demo.load_ohbot()
    with demo.ohbot_lock:
        if demo.shutting_down.is_set():
            return
        try:
            bot.move(bot.HEADTURN, position, SCAN_SPEED)
        except Exception as exc:
            print(f"[scan] head move to {position:g} failed: {exc}", flush=True)


@logcall
def check_mic(
    rem: Reminder,
    remind_at: datetime.datetime,
    voice_identifier: VoiceIdentifier,
    voice_db: FaceDB,
    owner_voice: OwnerStore,
    record_s: float | None = None,
) -> Bystander | None:
    """SENSOR 1 - listen across the whole pre-reminder window; who was heard?

    Delegates to the standalone voice engine: ``record_until`` holds the mic open
    continuously until the due time (so a bystander who speaks at ANY instant is
    captured, not just during a sample), and ``analyse_presence`` runs the dual
    sustained/bursty energy test over the whole recording and then embeds it once
    to identify a non-owner speaker.

    Returns the bystander, or ``None`` when only the owner (or nothing) was heard
    - which is the condition that escalates to the camera.
    """

    print("[fusion] sensor 1/2 - MIC: listening across the monitoring window...",
          flush=True)
    print("[info-status] First I will listen: if I hear another voice, I already "
          "know someone else is here and I will not need the camera.", flush=True)
    audio = vr.record_until(remind_at, rem.id, record_s)
    raw_id = vr.analyse_presence(audio, voice_identifier, voice_db, owner_voice, rem.id)
    # The raw recording is never retained past its analysis.
    del audio
    if raw_id is None:
        print(f"[fusion] {rem.id}: mic found no bystander.", flush=True)
        log.info("mic stage found no bystander (%s)", rem.id,
                 extra={"event": "stage_mic_clear"})
        return None
    log.info("mic stage found bystander %s (%s)", raw_id, rem.id,
             extra={"event": "stage_mic_hit"})
    return Bystander(raw_id=raw_id, modality=MODALITY_MIC)


@logcall
def check_camera(
    rem: Reminder,
    face_identifier: FaceIdentifier,
    face_db: FaceDB,
    owner_face: OwnerStore,
) -> tuple[Bystander | None, bool]:
    """SENSOR 2 - open the camera, look around the room; who is visible?

    Reached only when the mic heard nobody. Opens the webcam, sweeps the head
    through its positions (``HeadScanner``), clusters and identifies everyone seen
    across the sweep (``identify_people_in_frames`` - which is what stops one
    person photographed at two head positions becoming two ids), and closes the
    camera again. The camera is released and the head re-centred in every path,
    success or failure (the session context manager + the scanner's ``finally``).

    Returns ``(bystander, conclusive)``:

    - ``(Bystander, True)``  - someone besides the owner is visible;
    - ``(None, True)``       - the sweep ran and saw nobody but the owner;
    - ``(None, False)``      - the check is INCONCLUSIVE: the camera would not
      open, yielded no usable frame, or the scan/identification raised. The
      caller decides what that means: the legacy fusion apps keep their
      documented fail-open (fall back to the mic result - "nobody heard" - and
      reveal), while ``camera_fail_safe`` mode treats it as "cannot verify the
      room" and withholds privately. Either way it is logged as a warning so a
      run where the double-check silently did nothing is visible in the CSV
      rather than passing for a clean all-clear.
    """

    print("[fusion] sensor 2/2 - CAMERA: the mic heard no one else, double-checking "
          "by looking around.", flush=True)
    print("[info-status] I did not hear anyone else, but someone could be here "
          "quietly - so before I say anything private I will look around the room.",
          flush=True)
    # The camera is open ONLY for the sweep. Recognition then runs on the frames
    # already in hand, with the device closed - the shortest camera-on time the
    # check can have, which is the whole point of reaching for it last.
    #
    # SystemExit is caught alongside Exception because open_camera() signals an
    # unusable camera that way; mid-run it must degrade to "inconclusive", not
    # kill the whole reminder loop. KeyboardInterrupt still propagates.
    try:
        with _CameraSession(face_identifier) as cam:
            shots = cam.run_scan()
            swept = cam.scanner.enabled
        if not shots:
            print("[scan] WARNING: no usable view captured - the double-check saw "
                  "nothing at all.", flush=True)
            log.warning("camera stage got no frames; check is inconclusive (%s)",
                        rem.id, extra={"event": "stage_camera_blind"})
            telemetry.stage("camera", "warning", "No usable camera frame; presence is inconclusive.")
            return None, False
        if swept:
            seen = ", ".join(f"{s.position:g}/10" for s in shots)
            print(f"[scan] looked at {len(shots)} head position(s): {seen}.",
                  flush=True)
        bystander_key, per_person, owner_detected = identify_people_in_frames(
            face_identifier, face_db, owner_face, [s.frame for s in shots]
        )
    except (Exception, SystemExit) as exc:
        print(f"[scan] WARNING: the camera check failed ({exc}) - the double-check "
              "saw nothing at all.", flush=True)
        log.warning("camera stage failed (%s); check is inconclusive (%s)",
                    exc, rem.id, extra={"event": "stage_camera_blind"})
        telemetry.stage("camera", "warning", f"Camera check failed: {exc}")
        return None, False

    if owner_face.has_owner() and per_person and not owner_detected:
        sims = ", ".join(f"sim={sim:.2f}" for _, sim, _, _ in per_person)
        print(f"[fusion] {rem.id}: owner enrolled but not in frame (BLE confirms "
              f"in-room). Treating all faces as bystanders. owner-sim per face = "
              f"[{sims}], threshold = {SFACE_OWNER_THRESHOLD:.2f}.", flush=True)

    if not bystander_key:
        print(f"[fusion] {rem.id}: camera saw no bystander either.", flush=True)
        log.info("camera stage found no bystander (%s)", rem.id,
                 extra={"event": "stage_camera_clear"})
        telemetry.stage("camera", "complete", "Head scan found no bystander; camera closed.")
        telemetry.stage("identity", "skipped", "No camera bystander to identify.")
        return None, True

    print("[info-status] I saw someone with the owner.", flush=True)
    for pid, sim, is_new, is_owner in per_person:
        if is_owner:
            continue
        if is_new:
            print(f"[info-status] I have not seen this person before. I turned their "
                  f"face into a numeric embedding (a faceprint) and gave them the "
                  f"anonymous id {pid}. I do NOT keep the image or any personal data "
                  "- only the embedding.", flush=True)
        else:
            print(f"[info-status] I recognise this person as {pid}: their faceprint "
                  f"matches a stored one (cosine similarity {sim:.2f} >= threshold "
                  f"{SFACE_COSINE_SAME_PERSON:.2f}), so it is the same person as "
                  "before.", flush=True)
    print(f"[fusion] {rem.id}: camera bystander key '{bystander_key}'.", flush=True)
    log.info("camera stage found bystander %s (%s)", bystander_key, rem.id,
             extra={"event": "stage_camera_hit"})
    telemetry.stage("camera", "complete", "Head scan found a bystander; camera closed.")
    telemetry.stage(
        "identity", "complete", f"Camera bystander resolved as {bystander_key}.",
        identity=bystander_key, modality="face",
    )
    return Bystander(raw_id=bystander_key, modality=MODALITY_CAMERA), True


@logcall
def sense_presence(
    rem: Reminder,
    remind_at: datetime.datetime,
    voice_identifier: VoiceIdentifier,
    voice_db: FaceDB,
    owner_voice: OwnerStore,
    face_identifier: FaceIdentifier | None,
    face_db: FaceDB | None,
    owner_face: OwnerStore | None,
    *,
    record_s: float | None = None,
    poll_s: float = vr.DEFAULT_POLL_S,
) -> tuple[Bystander | None, bool]:
    """Run the sensors in ``SENSOR_PRIORITY`` order and stop at the first hit.

    This is the "call the other functions by priority" step: the mic first
    (it uses the waiting window anyway), the camera only if the mic came up empty.
    Passing ``face_identifier=None`` (from ``--no-camera``) drops stage 2, leaving
    a mic-only pipeline for comparison.

    When the mic window closes before the due time (an explicit ``record_s``, as
    the unified app uses), the camera stage is DELAYED so the sweep finishes as
    close to the due time as its estimated budget allows - the freshest practical
    look at the room, instead of a scan minutes early that could go stale.

    Returns ``(bystander, conclusive)``; ``conclusive=False`` means the LAST
    sensor consulted could not actually verify the room (camera failure) - see
    :func:`check_camera` for what callers do with that.
    """

    conclusive = True
    for modality in SENSOR_PRIORITY:
        if modality == MODALITY_MIC:
            found = check_mic(rem, remind_at, voice_identifier, voice_db,
                              owner_voice, record_s)
        elif modality == MODALITY_CAMERA:
            if face_identifier is None or face_db is None or owner_face is None:
                print("[fusion] camera double-check disabled (--no-camera); going on "
                      "the mic result alone.", flush=True)
                continue
            # Use the remaining pre-reminder interval: start the scan only when
            # its estimated budget just fits before the due time. If the due
            # time is closer than the budget (or already past), scan right away.
            budget = _camera_stage_budget_s()
            scan_at = remind_at - datetime.timedelta(seconds=budget)
            if (scan_at - datetime.datetime.now()).total_seconds() > 0:
                print(f"[fusion] {rem.id}: waiting until ~{scan_at:%H:%M:%S} "
                      f"(T-{int(budget)}s) so the camera look is as fresh as "
                      "possible; both sensors stay off meanwhile.", flush=True)
                vr.wait_until(scan_at, poll_s)
            found, conclusive = check_camera(rem, face_identifier, face_db,
                                             owner_face)
        else:                                   # pragma: no cover - guarded by the tuple
            continue
        if found is not None:
            print(f"[fusion] {rem.id}: bystander {found.raw_id} {found.found_by}; "
                  "skipping any remaining sensor.", flush=True)
            return found, True
    return None, conclusive


@logcall
def decide_and_deliver(
    rem: Reminder,
    bystander: Bystander | None,
    watch: BangleClient,
    consent_store: ConsentStore | None,
    *,
    conclusive: bool = True,
    fail_safe: bool = False,
) -> str | None:
    """Reveal, reuse a remembered answer, or ask the watch - then deliver.

    Called once both sensors have had their say. Identical policy to the
    single-modality apps, so the fused condition is comparable with them:

      - no bystander            -> the owner is alone -> reveal the reminder aloud;
      - bystander, REMEMBER mode-> reuse their stored Yes/No if there is one;
      - bystander, no memory /
        RE-ASK mode             -> ask on the watch. Yes -> aloud;
                                   No / no-reply -> privately to the wrist.

    ``conclusive=False`` (the camera stage failed to verify the room) with
    ``fail_safe=True`` withholds the reminder and delivers it privately - a
    sensor failure must never be read as "the owner is alone". With
    ``fail_safe=False`` (the legacy fusion apps) the mic result stands and the
    reminder is revealed, as documented in :func:`check_camera`.

    Returns a status string for the log, or ``None`` to HOLD the reminder without
    delivering it (the owner left during the window) - the caller then leaves it
    pending and retries when the watch is back in range.
    """

    text = rem.text
    private = demo.REMINDER_PRIVATE_TEMPLATE.format(text=text)

    # Re-confirm the owner is still here at the instant of delivery: they may have
    # walked out during the (up to 5 min) window. If gone, HOLD rather than
    # announcing to an empty room or over a bystander with the owner absent.
    if not watch.is_connected():
        print(f"[fusion] {rem.id}: owner not present at delivery time (left during "
              "the window) -> holding until they are back in range.", flush=True)
        log.info("owner left during window; holding %s", rem.id,
                 extra={"event": "owner_left"})
        return None

    if bystander is None and not conclusive and fail_safe:
        # The selected sensor could not actually verify the room. Privacy-safe
        # default: do NOT speak aloud; the owner still gets the reminder on the
        # wrist, and the robot stays neutral.
        print("[info-status] I could not verify whether the owner is alone (the "
              "camera check failed), so to stay safe I will NOT say the reminder "
              "out loud - I am sending it privately to the watch instead.",
              flush=True)
        print(f"[fusion] {rem.id}: presence check INCONCLUSIVE -> private note "
              "(fail-safe).", flush=True)
        log.info("inconclusive presence; withholding %s (fail-safe)", rem.id,
                 extra={"event": "inconclusive_withheld"})
        watch.notify(private)
        demo.behavior_withhold()
        telemetry.stage("consent", "skipped", "Presence was inconclusive; no disclosure consent inferred.")
        telemetry.stage("memory", "skipped", "No explicit answer was received.")
        telemetry.stage("delivery", "complete", "Fail-safe private wrist delivery.")
        telemetry.emit("outcome", outcome="private", detail="Inconclusive camera check")
        return f"reminder inconclusive -> private (sensor unverified) [{rem.id}]"

    if bystander is None:
        print("[info-status] The owner is alone - I neither heard nor saw anyone "
              "else, so I can say the reminder out loud.", flush=True)
        print(f"[fusion] {rem.id}: no bystander from any sensor -> owner alone.",
              flush=True)
        log.info("no bystander from any sensor; owner alone %s", rem.id,
                 extra={"event": "no_presence"})
        demo.deliver_reminder_spoken(text)
        telemetry.stage("consent", "skipped", "Owner is alone; no consent prompt needed.")
        telemetry.stage("memory", "skipped", "No consent decision was requested.")
        telemetry.stage("delivery", "complete", "Sensitive reminder spoken aloud to the owner.")
        telemetry.emit("outcome", outcome="spoken", detail="Both sensors clear")
        return f"reminder revealed, owner alone (mic+camera clear) [{rem.id}]"

    key = ConsentKey(bystander_id=bystander.consent_id,
                     content_type=demo.REMINDER_CONTENT_TYPE)
    if consent_store is not None:
        print(f"[info-status] Checking my memory for the owner's saved preference "
              f"about {bystander.raw_id}...", flush=True)
        cached = consent_store.get(key)
        if cached is True:
            print(f"[info-status] The owner has already allowed disclosure in front "
                  f"of {bystander.raw_id} - reusing that saved YES; no need to ask "
                  "again.", flush=True)
            print(f"[fusion] {rem.id}: remembered YES for {key.bystander_id} -> "
                  "disclose.", flush=True)
            log.info("reusing stored YES for %s (%s)", key.bystander_id, rem.id,
                     extra={"event": "consent_cache_hit"})
            demo.deliver_reminder_spoken(text)
            telemetry.stage("consent", "complete", "Remembered Yes reused; watch prompt skipped.")
            telemetry.stage("memory", "complete", "Existing Yes retained in consent memory.")
            telemetry.stage("delivery", "complete", "Reminder spoken aloud using remembered consent.")
            telemetry.emit("outcome", outcome="spoken", detail="Remembered Yes")
            return (f"reminder disclosed, bystander {key.bystander_id} "
                    f"(remembered YES) [{rem.id}]")
        if cached is False:
            print(f"[info-status] The owner previously chose NOT to disclose in "
                  f"front of {bystander.raw_id} - reusing that saved NO; sending it "
                  "privately to the watch instead.", flush=True)
            print(f"[fusion] {rem.id}: remembered NO for {key.bystander_id} -> "
                  "private note.", flush=True)
            log.info("reusing stored NO for %s (%s)", key.bystander_id, rem.id,
                     extra={"event": "consent_cache_hit"})
            watch.notify(private)
            demo.behavior_withhold()
            telemetry.stage("consent", "complete", "Remembered No reused; watch prompt skipped.")
            telemetry.stage("memory", "complete", "Existing No retained in consent memory.")
            telemetry.stage("delivery", "complete", "Reminder delivered privately to the wrist.")
            telemetry.emit("outcome", outcome="private", detail="Remembered No")
            return (f"reminder withheld -> private, bystander {key.bystander_id} "
                    f"(remembered NO) [{rem.id}]")
        print(f"[info-status] I have no saved preference for {bystander.raw_id} yet "
              "- I will ask the owner.", flush=True)
    else:
        print("[info-status] Re-ask policy: I ask the owner every time and never "
              "save the answer.", flush=True)

    print("[info-status] Asking the owner on the watch: may I say this reminder out "
          "loud in front of this person?", flush=True)
    print(f"[fusion] {rem.id}: bystander {key.bystander_id} present ({bystander.found_by}) "
          "and the reminder is due; asking on the watch for consent...", flush=True)
    telemetry.stage("consent", "active", "Waiting for a private Yes/No response on the watch.")
    log.info("asking watch for consent (%s, bystander %s)", rem.id, key.bystander_id,
             extra={"event": "consent_asked"})
    ans = watch.ask_consent(demo.PROMPT_MESSAGE, timeout=demo.CONSENT_TIMEOUT_S)
    if ans is None:
        # A non-answer is never stored (a non-decision); safe non-disclosing default.
        print("[info-status] No answer from the watch - to stay safe I will NOT say "
              "it aloud; sending it privately. (A non-answer is not saved.)",
              flush=True)
        print(f"[fusion] {rem.id}: no watch answer -> private note (not stored).",
              flush=True)
        log.info("no watch answer for %s", rem.id, extra={"event": "consent_timeout"})
        watch.notify(private)
        demo.behavior_withhold()
        telemetry.stage("consent", "warning", "No watch answer; privacy-safe default applied.")
        telemetry.stage("memory", "skipped", "A non-answer is never stored.")
        telemetry.stage("delivery", "complete", "Reminder delivered privately to the wrist.")
        telemetry.emit("outcome", outcome="private", detail="No watch answer")
        return f"reminder no-reply -> private, bystander {key.bystander_id} [{rem.id}]"
    log.info("watch answered %s for %s (bystander %s)", "YES" if ans else "NO",
             rem.id, key.bystander_id, extra={"event": "consent_answer"})
    if consent_store is not None:
        print(f"[info-status] Saving the owner's answer about {bystander.raw_id} so "
              "I do not have to ask again next time.", flush=True)
        consent_store.put(key, ans)
        telemetry.stage("memory", "complete", f"Explicit {'Yes' if ans else 'No'} stored for {bystander.raw_id}.")
    else:
        telemetry.stage("memory", "skipped", "Re-ask policy stores no decision.")
    if ans:
        print("[info-status] The owner said YES - saying the reminder out loud.",
              flush=True)
        print(f"[fusion] {rem.id}: watch said YES for {key.bystander_id} -> disclose.",
              flush=True)
        demo.deliver_reminder_spoken(text)
        telemetry.stage("consent", "complete", "Owner answered Yes on the watch.")
        telemetry.stage("delivery", "complete", "Sensitive reminder spoken aloud with consent.")
        telemetry.emit("outcome", outcome="spoken", detail="Watch answered Yes")
        return f"reminder asked YES, bystander {key.bystander_id} [{rem.id}]"
    print("[info-status] The owner said NO - sending the reminder privately to the "
          "watch and greeting neutrally.", flush=True)
    print(f"[fusion] {rem.id}: watch said NO for {key.bystander_id} -> private note.",
          flush=True)
    watch.notify(private)
    demo.behavior_withhold()
    telemetry.stage("consent", "complete", "Owner answered No on the watch.")
    telemetry.stage("delivery", "complete", "Reminder delivered privately to the wrist.")
    telemetry.emit("outcome", outcome="private", detail="Watch answered No")
    return f"reminder asked NO, bystander {key.bystander_id} [{rem.id}]"


@logcall
def monitor_and_deliver(
    rem: Reminder,
    remind_at: datetime.datetime,
    watch: BangleClient,
    consent_store: ConsentStore | None,
    voice_identifier: VoiceIdentifier,
    voice_db: FaceDB,
    owner_voice: OwnerStore,
    face_identifier: FaceIdentifier | None,
    face_db: FaceDB | None,
    owner_face: OwnerStore | None,
    *,
    record_s: float | None = None,
    poll_s: float = vr.DEFAULT_POLL_S,
    camera_fail_safe: bool = False,
) -> str | None:
    """One sensitive reminder, end to end: sense by priority, then decide.

    Phase 1 senses who is present (mic across the window; camera only if the mic
    heard nobody). Phase 2 - deliberately deferred to the DUE TIME, so the watch
    buzzes when the reminder is actually due rather than minutes early - reveals,
    reuses a remembered answer, or asks.

    Returns a status string, or ``None`` to hold the reminder (owner absent).
    """

    bystander, conclusive = sense_presence(
        rem, remind_at, voice_identifier, voice_db, owner_voice,
        face_identifier, face_db, owner_face,
        record_s=record_s, poll_s=poll_s,
    )
    # Idle (both sensors off) until the reminder is actually due; a no-op in
    # legacy mode, where the mic window itself ends at the due time.
    vr.wait_until(remind_at, poll_s)
    return decide_and_deliver(rem, bystander, watch, consent_store,
                              conclusive=conclusive, fail_safe=camera_fail_safe)


@logcall
def deliver_due_reminder(
    rem: Reminder,
    watch: BangleClient,
    consent_store: ConsentStore | None,
    voice_identifier: VoiceIdentifier,
    voice_db: FaceDB,
    owner_voice: OwnerStore,
    face_identifier: FaceIdentifier | None,
    face_db: FaceDB | None,
    owner_face: OwnerStore | None,
    *,
    poll_s: float = vr.DEFAULT_POLL_S,
    record_s: float | None = None,
    camera_fail_safe: bool = False,
) -> str | None:
    """One approaching reminder, end to end: sensitivity -> presence gate -> deliver.

    The per-reminder half of the run loop, factored out of :func:`run_config` so
    it can be exercised without the infinite loop (and without hardware, when the
    collaborators are fakes). Returns a status string on a terminal outcome, or
    ``None`` to HOLD the reminder. Exceptions propagate; the caller owns the
    bounded-retry policy.
    """

    remind_at = rem.remind_at_dt

    # AI sensitivity check: it decides HOW this reminder is delivered.
    # Non-sensitive (an errand) -> speak it at its time, no presence check
    # and no consent. Sensitive (health/finance/personal) -> run the fused
    # presence pipeline and gate on consent.
    sensitive, sens_note = vr.sensitivity_for(rem)
    print(f"[reminder] {rem.id}: sensitivity = "
          f"{'SENSITIVE' if sensitive else 'NON-SENSITIVE'} ({sens_note}).",
          flush=True)
    telemetry.stage(
        "sensitivity", "complete",
        f"{'Sensitive' if sensitive else 'Non-sensitive'} ({sens_note}).",
        sensitive=sensitive,
    )
    print("[info-status] " + (
        "This reminder is SENSITIVE - I must check who is around before "
        "saying it out loud." if sensitive else
        "This reminder is NOT sensitive - it is safe to say out loud even "
        "if someone else is nearby."), flush=True)

    # Is the owner present? BLE link up == owner in ~same room. A reminder
    # is for the owner, so hold it until they are back in range rather than
    # opening a sensor on an empty room.
    print("[info-status] Checking if the owner is in the room "
          "(via the watch's Bluetooth link)...", flush=True)
    telemetry.stage("owner", "active", "Checking the watch Bluetooth owner-presence signal.")
    if not watch.is_connected():
        print("[info-status] The owner is not in the room yet - I will hold "
              "the reminder until they are back.", flush=True)
        print("[reminder] owner not present (watch offline). Holding the "
              "reminder until the owner is back in range...", flush=True)
        telemetry.stage("owner", "warning", "Watch offline; reminder held and sensors remain off.")
        return None
    print("[info-status] The owner is in the room.", flush=True)
    telemetry.stage("owner", "complete", "Watch connected; owner presence confirmed.")

    if not sensitive:
        # Non-sensitive: nothing to protect -> speak it at its scheduled
        # time. Neither sensor opens. We still wait out the window so an
        # errand isn't blurted minutes early.
        vr.wait_until(remind_at, poll_s)
        if not watch.is_connected():
            # Owner left before the due time -> hold, same as the
            # sensitive path, rather than talking to an empty room.
            print(f"[reminder] {rem.id}: owner left before delivery; "
                  "holding until back in range.", flush=True)
            return None
        print("[info-status] Not sensitive - skipping the who-is-"
              "around check and disclosing to the owner now.",
              flush=True)
        print(f"[reminder] {rem.id}: non-sensitive -> speaking "
              "normally (no consent needed; sensors stayed off).",
              flush=True)
        demo.deliver_reminder_spoken(rem.text)
        for step in ("microphone", "camera", "identity", "consent", "memory"):
            telemetry.stage(step, "skipped", "Bypassed for non-sensitive content.")
        telemetry.stage("delivery", "complete", "Non-sensitive reminder spoken normally.")
        telemetry.emit("outcome", outcome="spoken", detail="Non-sensitive reminder")
        return f"reminder delivered, non-sensitive [{rem.id}]"

    print("[info-status] Sensitive - I will check whether the owner "
          "is alone: first by listening, then by looking.", flush=True)
    return monitor_and_deliver(
        rem, remind_at, watch, consent_store, voice_identifier,
        voice_db, owner_voice, face_identifier, face_db, owner_face,
        record_s=record_s, poll_s=poll_s, camera_fail_safe=camera_fail_safe,
    )


@logcall
def run(remember: bool) -> None:
    """CLI entry: parse the legacy flags, then run the fused reminder loop.

    ``remember=True``  -> the cache-memory policy: a bystander's Yes/No is stored
                          and reused, so the same person is never re-asked.
    ``remember=False`` -> the re-consent policy: the watch is asked EVERY time a
                          bystander is present; no decision is ever stored.
    Both are exposed as thin entry points (``robot.apps.fusion_remember`` /
    ``robot.apps.fusion_reask``); this is the shared engine behind them. The
    unified ``robot.apps.reminder_app`` skips this parser and calls
    :func:`run_config` directly with its own configuration.
    """

    setup_logging(run_name="fusion_reminder")
    ap = argparse.ArgumentParser(
        description="Fused reminder delivery: mic first, camera as a double-check "
                    "(both sensors stay off until a sensitive reminder is due)."
    )
    ap.add_argument("--poll", type=float, default=vr.DEFAULT_POLL_S,
                    help=f"clock-check interval while idle-waiting "
                         f"(default {vr.DEFAULT_POLL_S})")
    ap.add_argument("--lead", type=float, default=vr.DEFAULT_LEAD_S,
                    help=f"how long before a reminder's time the pipeline wakes up "
                         f"and starts listening, in seconds (default "
                         f"{vr.DEFAULT_LEAD_S} = 5 min)")
    ap.add_argument("--gate", type=float, default=vr.DEFAULT_RMS_GATE,
                    help=f"RMS gate for the SUSTAINED-speech test; raise to ignore "
                         f"louder background media, lower to catch a quieter/farther "
                         f"bystander (default {vr.DEFAULT_RMS_GATE})")
    ap.add_argument("--min-voiced", type=float, default=vr.DEFAULT_VOICED_FRACTION_MIN,
                    help=f"fraction of blocks over --gate needed for the sustained "
                         f"test (default {vr.DEFAULT_VOICED_FRACTION_MIN})")
    ap.add_argument("--peak", type=float, default=vr.DEFAULT_PEAK_RMS,
                    help=f"RMS for the BURSTY-speech test; >= {vr.PEAK_MIN_BLOCKS} "
                         f"blocks above it count as a voice even if the average is "
                         f"low (default {vr.DEFAULT_PEAK_RMS})")
    ap.add_argument("--min-speech", type=float, default=MIN_SPEECH_S,
                    help=f"seconds of HUMAN SPEECH (neural VAD) needed before a "
                         f"sound counts as a person; raise it to ignore brief "
                         f"speech-like blips (default {MIN_SPEECH_S})")
    ap.add_argument("--no-camera", action="store_true",
                    help="skip the camera double-check entirely (mic-only ablation)")
    args = ap.parse_args()

    # Legacy semantics preserved: ONE --lead is both the wake-up lead and the
    # recording window (record_s=None -> record right up to the due time), and an
    # inconclusive camera keeps its documented fail-open (fall back to the mic
    # result) so the study conditions behave exactly as before. The unified app
    # runs this same engine with camera_fail_safe=True instead.
    run_config(FusionReminderConfig(
        remember=remember,
        poll_s=args.poll,
        lead_s=args.lead,
        record_s=None,
        gate=args.gate,
        min_voiced=args.min_voiced,
        peak=args.peak,
        min_speech=args.min_speech,
        no_camera=args.no_camera,
        camera_fail_safe=False,
    ))


@logcall
def run_config(cfg: FusionReminderConfig) -> None:
    """Run the fused (mic-then-camera) reminder loop from a config object."""

    # Clamp to sane values so a stray non-positive value can't turn the idle
    # sleeps into a busy-wait.
    poll = max(0.1, cfg.poll_s)
    lead = max(0.0, cfg.lead_s)
    record_s = None if cfg.record_s is None else max(0.0, cfg.record_s)

    # The mic detector thresholds live in the voice engine; set them there so
    # record_until/analyse_presence use the values this run was started with.
    vr.RMS_GATE = cfg.gate
    vr.VOICED_FRACTION_MIN = max(0.0, cfg.min_voiced)
    vr.PEAK_RMS = cfg.peak

    vr.init_ohbot()
    print(f"[startup] sound detection (gate 1): a sample counts as SOUND if >= "
          f"{vr.VOICED_FRACTION_MIN:.0%} of blocks exceed the gate {vr.RMS_GATE:.3f} "
          f"(sustained) OR >= {vr.PEAK_MIN_BLOCKS} blocks exceed {vr.PEAK_RMS:.3f} "
          f"(bursty/distant). Tune with --gate / --min-voiced / --peak.", flush=True)
    # Build the speech gate now so a missing model is reported at startup rather
    # than mid-delivery, and so the first reminder doesn't pay the load.
    detector = get_speech_detector(min_speech_s=max(0.0, cfg.min_speech))
    print(f"[startup] speech detection (gate 2): {detector.backend} - a sound only "
          f"counts as a PERSON if it contains >= {detector.min_speech_s:.1f}s of "
          f"human speech. Appliances (grinder/fan/vacuum) are rejected here."
          if detector.enabled else
          "[startup] speech detection (gate 2): DISABLED - loudness alone decides, "
          "so appliances can be mistaken for people.", flush=True)

    # REMEMBER mode keeps a persistent consent cache; RE-ASK mode keeps none.
    consent_store = ConsentStore(FUSION_CONSENT_CACHE_PATH) if cfg.remember else None
    policy = ("REMEMBER (reuse a bystander's stored Yes/No)" if cfg.remember
              else "RE-ASK (ask the watch every time)")
    print(f"[startup] consent policy: {policy}.", flush=True)
    if consent_store is not None:
        print(f"[cache] loaded {len(consent_store.dump())} bystander record(s) from "
              f"{FUSION_CONSENT_CACHE_PATH}", flush=True)

    # --- sensor 1: voice. Models + galleries load now; the mic opens only when a
    # sensitive reminder is due.
    print("[startup] loading speaker encoder (first load takes a moment)...",
          flush=True)
    voice_identifier = VoiceIdentifier()
    voice_db = FaceDB(VOICE_DB_PATH, match_threshold=VOICE_SAME_SPEAKER)
    owner_voice = OwnerStore(OWNER_VOICE_PATH)
    if not owner_voice.has_owner():
        raise SystemExit(
            "[startup] No voice owner enrolled. Run this first:\n"
            "    python -m robot.apps.enroll_voice"
        )
    # Pin a valid input device now, but do NOT open a stream - the mic stays off
    # until record_until() is called on a due reminder.
    sd.default.device = (pick_input_device(), sd.default.device[1])

    # --- sensor 2: face. Weights load now so the double-check isn't slowed by a
    # download; the camera device itself stays CLOSED until a check needs it.
    face_identifier: FaceIdentifier | None = None
    face_db: FaceDB | None = None
    owner_face: OwnerStore | None = None
    if cfg.no_camera:
        print("[startup] no-camera mode: the camera double-check is disabled; this "
              "run is mic-only.", flush=True)
    else:
        print("[startup] preparing face detector + recogniser (YuNet + SFace)...",
              flush=True)
        yunet_path, sface_path = ensure_models()
        face_identifier = FaceIdentifier(yunet_path, sface_path)
        face_db = FaceDB(FACE_DB_PATH, match_threshold=SFACE_COSINE_SAME_PERSON)
        owner_face = OwnerStore(OWNER_FACE_PATH)
        if not owner_face.has_owner():
            raise SystemExit(
                "[startup] No face owner enrolled, and the camera double-check "
                "needs one to tell the owner from a bystander. Run:\n"
                "    python -m robot.apps.enroll_face\n"
                "or start with --no-camera to run mic-only."
            )
        print(f"[startup] camera stays CLOSED until a check needs it "
              f"(face gallery: {face_db.count()} known person(s)).", flush=True)
        if _preview_enabled():
            print(f"[startup] when it does open, a preview window "
                  f"('{CAMERA_PREVIEW_WINDOW}') shows what it sees and closes "
                  "again with the device - so the window is on screen for "
                  "exactly the seconds the camera is recording. Set "
                  "CAMERA_PREVIEW=0 to run without it.", flush=True)

    print(f"[startup] sensor priority: "
          f"{' -> '.join(SENSOR_PRIORITY if not cfg.no_camera else (MODALITY_MIC,))}"
          " (a later sensor runs only if the earlier one found nobody).", flush=True)
    if cfg.camera_fail_safe:
        print("[startup] fail-safe mode: an inconclusive camera check withholds a "
              "sensitive reminder (private note to the wrist) instead of revealing "
              "it.", flush=True)

    print("[startup] connecting to the watch (owner-presence + consent link)...",
          flush=True)
    watch = BangleClient()
    if not watch.start():
        print("[ble] watch not found yet. Reminders need it to confirm the owner "
              "is present and to ask consent - the BLE link keeps rescanning in "
              "the background and reminders are held until it is up.", flush=True)

    pending = ReminderStore(REMINDERS_PATH).pending()
    if cfg.target_reminder_id:
        pending = [r for r in pending if r.id == cfg.target_reminder_id]
    if not pending:
        print("[reminders] none pending. Add one with add_reminder.py.", flush=True)
    else:
        window_note = (
            f"wakes the pipeline ~{int(lead)}s (={int(lead / 60)} min) early"
            if record_s is None else
            f"wakes the pipeline {int(lead)}s (={int(lead / 60)} min) early and "
            f"records the mic for {int(record_s)}s (={int(record_s / 60)} min)"
        )
        print(f"[reminders] {len(pending)} pending; next due {pending[0].remind_at} "
              f"({pending[0].text!r}). A sensitive reminder {window_note}; mic and "
              "camera stay OFF until then.", flush=True)
    print("[running] waiting for reminder times. Press Ctrl-C to quit.", flush=True)

    last_heartbeat = time.monotonic()
    delivery_errors: dict[str, int] = {}   # rem.id -> consecutive failed attempts
    try:
        while True:
            reminder_store = ReminderStore(REMINDERS_PATH)  # re-read: new + delivered
            # Fire `lead` seconds early: a reminder counts as due once we are
            # within the lead window of its scheduled time, so the pipeline wakes
            # up ahead of the due time rather than exactly at it.
            due = reminder_store.due(
                datetime.datetime.now() + datetime.timedelta(seconds=lead)
            )
            if cfg.target_reminder_id:
                due = [r for r in due if r.id == cfg.target_reminder_id]

            if not due:
                now = time.monotonic()
                if now - last_heartbeat >= vr.HEARTBEAT_S:
                    pend = reminder_store.pending()
                    if cfg.target_reminder_id:
                        pend = [r for r in pend if r.id == cfg.target_reminder_id]
                    nxt = f"next due {pend[0].remind_at} ({pend[0].text!r})" if pend \
                        else "none pending"
                    print("[info-status] Looking for reminders that are due...",
                          flush=True)
                    print(f"[waiting] {nxt}; mic off, camera closed.", flush=True)
                    last_heartbeat = now
                time.sleep(poll)
                continue

            rem = due[0]
            remind_at = rem.remind_at_dt
            print(f"\n[info-status] Reminder found: {rem.text!r} "
                  f"(scheduled for {rem.remind_at}).", flush=True)
            to_due = (remind_at - datetime.datetime.now()).total_seconds()
            print(f"[reminder] {rem.id} approaching (scheduled {rem.remind_at}, "
                  f"~{int(max(to_due, 0))}s until due): {rem.text!r}", flush=True)
            log.info("reminder %s due (%r)", rem.id, rem.text,
                     extra={"event": "reminder_due"})

            try:
                # The whole per-reminder path (sensitivity -> presence gate ->
                # sensing -> consent -> delivery). None -> HOLD (owner away).
                status = deliver_due_reminder(
                    rem, watch, consent_store, voice_identifier, voice_db,
                    owner_voice, face_identifier, face_db, owner_face,
                    poll_s=poll, record_s=record_s,
                    camera_fail_safe=cfg.camera_fail_safe,
                )
            except Exception:
                # Transient failure: DON'T mark delivered - leave it pending and
                # retry, capped so a permanently broken reminder can't loop forever.
                traceback.print_exc()
                delivery_errors[rem.id] = delivery_errors.get(rem.id, 0) + 1
                if delivery_errors[rem.id] >= vr.MAX_DELIVERY_ATTEMPTS:
                    print(f"[reminder] {rem.id}: failed {delivery_errors[rem.id]} "
                          "times; giving up. Sending it privately to the watch "
                          "(best-effort) so it is not lost silently.", flush=True)
                    # Never disclose aloud on a failure path; a best-effort
                    # private note is the only channel that cannot leak.
                    watch.notify(demo.REMINDER_PRIVATE_TEMPLATE.format(text=rem.text))
                    reminder_store.mark_delivered(rem.id)
                else:
                    print(f"[reminder] {rem.id}: delivery error "
                          f"({delivery_errors[rem.id]}/{vr.MAX_DELIVERY_ATTEMPTS}); "
                          "leaving it pending to retry.", flush=True)
                    time.sleep(max(poll, 3.0))
                last_heartbeat = 0.0
                continue

            if status is None:
                # Held (owner not present) -> keep it pending and retry after a
                # short pause, when the owner may be back in range. Any presence
                # result from the abandoned attempt is discarded - the retry
                # senses afresh.
                time.sleep(max(poll, 3.0))
                last_heartbeat = 0.0
                continue

            # Delivered successfully -> mark it so it fires exactly once.
            print(f"[reminder] {status}", flush=True)
            reminder_store.mark_delivered(rem.id)
            last_heartbeat = 0.0  # force a fresh status line next wait
    except KeyboardInterrupt:
        print("\n[shutdown] interrupted.", file=sys.stderr)
    finally:
        demo.shutting_down.set()
        watch.close()
        vr.close_ohbot()
