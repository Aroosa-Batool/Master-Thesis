"""Shared voice-modality reminder engine (mic presence + watch consent).

Not run directly - it is the engine behind the two voice entry points, which
differ only in whether a bystander's consent decision is remembered:
  - ``robot.apps.mic_remember`` -> ``run(remember=True)``  (cache-memory policy)
  - ``robot.apps.mic_reask``    -> ``run(remember=False)`` (re-consent policy)

The microphone stays OFF until a reminder is actually due. Per reminder the
pipeline is:

  1. a reminder has a due time (e.g. 18:42);
  2. shortly before that time (a configurable lead, ~1 min) - detected by
     polling the clock, no audio -
  3. an AI sensitivity classifier (sensitivity.py) decides HOW to deliver it:
       - non-sensitive (an errand, "buy milk") -> just speak it, no presence
         check and no consent; the mic never opens. Done.
       - sensitive (health/finance/personal, "doctor's appointment") -> run the
         presence-gated consent flow below.
  4. confirm the owner is present  -> the watch's BLE link is up (~same room);
  5. RECORD a window (default 5 min ending at the reminder's time): the mic runs
     CONTINUOUSLY the whole time - no on/off gaps - and the recording is analysed
     once, afterwards. Any non-owner HUMAN VOICE heard anywhere in the window is
     REMEMBERED, so it does not matter whether they speak at the start or the end.
     "Human voice" is enforced by a neural VAD (``robot.perception.speech_vad``)
     on top of the energy gate: a loud appliance is not a person, and without that
     second gate anything loud that was not the owner became a bystander.
     The window only detects who is present; it does NOT prompt yet;
  6. at the DUE TIME, no bystander was heard -> owner alone -> disclose aloud;
  7. at the DUE TIME, a bystander was heard -> only NOW ask/decide on the watch.
     In REMEMBER mode a bystander with a stored Yes/No is reused (unknown -> asked
     once and stored); in RE-ASK mode the watch is asked EVERY time. Yes -> speak
     aloud; No/no-reply -> deliver privately to the wrist. The watch prompt appears
     when the reminder is due, not minutes early.

The sensitivity label is normally computed once when the reminder is added
(add_reminder.py) and stored on the reminder; a reminder saved before the
classifier existed is classified live here instead.

Voice-only caveat: a bystander who is present but stays completely silent for the
whole window cannot be heard, so is treated as absent - the case this serves is a
bystander who speaks at some point (the camera pipeline covers silent presence,
and ``robot.core.fusion_reminder`` chains the two).

Presence sensing and the consent timing live in :func:`monitor_and_deliver`,
while the disclosure/withhold speech and the speaker re-identification come from
the shared support module ``robot.core.robot_io`` (``deliver_reminder_spoken``,
``behavior_withhold``, ``identify_bystander_averaged``).

The watch is required: it is both the owner-presence signal (BLE in range) and
the consent channel. The mic is opened only in :func:`record_until`.

Run (via the thin app wrappers):
    python -m robot.apps.mic_remember                       # cache-memory policy
    python -m robot.apps.mic_reask                          # re-consent policy
    NO_OHBOT=1 python -m robot.apps.mic_remember            # OS voice, no robot
    python -m robot.apps.mic_reask --lead 120 --gate 0.02

The unified ``robot.apps.reminder_app`` drives this same engine programmatically
via :class:`VoiceReminderConfig` / :func:`run_config`, splitting the single
``--lead`` into a wake-up lead and an explicit recording duration (by default
wake at T-7 min, record T-7 min -> T-2 min, deliver at T).
"""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
import time
from dataclasses import dataclass

import numpy as np

try:
    import sounddevice as sd
except (ModuleNotFoundError, OSError) as exc:
    raise SystemExit(
        "Missing dependency: install with `pip install sounddevice` "
        "(needs the PortAudio library; on Linux: `apt install libportaudio2`)."
    ) from exc

from robot.perception.audio_device import pick_input_device
from robot.perception.face_db import FaceDB
from robot.core.owner import OwnerStore
from robot.core.policy import BangleClient, ConsentKey, ConsentStore
from robot.core.reminders import Reminder, ReminderStore
from robot.perception.speech_vad import MIN_SPEECH_S, get_speech_detector
from robot.perception.voice_id import (
    VOICE_OWNER_THRESHOLD,
    VOICE_SAME_SPEAKER,
    VOICE_SR,
    VoiceIdentifier,
)

# The consent/disclosure policy, the reminder paths, and the Ohbot glue
# (shim + lock + NO_OHBOT) all live in robot_io (imported as `demo`); import it
# so every reminder is delivered by exactly the same consent policy.
import robot.core.robot_io as demo

from robot.core.logsetup import setup_logging, logcall, get_logger
from robot.core import presentation_telemetry as telemetry

log = get_logger(__name__)


# Inside the monitoring window the mic records CONTINUOUSLY (no on/off sampling),
# so a bystander who speaks at ANY instant is captured - nothing is missed in a
# gap. The whole window is then analysed once, at the due time. If the window has
# already collapsed (a reminder picked up at/after its time) we still record at
# least this many seconds so there is always a presence check before disclosing.
MIN_RECORD_S = 5.0
# How often to check the clock while idle-waiting (mic off, e.g. a non-sensitive
# reminder waiting for its time). NO audio captured meanwhile.
DEFAULT_POLL_S = 2.0
# Seconds between "still waiting" heartbeat lines (idle) and "still listening"
# progress lines (during a continuous recording).
HEARTBEAT_S = 30.0
LISTEN_HEARTBEAT_S = 20.0
# How much of the just-captured audio each progress line samples for its live
# readout - the dual voiced/peak detector run over the most recent few seconds,
# so the operator can see in real time whether a voice is actually being heard.
RECENT_WINDOW_S = 4.0

# A reminder whose delivery raises is left PENDING and retried (a transient mic /
# BLE / embedding hiccup must not silently lose it). This caps the retries so a
# permanently broken reminder can't wedge the loop forever - after this many
# failed attempts it is given up and marked delivered.
MAX_DELIVERY_ATTEMPTS = 3

# The MONITORING WINDOW: start recording for presence this many seconds before a
# reminder's scheduled time. The mic runs continuously across the whole window -
# the reminder need not have anyone speaking the entire time; a non-owner voice
# heard anywhere in it counts. Default 5 minutes. The reminder is spoken at its
# scheduled time (end of the window), not early.
DEFAULT_LEAD_S = 300.0

# GATE 1 of 2 - energy. This decides only "is there any SOUND here?", cheaply, so
# a quiet window can be dismissed without running a model. It is NOT a speech
# test: it fires on a grinder, a vacuum or a slammed door just as readily as on a
# voice, which is why gate 2 (the neural VAD in robot.perception.speech_vad) then
# asks whether any of that sound is a human voice. Both must pass before anyone is
# treated as present - see analyse_presence.
#
# A sample counts as SOUND if EITHER of two tests fires - this dual test is what
# lets us catch a DISTANT/quiet bystander (a person across the room, whose voice
# reaches the mic faint) as well as a close one:
#
#   1. SUSTAINED speech: at least VOICED_FRACTION_MIN of the 100 ms blocks have
#      RMS above RMS_GATE (close, steady talking crosses the gate most of the time);
#   2. BURSTY/distant speech: at least PEAK_MIN_BLOCKS blocks exceed the louder
#      PEAK_RMS. Far-field speech has a low AVERAGE (most blocks below the gate)
#      but real syllable peaks - a couple of clearly loud blocks means a genuine
#      voice, not room tone. Requiring >=2 (not 1) rejects a single click/thump.
#
# Measured against a real "roommate talking across the room" recording: the voice
# peaked at RMS ~0.033-0.060 with an average ~0.007, so the old single test
# (gate 0.03, 10% sustained) saw only 2-6% voiced and missed it; the peak test
# catches those 0.045-0.060 bursts. Tune with --gate / --min-voiced / --peak:
# raise them to ignore louder background media, lower to catch a fainter bystander.
DEFAULT_RMS_GATE = 0.02
RMS_GATE = DEFAULT_RMS_GATE          # overridden from --gate in main()
DEFAULT_VOICED_FRACTION_MIN = 0.06
VOICED_FRACTION_MIN = DEFAULT_VOICED_FRACTION_MIN   # overridden from --min-voiced
DEFAULT_PEAK_RMS = 0.035
PEAK_RMS = DEFAULT_PEAK_RMS          # overridden from --peak in main()
PEAK_MIN_BLOCKS = 2                  # >= this many loud blocks => a real voice


@dataclass
class VoiceReminderConfig:
    """Programmatic configuration for :func:`run_config`.

    The legacy CLI (``mic_remember`` / ``mic_reask`` with ``--lead``) wakes up
    ``lead_s`` before a reminder and records right up to the due time
    (``record_s=None``). The unified ``robot.apps.reminder_app`` separates the
    two concepts: wake at T - ``lead_s`` and record for exactly ``record_s``
    seconds (so with the defaults 420/300 the mic runs T-7min -> T-2min, the
    recording is analysed as soon as the mic closes, and delivery still happens
    at T).
    """

    remember: bool                   # True -> ConsentStore; False -> re-ask, no store
    poll_s: float = DEFAULT_POLL_S   # clock-check interval while idle-waiting
    lead_s: float = DEFAULT_LEAD_S   # wake/monitoring lead before a reminder's time
    record_s: float | None = None    # continuous-recording duration; None -> until due
    gate: float = DEFAULT_RMS_GATE
    min_voiced: float = DEFAULT_VOICED_FRACTION_MIN
    peak: float = DEFAULT_PEAK_RMS
    min_speech: float = MIN_SPEECH_S
    target_reminder_id: str | None = None


@logcall(level=logging.DEBUG)
def _plan_record_seconds(seconds_to_due: float, record_s: float | None) -> float:
    """How long the continuous mic window should actually record.

    ``record_s=None`` is the legacy behaviour: record right up to the due time.
    An explicit ``record_s`` records that long, clipped to the time actually
    left before the due time (a reminder picked up late must not still be
    recording after T). Either way at least ``MIN_RECORD_S`` is recorded so a
    sensitive reminder is never delivered without a presence check.
    """

    if record_s is None:
        return max(seconds_to_due, MIN_RECORD_S)
    return max(min(record_s, max(seconds_to_due, 0.0)), MIN_RECORD_S)


@logcall
def init_ohbot() -> None:
    """Bring up the shared Ohbot the same way the demo does (or skip it)."""

    if demo.NO_OHBOT:
        print("[startup] NO_OHBOT=1 set; the robot's lines use the OS voice.",
              flush=True)
        return
    print(
        f"[startup] initialising Ohbot (port hint='{demo.OHBOT_PORT_HINT}'). "
        "If this hangs, the robot is likely not plugged in - rerun with "
        "NO_OHBOT=1 to skip it.",
        flush=True,
    )
    bot = demo.load_ohbot()
    with demo.ohbot_lock:
        bot.setSynthesizer("espeak")
        bot.init(demo.OHBOT_PORT_HINT)
        bot.reset()
        bot.setVoice("-v en-gb+f3")
    print("[startup] Ohbot ready.", flush=True)


@logcall
def close_ohbot() -> None:
    if demo.NO_OHBOT:
        return
    bot = demo.load_ohbot()
    with demo.ohbot_lock:
        try:
            bot.reset()
        finally:
            bot.close()


@logcall
def record_until(
    remind_at: datetime.datetime, rem_id: str, record_s: float | None = None,
) -> np.ndarray:
    """Record the mic CONTINUOUSLY for the monitoring window; return the buffer.

    The microphone is on for the entire window - there are NO on/off gaps - so a
    bystander who speaks at any instant is captured; nothing is missed. The whole
    recording is analysed once, afterwards, as soon as the mic closes.

    ``record_s=None`` (the legacy ``--lead`` behaviour) records right up to
    ``remind_at`` and returns at the due time. An explicit ``record_s`` records
    that many seconds starting NOW and returns as soon as the recording is done -
    which may be well before ``remind_at`` (the unified app records T-7min ->
    T-2min and then idles, mic off, until T). A collapsed or past-due window (a
    reminder picked up at/after its time) still records ``MIN_RECORD_S`` so
    there is always some audio to check before disclosing.

    This is the ONLY place the microphone is opened.
    """

    record_s = _plan_record_seconds(_seconds_until(remind_at), record_s)
    ends_at = datetime.datetime.now() + datetime.timedelta(seconds=record_s)
    print(f"[monitor] {rem_id}: listening CONTINUOUSLY for {int(record_s)}s until "
          f"{ends_at:%H:%M:%S} (mic on the whole time; analysed when the mic "
          f"closes; reminder due {remind_at:%H:%M})...",
          flush=True)
    telemetry.stage("microphone", "active", "Listening for another human voice.")
    telemetry.sensor("microphone", True, duration_s=record_s)
    buf = sd.rec(int(record_s * VOICE_SR), samplerate=VOICE_SR,
                 channels=1, dtype="float32")
    # Wait out the window; recording proceeds in the background. Periodically show
    # a progress line with a live level readout so it is visible the mic is working.
    next_beat = LISTEN_HEARTBEAT_S
    while _seconds_until(ends_at) > 0:
        interval = 0.25 if telemetry.enabled() else 2.0
        time.sleep(min(interval, max(_seconds_until(ends_at), 0.0)))
        remaining = max(_seconds_until(ends_at), 0.0)
        elapsed = record_s - remaining
        filled = min(len(buf), int(elapsed * VOICE_SR))
        if telemetry.enabled() and filled:
            lo = max(0, filled - int(0.5 * VOICE_SR))
            telemetry.metric(
                "microphone_level",
                _rms(buf[lo:filled, 0]),
                progress=min(1.0, elapsed / max(record_s, 0.001)),
                remaining_s=remaining,
            )
        if elapsed >= next_beat:
            lo = max(0, filled - int(RECENT_WINDOW_S * VOICE_SR))   # last few s so far
            recent = buf[lo:filled, 0]
            # Run the SAME two gates live over the recent window so the line shows
            # whether a HUMAN VOICE is currently being heard - a loud appliance
            # reads as "noise", not "VOICE", which is what makes the live readout
            # trustworthy while tuning. (A real-time hint only; the binding
            # decision is still made over the WHOLE window at the due time.)
            frac, peak, mean, loud, hot = presence_metrics(recent)
            if hot:
                verdict = "SPEECH" if get_speech_detector().has_speech(recent) \
                    else "noise (not a voice)"
            else:
                verdict = "quiet"
            to_due = int(max(_seconds_until(remind_at), 0.0))
            print(f"[monitor] {rem_id}: listening... {int(elapsed)}s/{int(record_s)}s "
                  f"| last {int(RECENT_WINDOW_S)}s: RMS mean {mean:.3f} peak {peak:.3f}, "
                  f"{frac:.0%} voiced, {loud} loud>{PEAK_RMS:.3f} "
                  f"-> {verdict} | {to_due}s to due.", flush=True)
            log.info("progress %ds/%ds recent=%s mean=%.3f peak=%.3f voiced=%.0f%% "
                     "loud=%d to_due=%ds", int(elapsed), int(record_s),
                     verdict, mean, peak, frac * 100, loud, to_due,
                     extra={"event": "listening_progress"})
            next_beat += LISTEN_HEARTBEAT_S
    sd.wait()   # ensure the full record_s is captured (matters for past-due fallback)
    telemetry.sensor("microphone", False)
    telemetry.stage("microphone", "complete", "Listening finished; analysing temporary audio.")
    return buf[:, 0].copy()


@logcall(level=logging.DEBUG)
def _rms(block: np.ndarray) -> float:
    return float(np.sqrt(np.mean(block ** 2))) if len(block) else 0.0


@logcall(level=logging.DEBUG)
def presence_metrics(audio: np.ndarray) -> tuple[float, float, float, int, bool]:
    """Per-sample energy metrics + the dual voiced/peak presence decision.

    Returns ``(voiced_fraction, peak_rms, mean_rms, loud_blocks, detected)`` over
    100 ms blocks. ``detected`` is the OR of the two tests documented at the top of
    this file: SUSTAINED (fraction of blocks over RMS_GATE >= VOICED_FRACTION_MIN)
    OR BURSTY (>= PEAK_MIN_BLOCKS blocks over the louder PEAK_RMS) - the second is
    what catches a distant bystander whose average is low but whose syllables peak.
    """

    block = int(0.1 * VOICE_SR)
    if len(audio) < block:
        return 0.0, 0.0, 0.0, 0, False
    n = len(audio) // block
    rmss = [_rms(audio[i * block:(i + 1) * block]) for i in range(n)]
    voiced = sum(1 for r in rmss if r > RMS_GATE)
    loud = sum(1 for r in rmss if r > PEAK_RMS)
    frac = voiced / n
    detected = (frac >= VOICED_FRACTION_MIN) or (loud >= PEAK_MIN_BLOCKS)
    return frac, max(rmss), sum(rmss) / n, loud, detected


@logcall
def sensitivity_for(rem: Reminder) -> tuple[bool, str]:
    """Whether a due reminder is sensitive, plus a note on where that came from.

    Prefers the flag stored at add time by ``add_reminder.py``; if it is
    missing (a reminder saved before the classifier existed), classify the text
    live now - loading the text encoder lazily so the runner never pays for it
    unless a reminder actually needs it.
    """

    if rem.sensitive is not None:
        return rem.sensitive, "stored at add time"
    from robot.core.sensitivity import classify

    res = classify(rem.text)
    return res.sensitive, f"classified live - {res.backend}: {res.reason}"


@logcall
def analyse_presence(audio, voice_identifier, voice_db, owner_store, rem_id) -> str | None:
    """Analyse the whole recording: log energy metrics, then identify a bystander.

    Returns the bystander id - a persisted, re-identifiable voice print - if a
    non-owner voice was heard, else ``None`` (owner alone / silence / noise).

    TWO gates run, in order, and both must pass:

    1. ENERGY (cheap, first): the dual sustained-OR-bursty test over block RMS
       (see the constants at the top of this file). This only asks "is there
       anything here at all?" - the block-RMS peak/mean are logged so a
       non-detection is tunable (a peak near 0 => the mic isn't hearing the
       source, a device/level problem; a peak above the gate that still doesn't
       trigger => lower the thresholds).
    2. SPEECH (content-based): the neural VAD in ``robot.perception.speech_vad``
       asks "is any of this a HUMAN VOICE?". This gate is why a coffee grinder,
       fan or vacuum no longer becomes a bystander. Without it, energy alone let
       any loud sound through, and the identity stage below only ever asks "is
       this the owner?" - so a non-owner *noise* was filed as a person.

    Only the SPEECH samples are passed on to be embedded, so the voiceprint that
    reaches the gallery is built from a human voice and nothing else. The audio is
    embedded ONCE (inside identify_bystander_averaged) to avoid re-embedding a
    long recording.
    """

    frac, peak, mean, loud, detected = presence_metrics(audio)
    print(f"[monitor] {rem_id}: analysed {len(audio) / VOICE_SR:.0f}s - {frac:.0%} "
          f"voiced (gate {RMS_GATE:.3f}, need {VOICED_FRACTION_MIN:.0%}); {loud} loud "
          f"block(s) > {PEAK_RMS:.3f} (need {PEAK_MIN_BLOCKS}); RMS peak={peak:.3f} "
          f"mean={mean:.3f} -> {'SOUND' if detected else 'quiet'}.", flush=True)
    if not detected:
        telemetry.stage("identity", "skipped", "No audible bystander to identify.")
        return None

    # Gate 2: was any of that sound a human voice? Everything that is not speech
    # is dropped here and can never reach the speaker encoder or the gallery.
    detector = get_speech_detector()
    speech = detector.speech_only(audio)
    speech_s = len(speech) / VOICE_SR
    if detector.enabled:
        print(f"[monitor] {rem_id}: speech check ({detector.backend}) - "
              f"{speech_s:.1f}s of human speech in {len(audio) / VOICE_SR:.0f}s "
              f"(need {detector.min_speech_s:.1f}s).", flush=True)
    if not detector.has_speech(audio):
        print("[info-status] I heard a sound, but it was not a human voice - "
              "something like an appliance or background noise. That is not a "
              "person, so I will not treat it as one.", flush=True)
        print(f"[monitor] {rem_id}: sound present but NO human speech "
              f"({speech_s:.1f}s < {detector.min_speech_s:.1f}s) -> not a person.",
              flush=True)
        log.info("sound but no speech (%.2fs) for %s; not a bystander", speech_s,
                 rem_id, extra={"event": "noise_rejected"})
        telemetry.stage("identity", "skipped", "Sound rejected: no human speech detected.")
        return None

    bid, sim, is_new, owner_det, n_by = demo.identify_bystander_averaged(
        voice_identifier, voice_db, owner_store, speech
    )
    if owner_det:
        print(f"[monitor] {rem_id}:   owner voice heard and subtracted.", flush=True)
    if not bid:
        print(f"[monitor] {rem_id}:   only the owner was heard; no bystander.",
              flush=True)
        telemetry.stage("identity", "complete", "Only the enrolled owner's voice was heard.")
        return None
    print("[info-status] I heard someone else here with the owner.", flush=True)
    if is_new:
        print("[info-status] I have not heard this person before. I turned their "
              f"voice into a numeric embedding (a voiceprint) and gave them the "
              f"anonymous id {bid}. I do NOT keep their raw audio or any personal "
              "data - only the embedding.", flush=True)
    else:
        print(f"[info-status] I recognise this person as {bid}: their voiceprint "
              f"matches a stored one (cosine similarity {sim:.2f} >= threshold "
              f"{VOICE_SAME_SPEAKER:.2f}), so it is the same person as before.",
              flush=True)
    print(f"[monitor] {rem_id}: bystander {bid} present "
          f"({'NEW id' if is_new else 'matched existing'}, sim={sim:.2f}, {n_by} "
          "voiced window(s) averaged) - remembered; will decide / ask at the due "
          "time.", flush=True)
    log.info("bystander %s present (new=%s, sim=%.2f)", bid, is_new, sim,
             extra={"event": "bystander_detected"})
    telemetry.stage(
        "identity", "complete", f"Voice bystander resolved as {bid}.",
        identity=bid, modality="voice", similarity=sim, is_new=is_new,
    )
    return bid


@logcall(level=logging.DEBUG)
def _seconds_until(when: datetime.datetime) -> float:
    return (when - datetime.datetime.now()).total_seconds()


@logcall
def wait_until(when: datetime.datetime, poll: float) -> None:
    """Idle-sleep (mic off) until ``when``, in small steps so Ctrl-C stays live."""

    while True:
        left = _seconds_until(when)
        if left <= 0:
            return
        time.sleep(min(poll, left))


@logcall
def monitor_and_deliver(
    rem: Reminder,
    remind_at: datetime.datetime,
    watch: BangleClient,
    consent_store: ConsentStore | None,
    voice_identifier: VoiceIdentifier,
    voice_db: FaceDB,
    owner_store: OwnerStore,
    *,
    record_s: float | None = None,
    poll_s: float = DEFAULT_POLL_S,
) -> str | None:
    """Record who is present across the window, then decide/ask at the due time.

    From now until ``remind_at`` (the up-to-``--lead`` window, ~5 min) the mic
    records CONTINUOUSLY - no on/off gaps - so a bystander who speaks at any instant
    is captured; nothing is missed. The whole recording is then analysed once, at
    the due time: if a non-owner voice was heard the bystander is REMEMBERED. The
    consent prompt is deliberately deferred to the DUE TIME, so the watch buzzes
    when the reminder is actually due, not minutes early. At the due time: no
    bystander heard -> owner alone -> disclose; a REMEMBERED bystander reuses their
    stored Yes/No (no re-ask); an unknown bystander is asked on the watch then.

    Returns a HUD status string on delivery, or ``None`` to HOLD without delivering
    (the owner was not present at the moment of delivery) - the caller then leaves
    the reminder pending and retries when the owner is back in range.

    Guarantees / limitations:
    - A collapsed/past-due window still records ``MIN_RECORD_S`` and is analysed, so
      a sensitive reminder is never spoken without a presence check.
    - Continuous capture: unlike the earlier duty-cycled sampling, nothing is missed
      in a gap - the trade is that the mic is on for the whole window and a long
      recording takes a few seconds to embed at the due time.
    - Whole-window average: all non-owner voiced windows are averaged into ONE id,
      so two different simultaneous bystanders merge (fine for owner-plus-one).
    - Voice-only: a bystander who is present but silent the whole window cannot be
      heard, so is treated as absent (the camera pipeline covers silent presence).
    - 'Same person' reuse is voice-similarity based (VOICE_SAME_SPEAKER): if a
      re-match falls below threshold a new id is minted and consent is re-asked.
    """

    text = rem.text
    private = demo.REMINDER_PRIVATE_TEMPLATE.format(text=text)

    # Phase 1 - DETECT & REMEMBER: record the whole window continuously (mic on
    # the entire time), then analyse it once as soon as the mic closes. With
    # record_s=None (legacy) the recording ends at the due time; with an explicit
    # record_s it ends earlier (e.g. T-2min) and we idle, mic off, until T. No
    # consent is asked here - that is deferred to phase 2 (the due time).
    audio = record_until(remind_at, rem.id, record_s)
    bystander = analyse_presence(audio, voice_identifier, voice_db, owner_store, rem.id)
    # The raw recording is never retained: only the analysis result (a bystander
    # id, i.e. an embedding-backed gallery entry) survives past this point.
    del audio
    # Idle (mic off) until the reminder is actually due; a no-op in legacy mode,
    # where the recording itself ends at the due time.
    wait_until(remind_at, poll_s)

    # Phase 2 - it is now the due time. Decide and, only if needed, ask for consent.
    # Re-confirm the owner is still here at the instant of delivery: they may have
    # walked out during the (up to 5 min) window. If gone, HOLD (return None) so
    # the caller keeps the reminder pending rather than announcing it to an empty
    # room or over a bystander with the owner absent.
    if not watch.is_connected():
        print(f"[monitor] {rem.id}: owner not present at delivery time (left during "
              "the window) -> holding until they are back in range.", flush=True)
        log.info("owner left during window; holding %s", rem.id,
                 extra={"event": "owner_left"})
        return None

    # No bystander was ever heard -> owner is alone -> disclose.
    if bystander is None:
        print("[info-status] The owner is alone - no other voice was heard, so I "
              "can say the reminder out loud.", flush=True)
        print(f"[monitor] {rem.id}: no one heard across the window -> owner alone.",
              flush=True)
        log.info("no bystander across window; owner alone %s", rem.id,
                 extra={"event": "no_presence"})
        demo.deliver_reminder_spoken(text)
        telemetry.stage("consent", "skipped", "Owner is alone; no consent prompt needed.")
        telemetry.stage("memory", "skipped", "No consent decision was requested.")
        telemetry.stage("delivery", "complete", "Sensitive reminder spoken aloud to the owner.")
        telemetry.emit("outcome", outcome="spoken", detail="Owner alone")
        return f"reminder delivered, owner alone (window quiet) [{rem.id}]"

    # A bystander is present and the reminder is now due. In REMEMBER mode
    # (consent_store given) reuse a stored Yes/No if we have one; in RE-ASK mode
    # (consent_store is None) always ask the watch afresh - the bystander is still
    # recognised, but only for logging, never to skip the prompt.
    key = ConsentKey(bystander_id=bystander, content_type=demo.REMINDER_CONTENT_TYPE)
    if consent_store is not None:
        print(f"[info-status] Checking my memory for the owner's saved preference "
              f"about {bystander}...", flush=True)
        cached = consent_store.get(key)
        if cached is True:
            print(f"[info-status] The owner has already allowed disclosure in front "
                  f"of {bystander} - reusing that saved YES; no need to ask again.",
                  flush=True)
            log.info("reusing stored YES for bystander %s (%s)", bystander, rem.id,
                     extra={"event": "consent_cache_hit"})
            print(f"[monitor] {rem.id}: remembered YES for {bystander} -> disclose.",
                  flush=True)
            demo.deliver_reminder_spoken(text)
            telemetry.stage("consent", "complete", "Remembered Yes reused; watch prompt skipped.")
            telemetry.stage("memory", "complete", "Existing Yes retained in consent memory.")
            telemetry.stage("delivery", "complete", "Reminder spoken aloud using remembered consent.")
            telemetry.emit("outcome", outcome="spoken", detail="Remembered Yes")
            return f"reminder disclosed, bystander {bystander} (remembered YES) [{rem.id}]"
        if cached is False:
            print(f"[info-status] The owner previously chose NOT to disclose in "
                  f"front of {bystander} - reusing that saved NO; sending it "
                  "privately to the watch instead.", flush=True)
            log.info("reusing stored NO for bystander %s (%s)", bystander, rem.id,
                     extra={"event": "consent_cache_hit"})
            print(f"[monitor] {rem.id}: remembered NO for {bystander} -> private note.",
                  flush=True)
            watch.notify(private)
            demo.behavior_withhold()
            telemetry.stage("consent", "complete", "Remembered No reused; watch prompt skipped.")
            telemetry.stage("memory", "complete", "Existing No retained in consent memory.")
            telemetry.stage("delivery", "complete", "Reminder delivered privately to the wrist.")
            telemetry.emit("outcome", outcome="private", detail="Remembered No")
            return f"reminder withheld -> private, bystander {bystander} (remembered NO) [{rem.id}]"
        print(f"[info-status] I have no saved preference for {bystander} yet - I will "
              "ask the owner.", flush=True)
    else:
        print("[info-status] Re-ask policy: I ask the owner every time and never "
              "save the answer.", flush=True)

    # Ask the watch: the first time for this bystander (remember mode) or every
    # time (re-ask mode).
    remembered = " (remembered)" if consent_store is not None else ""
    print("[info-status] Asking the owner on the watch: may I say this reminder out "
          "loud in front of this person?", flush=True)
    print(f"[monitor] {rem.id}: bystander {bystander} present and reminder is due; "
          "asking on the watch for consent...", flush=True)
    telemetry.stage("consent", "active", "Waiting for a private Yes/No response on the watch.")
    log.info("asking watch for consent (%s, bystander %s)", rem.id, bystander,
             extra={"event": "consent_asked"})
    ans = watch.ask_consent(demo.PROMPT_MESSAGE, timeout=demo.CONSENT_TIMEOUT_S)
    if ans is None:
        # A non-answer is never stored (a non-decision); safe non-disclosing default.
        print("[info-status] No answer from the watch - to stay safe I will NOT say "
              "it aloud; sending it privately. (A non-answer is not saved.)",
              flush=True)
        print(f"[monitor] {rem.id}: no watch answer -> private note (not stored).",
              flush=True)
        log.info("no watch answer for %s", rem.id, extra={"event": "consent_timeout"})
        watch.notify(private)
        demo.behavior_withhold()
        telemetry.stage("consent", "warning", "No watch answer; privacy-safe default applied.")
        telemetry.stage("memory", "skipped", "A non-answer is never stored.")
        telemetry.stage("delivery", "complete", "Reminder delivered privately to the wrist.")
        telemetry.emit("outcome", outcome="private", detail="No watch answer")
        return f"reminder no-reply -> private, bystander {bystander} [{rem.id}]"
    log.info("watch answered %s for %s (bystander %s)", "YES" if ans else "NO",
             rem.id, bystander, extra={"event": "consent_answer"})
    if consent_store is not None:
        print(f"[info-status] Saving the owner's answer about {bystander} so I do "
              "not have to ask again next time.", flush=True)
        consent_store.put(key, ans)
        telemetry.stage("memory", "complete", f"Explicit {'Yes' if ans else 'No'} stored for {bystander}.")
    else:
        telemetry.stage("memory", "skipped", "Re-ask policy stores no decision.")
    if ans:
        print("[info-status] The owner said YES - saying the reminder out loud.",
              flush=True)
        print(f"[monitor] {rem.id}: watch said YES for {bystander}{remembered} -> "
              "disclose.", flush=True)
        demo.deliver_reminder_spoken(text)
        telemetry.stage("consent", "complete", "Owner answered Yes on the watch.")
        telemetry.stage("delivery", "complete", "Sensitive reminder spoken aloud with consent.")
        telemetry.emit("outcome", outcome="spoken", detail="Watch answered Yes")
        return f"reminder asked YES, bystander {bystander} [{rem.id}]"
    print("[info-status] The owner said NO - sending the reminder privately to the "
          "watch and greeting neutrally.", flush=True)
    print(f"[monitor] {rem.id}: watch said NO for {bystander}{remembered} -> "
          "private note.", flush=True)
    watch.notify(private)
    demo.behavior_withhold()
    telemetry.stage("consent", "complete", "Owner answered No on the watch.")
    telemetry.stage("delivery", "complete", "Reminder delivered privately to the wrist.")
    telemetry.emit("outcome", outcome="private", detail="Watch answered No")
    return f"reminder asked NO, bystander {bystander} [{rem.id}]"


@logcall
def deliver_due_reminder(
    rem: Reminder,
    watch: BangleClient,
    consent_store: ConsentStore | None,
    voice_identifier: VoiceIdentifier,
    voice_db: FaceDB,
    owner_store: OwnerStore,
    *,
    poll_s: float = DEFAULT_POLL_S,
    record_s: float | None = None,
) -> str | None:
    """One approaching reminder, end to end: sensitivity -> presence gate -> deliver.

    The per-reminder half of the run loop, factored out of :func:`run_config` so
    it can be exercised without the infinite loop (and without hardware, when the
    collaborators are fakes). Returns a status string on a terminal outcome
    (spoken or delivered privately), or ``None`` to HOLD the reminder - the
    caller leaves it pending and retries. Exceptions propagate; the caller owns
    the bounded-retry policy.
    """

    remind_at = rem.remind_at_dt

    # AI sensitivity check: it decides HOW this reminder is delivered.
    # Non-sensitive (an errand) -> speak it at its time, no presence check
    # and no consent. Sensitive (health/finance/personal) -> monitor the
    # pre-reminder window for a bystander and gate on consent.
    sensitive, sens_note = sensitivity_for(rem)
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
    # is for the owner, so we hold it (either path) until they are back in
    # range rather than announcing it to an empty room. Nothing (mic included)
    # is opened while the owner is away. Checked as the window opens; a brief
    # BLE flap mid-window is tolerated.
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
        # time. The mic never opens. We still wait out the window so an
        # errand isn't blurted minutes early.
        wait_until(remind_at, poll_s)
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
              "normally (no consent needed; mic stayed off).",
              flush=True)
        demo.deliver_reminder_spoken(rem.text)
        for step in ("microphone", "camera", "identity", "consent", "memory"):
            telemetry.stage(step, "skipped", "Bypassed for non-sensitive content.")
        telemetry.stage("delivery", "complete", "Non-sensitive reminder spoken normally.")
        telemetry.emit("outcome", outcome="spoken", detail="Non-sensitive reminder")
        return f"reminder delivered, non-sensitive [{rem.id}]"

    print("[info-status] Sensitive - listening to check whether the "
          "owner is alone or with someone else...", flush=True)
    # Sensitive: record the window continuously, remember any bystander,
    # then decide/ask at the due time. Returns None to HOLD (owner absent
    # at the moment of delivery).
    return monitor_and_deliver(
        rem, remind_at, watch, consent_store, voice_identifier,
        voice_db, owner_store, record_s=record_s, poll_s=poll_s,
    )


@logcall
def run(remember: bool) -> None:
    """CLI entry: parse the legacy flags, then run the voice reminder loop.

    ``remember=True``  -> the cache-memory policy: a bystander's Yes/No is stored
                          and reused, so the same person is never re-asked.
    ``remember=False`` -> the re-consent policy: the watch is asked EVERY time a
                          bystander is present; no decision is ever stored.
    Both are exposed as thin entry points (``robot.apps.mic_remember`` /
    ``robot.apps.mic_reask``); this is the shared engine behind them. The
    unified ``robot.apps.reminder_app`` skips this parser and calls
    :func:`run_config` directly with its own configuration.
    """

    setup_logging(run_name="voice_reminder")
    ap = argparse.ArgumentParser(
        description="Time-triggered reminder delivery (mic stays off until due)."
    )
    ap.add_argument("--poll", type=float, default=DEFAULT_POLL_S,
                    help=f"clock-check interval while idle-waiting "
                         f"(default {DEFAULT_POLL_S})")
    ap.add_argument("--lead", type=float, default=DEFAULT_LEAD_S,
                    help=f"length of the continuous-listening window before a "
                         f"reminder's time, in seconds (default {DEFAULT_LEAD_S} "
                         f"= 5 min); the mic records the whole window")
    ap.add_argument("--gate", type=float, default=DEFAULT_RMS_GATE,
                    help=f"RMS gate for the SUSTAINED-speech test; raise to ignore "
                         f"louder background media, lower to catch a quieter/farther "
                         f"bystander (default {DEFAULT_RMS_GATE})")
    ap.add_argument("--min-voiced", type=float, default=DEFAULT_VOICED_FRACTION_MIN,
                    help=f"fraction of blocks over --gate needed for the sustained "
                         f"test (default {DEFAULT_VOICED_FRACTION_MIN})")
    ap.add_argument("--peak", type=float, default=DEFAULT_PEAK_RMS,
                    help=f"RMS for the BURSTY-speech test; >= {PEAK_MIN_BLOCKS} blocks "
                         f"above it count as a voice even if the average is low "
                         f"(catches distant talking; default {DEFAULT_PEAK_RMS})")
    ap.add_argument("--min-speech", type=float, default=MIN_SPEECH_S,
                    help=f"seconds of HUMAN SPEECH (neural VAD) needed before a "
                         f"sound counts as a person; raise it to ignore brief "
                         f"speech-like blips (default {MIN_SPEECH_S})")
    args = ap.parse_args()

    # Legacy semantics: ONE --lead value is both the wake-up lead and the
    # recording window (record_s=None -> record right up to the due time).
    run_config(VoiceReminderConfig(
        remember=remember,
        poll_s=args.poll,
        lead_s=args.lead,
        record_s=None,
        gate=args.gate,
        min_voiced=args.min_voiced,
        peak=args.peak,
        min_speech=args.min_speech,
    ))


@logcall
def run_config(cfg: VoiceReminderConfig) -> None:
    """Run the voice reminder loop from a config object (no argv involved)."""

    # Clamp to sane values so a stray non-positive value can't turn the idle
    # sleeps into a busy-wait.
    poll = max(0.1, cfg.poll_s)
    lead = max(0.0, cfg.lead_s)
    record_s = None if cfg.record_s is None else max(0.0, cfg.record_s)

    global RMS_GATE, VOICED_FRACTION_MIN, PEAK_RMS
    RMS_GATE = cfg.gate
    VOICED_FRACTION_MIN = max(0.0, cfg.min_voiced)
    PEAK_RMS = cfg.peak

    init_ohbot()
    print(f"[startup] sound detection (gate 1): a sample counts as SOUND if >= "
          f"{VOICED_FRACTION_MIN:.0%} of blocks exceed the gate {RMS_GATE:.3f} "
          f"(sustained) OR >= {PEAK_MIN_BLOCKS} blocks exceed {PEAK_RMS:.3f} "
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
    consent_store = ConsentStore(demo.CACHE_PATH) if cfg.remember else None
    policy = ("REMEMBER (reuse a bystander's stored Yes/No)" if cfg.remember
              else "RE-ASK (ask the watch every time)")
    print(f"[startup] consent policy: {policy}.", flush=True)
    print("[startup] loading speaker encoder (first load takes a moment)...",
          flush=True)
    voice_identifier = VoiceIdentifier()
    voice_db = FaceDB(demo.VOICE_DB_PATH, match_threshold=VOICE_SAME_SPEAKER)
    owner_store = OwnerStore(demo.OWNER_VOICE_PATH)
    if not owner_store.has_owner():
        raise SystemExit(
            "[startup] No voice owner enrolled. Run this first:\n"
            "    python -m robot.apps.enroll_voice"
        )

    # Pin a valid input device now, but do NOT open a stream - the mic stays
    # off until record_until() is called on a due reminder.
    sd.default.device = (pick_input_device(), sd.default.device[1])

    print("[startup] connecting to the watch (owner-presence + consent link)...",
          flush=True)
    watch = BangleClient()
    if not watch.start():
        print("[ble] watch not found yet. Reminders need it to confirm the owner "
              "is present and to ask consent - the BLE link keeps rescanning in "
              "the background and reminders are held until it is up.", flush=True)

    pending = ReminderStore(demo.REMINDERS_PATH).pending()
    if cfg.target_reminder_id:
        pending = [r for r in pending if r.id == cfg.target_reminder_id]
    if not pending:
        print("[reminders] none pending. Add one with add_reminder.py.",
              flush=True)
    else:
        window_note = (
            f"the mic records CONTINUOUSLY for the ~{int(lead)}s "
            f"(={int(lead / 60)} min) before its time"
            if record_s is None else
            f"the mic opens {int(lead)}s (={int(lead / 60)} min) before its time "
            f"and records CONTINUOUSLY for {int(record_s)}s "
            f"(={int(record_s / 60)} min)"
        )
        print(f"[reminders] {len(pending)} pending; next due {pending[0].remind_at} "
              f"({pending[0].text!r}). For a sensitive reminder {window_note}; "
              f"mic stays OFF until then.", flush=True)
    print("[running] waiting for reminder times. Press Ctrl-C to quit.", flush=True)

    last_heartbeat = time.monotonic()
    delivery_errors: dict[str, int] = {}   # rem.id -> consecutive failed attempts
    try:
        while True:
            reminder_store = ReminderStore(demo.REMINDERS_PATH)  # re-read: new + delivered
            # Fire `lead` seconds early: a reminder counts as due once we are
            # within the lead window of its scheduled time, so monitoring starts
            # ahead of the due time rather than exactly at it.
            due = reminder_store.due(
                datetime.datetime.now() + datetime.timedelta(seconds=lead)
            )
            if cfg.target_reminder_id:
                due = [r for r in due if r.id == cfg.target_reminder_id]

            if not due:
                now = time.monotonic()
                if now - last_heartbeat >= HEARTBEAT_S:
                    pend = reminder_store.pending()
                    if cfg.target_reminder_id:
                        pend = [r for r in pend if r.id == cfg.target_reminder_id]
                    nxt = f"next due {pend[0].remind_at} ({pend[0].text!r})" if pend \
                        else "none pending"
                    print("[info-status] Looking for reminders that are due...",
                          flush=True)
                    print(f"[waiting] {nxt}; mic off.", flush=True)
                    last_heartbeat = now
                time.sleep(poll)
                continue

            rem = due[0]
            remind_at = rem.remind_at_dt
            print(f"\n[info-status] Reminder found: {rem.text!r} "
                  f"(scheduled for {rem.remind_at}).", flush=True)
            print(f"[reminder] {rem.id} approaching (scheduled {rem.remind_at}, "
                  f"~{int(max(_seconds_until(remind_at), 0))}s until due): "
                  f"{rem.text!r}", flush=True)
            log.info("reminder %s due (%r)", rem.id, rem.text,
                     extra={"event": "reminder_due"})

            try:
                # The whole per-reminder path (sensitivity -> presence gate ->
                # monitoring -> consent -> delivery). None -> HOLD (owner away).
                status = deliver_due_reminder(
                    rem, watch, consent_store, voice_identifier, voice_db,
                    owner_store, poll_s=poll, record_s=record_s,
                )
            except Exception:
                # Transient failure: DON'T mark delivered - leave it pending and
                # retry, capped so a permanently broken reminder can't loop forever.
                import traceback
                traceback.print_exc()
                delivery_errors[rem.id] = delivery_errors.get(rem.id, 0) + 1
                if delivery_errors[rem.id] >= MAX_DELIVERY_ATTEMPTS:
                    print(f"[reminder] {rem.id}: failed {delivery_errors[rem.id]} "
                          "times; giving up. Sending it privately to the watch "
                          "(best-effort) so it is not lost silently.", flush=True)
                    # Never disclose aloud on a failure path; a best-effort
                    # private note is the only channel that cannot leak.
                    watch.notify(demo.REMINDER_PRIVATE_TEMPLATE.format(text=rem.text))
                    reminder_store.mark_delivered(rem.id)
                else:
                    print(f"[reminder] {rem.id}: delivery error "
                          f"({delivery_errors[rem.id]}/{MAX_DELIVERY_ATTEMPTS}); "
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
        watch.close()
        close_ohbot()
