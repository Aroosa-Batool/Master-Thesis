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
     once, afterwards. Any non-owner voice heard anywhere in the window is
     REMEMBERED, so it does not matter whether they speak at the start or the end.
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
bystander who speaks at some point (the camera pipeline covers silent presence).

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
"""

from __future__ import annotations

import argparse
import datetime
import sys
import time

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

# A sample counts as "someone is speaking" if EITHER of two tests fires - this
# dual test is what lets us catch a DISTANT/quiet bystander (a person across the
# room, whose voice reaches the mic faint) as well as a close one:
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
    with demo.ohbot_lock:
        demo.ohbot.setSynthesizer("espeak")
        demo.ohbot.init(demo.OHBOT_PORT_HINT)
        demo.ohbot.reset()
        demo.ohbot.setVoice("-v en-gb+f3")
    print("[startup] Ohbot ready.", flush=True)


def close_ohbot() -> None:
    if demo.NO_OHBOT:
        return
    with demo.ohbot_lock:
        try:
            demo.ohbot.reset()
        finally:
            demo.ohbot.close()


def record_until(remind_at: datetime.datetime, rem_id: str) -> np.ndarray:
    """Record the mic CONTINUOUSLY until ``remind_at``; return the mono buffer.

    The microphone is on for the entire monitoring window - there are NO on/off
    gaps - so a bystander who speaks at any instant is captured; nothing is missed.
    The whole recording is analysed once, afterwards, at the due time. A collapsed
    or past-due window (a reminder picked up at/after its time) still records
    ``MIN_RECORD_S`` so there is always some audio to check before disclosing.

    Returns at (or, for the past-due fallback, just after) ``remind_at``. This is
    the ONLY place the microphone is opened.
    """

    record_s = max(_seconds_until(remind_at), MIN_RECORD_S)
    print(f"[monitor] {rem_id}: listening CONTINUOUSLY for {int(record_s)}s until "
          f"{remind_at:%H:%M} (mic on the whole time; analysed at the due time)...",
          flush=True)
    buf = sd.rec(int(record_s * VOICE_SR), samplerate=VOICE_SR,
                 channels=1, dtype="float32")
    # Wait out the window; recording proceeds in the background. Periodically show
    # a progress line with a live level readout so it is visible the mic is working.
    next_beat = LISTEN_HEARTBEAT_S
    while _seconds_until(remind_at) > 0:
        time.sleep(min(2.0, max(_seconds_until(remind_at), 0.0)))
        elapsed = record_s - max(_seconds_until(remind_at), 0.0)
        if elapsed >= next_beat:
            filled = min(len(buf), int(elapsed * VOICE_SR))
            lo = max(0, filled - int(2 * VOICE_SR))     # last ~2 s captured so far
            recent = buf[lo:filled, 0]
            print(f"[monitor] {rem_id}: listening... {int(elapsed)}s/{int(record_s)}s "
                  f"(recent RMS {_rms(recent):.3f}).", flush=True)
            next_beat += LISTEN_HEARTBEAT_S
    sd.wait()   # ensure the full record_s is captured (matters for past-due fallback)
    return buf[:, 0].copy()


def _rms(block: np.ndarray) -> float:
    return float(np.sqrt(np.mean(block ** 2))) if len(block) else 0.0


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


def analyse_presence(audio, voice_identifier, voice_db, owner_store, rem_id) -> str | None:
    """Analyse the whole recording: log energy metrics, then identify a bystander.

    Returns the bystander id - a persisted, re-identifiable voice print - if a
    non-owner voice was heard, else ``None`` (owner alone / silence). The dual
    sustained-OR-bursty energy test (see the constants at the top of this file)
    first decides whether there is any voice worth embedding; the block-RMS
    peak/mean are logged so a non-detection is tunable (a peak near 0 => the mic
    isn't hearing the source, a device/level problem; a peak above the gate that
    still doesn't trigger => lower the thresholds). The audio is embedded ONCE
    (inside identify_bystander_averaged) to avoid re-embedding a long recording.
    """

    frac, peak, mean, loud, detected = presence_metrics(audio)
    print(f"[monitor] {rem_id}: analysed {len(audio) / VOICE_SR:.0f}s - {frac:.0%} "
          f"voiced (gate {RMS_GATE:.3f}, need {VOICED_FRACTION_MIN:.0%}); {loud} loud "
          f"block(s) > {PEAK_RMS:.3f} (need {PEAK_MIN_BLOCKS}); RMS peak={peak:.3f} "
          f"mean={mean:.3f} -> {'VOICE' if detected else 'quiet'}.", flush=True)
    if not detected:
        return None
    bid, sim, is_new, owner_det, n_by = demo.identify_bystander_averaged(
        voice_identifier, voice_db, owner_store, audio
    )
    if owner_det:
        print(f"[monitor] {rem_id}:   owner voice heard and subtracted.", flush=True)
    if not bid:
        print(f"[monitor] {rem_id}:   only the owner was heard; no bystander.",
              flush=True)
        return None
    print(f"[monitor] {rem_id}: bystander {bid} present "
          f"({'NEW id' if is_new else 'matched existing'}, sim={sim:.2f}, {n_by} "
          "voiced window(s) averaged) - remembered; will decide / ask at the due "
          "time.", flush=True)
    return bid


def _seconds_until(when: datetime.datetime) -> float:
    return (when - datetime.datetime.now()).total_seconds()


def wait_until(when: datetime.datetime, poll: float) -> None:
    """Idle-sleep (mic off) until ``when``, in small steps so Ctrl-C stays live."""

    while True:
        left = _seconds_until(when)
        if left <= 0:
            return
        time.sleep(min(poll, left))


def monitor_and_deliver(
    rem: Reminder,
    remind_at: datetime.datetime,
    watch: BangleClient,
    consent_store: ConsentStore | None,
    voice_identifier: VoiceIdentifier,
    voice_db: FaceDB,
    owner_store: OwnerStore,
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

    # Phase 1 - DETECT & REMEMBER: record the whole window continuously (mic on the
    # entire time), then analyse it once. record_until returns at/after the due
    # time. No consent is asked here - that is deferred to phase 2 (the due time).
    audio = record_until(remind_at, rem.id)
    bystander = analyse_presence(audio, voice_identifier, voice_db, owner_store, rem.id)

    # Phase 2 - it is now the due time. Decide and, only if needed, ask for consent.
    # Re-confirm the owner is still here at the instant of delivery: they may have
    # walked out during the (up to 5 min) window. If gone, HOLD (return None) so
    # the caller keeps the reminder pending rather than announcing it to an empty
    # room or over a bystander with the owner absent.
    if not watch.is_connected():
        print(f"[monitor] {rem.id}: owner not present at delivery time (left during "
              "the window) -> holding until they are back in range.", flush=True)
        return None

    # No bystander was ever heard -> owner is alone -> disclose.
    if bystander is None:
        print(f"[monitor] {rem.id}: no one heard across the window -> owner alone.",
              flush=True)
        demo.deliver_reminder_spoken(text)
        return f"reminder delivered, owner alone (window quiet) [{rem.id}]"

    # A bystander is present and the reminder is now due. In REMEMBER mode
    # (consent_store given) reuse a stored Yes/No if we have one; in RE-ASK mode
    # (consent_store is None) always ask the watch afresh - the bystander is still
    # recognised, but only for logging, never to skip the prompt.
    key = ConsentKey(bystander_id=bystander, content_type=demo.REMINDER_CONTENT_TYPE)
    if consent_store is not None:
        cached = consent_store.get(key)
        if cached is True:
            print(f"[monitor] {rem.id}: remembered YES for {bystander} -> disclose.",
                  flush=True)
            demo.deliver_reminder_spoken(text)
            return f"reminder disclosed, bystander {bystander} (remembered YES) [{rem.id}]"
        if cached is False:
            print(f"[monitor] {rem.id}: remembered NO for {bystander} -> private note.",
                  flush=True)
            watch.notify(private)
            demo.behavior_withhold()
            return f"reminder withheld -> private, bystander {bystander} (remembered NO) [{rem.id}]"

    # Ask the watch: the first time for this bystander (remember mode) or every
    # time (re-ask mode).
    remembered = " (remembered)" if consent_store is not None else ""
    print(f"[monitor] {rem.id}: bystander {bystander} present and reminder is due; "
          "asking on the watch for consent...", flush=True)
    ans = watch.ask_consent(demo.PROMPT_MESSAGE, timeout=demo.CONSENT_TIMEOUT_S)
    if ans is None:
        # A non-answer is never stored (a non-decision); safe non-disclosing default.
        print(f"[monitor] {rem.id}: no watch answer -> private note (not stored).",
              flush=True)
        watch.notify(private)
        demo.behavior_withhold()
        return f"reminder no-reply -> private, bystander {bystander} [{rem.id}]"
    if consent_store is not None:
        consent_store.put(key, ans)
    if ans:
        print(f"[monitor] {rem.id}: watch said YES for {bystander}{remembered} -> "
              "disclose.", flush=True)
        demo.deliver_reminder_spoken(text)
        return f"reminder asked YES, bystander {bystander} [{rem.id}]"
    print(f"[monitor] {rem.id}: watch said NO for {bystander}{remembered} -> "
          "private note.", flush=True)
    watch.notify(private)
    demo.behavior_withhold()
    return f"reminder asked NO, bystander {bystander} [{rem.id}]"


def run(remember: bool) -> None:
    """Run the voice reminder loop.

    ``remember=True``  -> the cache-memory policy: a bystander's Yes/No is stored
                          and reused, so the same person is never re-asked.
    ``remember=False`` -> the re-consent policy: the watch is asked EVERY time a
                          bystander is present; no decision is ever stored.
    Both are exposed as thin entry points (``robot.apps.mic_remember`` /
    ``robot.apps.mic_reask``); this is the shared engine behind them.
    """

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
    args = ap.parse_args()

    # Clamp to sane values so a stray non-positive flag can't turn the idle sleeps
    # into a busy-wait.
    args.poll = max(0.1, args.poll)
    args.lead = max(0.0, args.lead)

    global RMS_GATE, VOICED_FRACTION_MIN, PEAK_RMS
    RMS_GATE = args.gate
    VOICED_FRACTION_MIN = max(0.0, args.min_voiced)
    PEAK_RMS = args.peak

    init_ohbot()
    print(f"[startup] voice detection: a sample counts as a voice if >= "
          f"{VOICED_FRACTION_MIN:.0%} of blocks exceed the gate {RMS_GATE:.3f} "
          f"(sustained) OR >= {PEAK_MIN_BLOCKS} blocks exceed {PEAK_RMS:.3f} "
          f"(bursty/distant). Tune with --gate / --min-voiced / --peak.", flush=True)

    # REMEMBER mode keeps a persistent consent cache; RE-ASK mode keeps none.
    consent_store = ConsentStore(demo.CACHE_PATH) if remember else None
    policy = ("REMEMBER (reuse a bystander's stored Yes/No)" if remember
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
              "is present and to ask consent - will keep checking.", flush=True)

    pending = ReminderStore(demo.REMINDERS_PATH).pending()
    if not pending:
        print("[reminders] none pending. Add one with add_reminder.py.",
              flush=True)
    else:
        print(f"[reminders] {len(pending)} pending; next due {pending[0].remind_at} "
              f"({pending[0].text!r}). For a sensitive reminder the mic records "
              f"CONTINUOUSLY for the ~{int(args.lead)}s (={int(args.lead / 60)} min) "
              f"before its time; mic stays OFF until then.", flush=True)
    print("[running] waiting for reminder times. Press Ctrl-C to quit.", flush=True)

    last_heartbeat = time.monotonic()
    delivery_errors: dict[str, int] = {}   # rem.id -> consecutive failed attempts
    try:
        while True:
            reminder_store = ReminderStore(demo.REMINDERS_PATH)  # re-read: new + delivered
            # Fire args.lead seconds early: a reminder counts as due once we are
            # within the lead window of its scheduled time, so listening/delivery
            # starts ~1 min before rather than exactly at it.
            due = reminder_store.due(
                datetime.datetime.now() + datetime.timedelta(seconds=args.lead)
            )

            if not due:
                now = time.monotonic()
                if now - last_heartbeat >= HEARTBEAT_S:
                    pend = reminder_store.pending()
                    nxt = f"next due {pend[0].remind_at} ({pend[0].text!r})" if pend \
                        else "none pending"
                    print(f"[waiting] {nxt}; mic off.", flush=True)
                    last_heartbeat = now
                time.sleep(args.poll)
                continue

            rem = due[0]
            remind_at = rem.remind_at_dt
            print(f"\n[reminder] {rem.id} approaching (scheduled {rem.remind_at}, "
                  f"~{int(max(_seconds_until(remind_at), 0))}s until due): "
                  f"{rem.text!r}", flush=True)

            # AI sensitivity check: it decides HOW this reminder is delivered.
            # Non-sensitive (an errand) -> speak it at its time, no presence check
            # and no consent. Sensitive (health/finance/personal) -> monitor the
            # pre-reminder window for a bystander and gate on consent.
            sensitive, sens_note = sensitivity_for(rem)
            print(f"[reminder] {rem.id}: sensitivity = "
                  f"{'SENSITIVE' if sensitive else 'NON-SENSITIVE'} ({sens_note}).",
                  flush=True)

            # Is the owner present? BLE link up == owner in ~same room. A reminder
            # is for the owner, so we hold it (either path) until they are back in
            # range rather than announcing it to an empty room. Checked as the
            # window opens; a brief BLE flap mid-window is tolerated.
            if not watch.is_connected():
                print("[reminder] owner not present (watch offline). Holding the "
                      "reminder until the owner is back in range...", flush=True)
                time.sleep(max(args.poll, 3.0))
                continue

            try:
                if not sensitive:
                    # Non-sensitive: nothing to protect -> speak it at its scheduled
                    # time. The mic never opens. We still wait out the window so an
                    # errand isn't blurted minutes early.
                    wait_until(remind_at, args.poll)
                    if not watch.is_connected():
                        # Owner left before the due time -> hold, same as the
                        # sensitive path, rather than talking to an empty room.
                        print(f"[reminder] {rem.id}: owner left before delivery; "
                              "holding until back in range.", flush=True)
                        status = None
                    else:
                        print(f"[reminder] {rem.id}: non-sensitive -> speaking "
                              "normally (no consent needed; mic stayed off).",
                              flush=True)
                        demo.deliver_reminder_spoken(rem.text)
                        status = f"reminder delivered, non-sensitive [{rem.id}]"
                else:
                    # Sensitive: record the window continuously, remember any
                    # bystander, then decide/ask at the due time. Returns None to
                    # HOLD (owner absent at the moment of delivery).
                    status = monitor_and_deliver(
                        rem, remind_at, watch, consent_store, voice_identifier,
                        voice_db, owner_store,
                    )
            except Exception:
                # Transient failure: DON'T mark delivered - leave it pending and
                # retry, capped so a permanently broken reminder can't loop forever.
                import traceback
                traceback.print_exc()
                delivery_errors[rem.id] = delivery_errors.get(rem.id, 0) + 1
                if delivery_errors[rem.id] >= MAX_DELIVERY_ATTEMPTS:
                    print(f"[reminder] {rem.id}: failed {delivery_errors[rem.id]} "
                          "times; giving up and marking it delivered.", flush=True)
                    reminder_store.mark_delivered(rem.id)
                else:
                    print(f"[reminder] {rem.id}: delivery error "
                          f"({delivery_errors[rem.id]}/{MAX_DELIVERY_ATTEMPTS}); "
                          "leaving it pending to retry.", flush=True)
                    time.sleep(max(args.poll, 3.0))
                last_heartbeat = 0.0
                continue

            if status is None:
                # Held (owner not present at delivery) -> keep it pending and retry
                # after a short pause, when the owner may be back in range.
                time.sleep(max(args.poll, 3.0))
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
