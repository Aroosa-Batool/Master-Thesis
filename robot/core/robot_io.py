"""Shared reminder-delivery support for the voice pipeline.

  - the Ohbot glue (init/lock/shutdown, macOS ``afplay`` shim, OS-TTS fallback);
  - the on-disk paths for the voice identity + consent + reminder stores;
  - the reminder consent constants and speech templates;
  - the spoken/neutral behaviours (``deliver_reminder_spoken``,
    ``behavior_withhold``);
  - ``identify_bystander_averaged`` - collapse the non-owner voice windows in a
    recording into one stable bystander id, using the enrolled owner print to
    subtract the watch-wearer.

Identity/consent stores (a voice ``person_001`` is a different namespace from a
face ``person_001``):
  - owner voice print : ``owner_voice.json``      (enroll_voice.py)
  - bystander gallery : ``voice_db.json``
  - consent memory    : ``consent_cache_voice.json``
  - reminders         : ``reminders.json``        (add_reminder.py)

This module is not meant to be run directly; use ``mic_remember`` / ``mic_reask``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading

import numpy as np

from robot.perception.face_db import FaceDB
from robot.core.owner import OwnerStore
from robot.perception.voice_id import VOICE_OWNER_THRESHOLD, VoiceIdentifier
from robot.core.logsetup import logcall, get_logger

log = get_logger(__name__)


OHBOT_PORT_HINT = os.environ.get("OHBOT_PORT", "Pico")
# Set NO_OHBOT=1 to skip Ohbot init/use entirely - the consent flow on the
# watch still runs and disclose/withhold are spoken via the OS voice.
NO_OHBOT = os.environ.get("NO_OHBOT") == "1"

# Importing the third-party Ohbot module opens a serial port immediately on some
# SDK versions.  Keep it genuinely lazy so importing the reminder engines is
# safe in tests, in the presentation dashboard, and in laptop-voice mode.
ohbot = None


def load_ohbot():
    """Return the Ohbot SDK module, importing it only for a real robot run."""

    global ohbot
    if NO_OHBOT:
        return None
    if ohbot is not None:
        return ohbot
    try:
        from ohbot import ohbot as sdk
    except ModuleNotFoundError as exc:
        raise SystemExit("Missing dependency: install with `pip install ohbot`.") from exc
    ohbot = sdk
    _configure_macos_playback(ohbot)
    return ohbot

def _configure_macos_playback(sdk) -> None:
    """Install the macOS playback shim after the SDK has been loaded."""

    if sys.platform != "darwin":
        return
    silence_wav = os.path.join(os.path.dirname(sdk.__file__), "Silence1.wav")

    @logcall
    def _say_speech_macos(addSilence):
        try:
            if addSilence:
                subprocess.run(["afplay", silence_wav], timeout=5, check=False)
            subprocess.run(["afplay", "ohbotspeech.wav"], timeout=30, check=False)
        except subprocess.TimeoutExpired:
            print("[ohbot] afplay timed out; continuing.")
        except FileNotFoundError:
            print("[ohbot] afplay not found; skipping audio.")

    sdk.saySpeech = _say_speech_macos


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

# Reminders share ONE content type (not one per reminder) so a bystander's
# Yes/No is remembered across every reminder, not re-asked for each.
REMINDER_CONTENT_TYPE = "reminder"
from robot.paths import (
    VOICE_CONSENT_CACHE_PATH as CACHE_PATH,
    VOICE_DB_PATH,
    OWNER_VOICE_PATH,
    REMINDERS_PATH,
)

PROMPT_MESSAGE = (
    "I have noticed that someone is present with you. "
    "Do you want me to send private reminders in front of them?"
)

# Neutral line the robot speaks when a reminder is withheld from disclosure.
WITHHOLD_LINE = "Hello there."

# Reminder content (a doctor's appointment etc.). Spoken aloud on a Yes or when
# the owner is alone; pushed privately to the wrist on a No.
REMINDER_DISCLOSE_TEMPLATE = "Here is your reminder for {text}."
REMINDER_PRIVATE_TEMPLATE = "Reminder: {text}"


@logcall
def behavior_withhold() -> None:
    """Reminder withheld from disclosure - Ohbot stays neutral."""

    print(f">>> withhold -> {WITHHOLD_LINE!r}")
    log.info("reminder withheld from disclosure", extra={"event": "withheld"})
    if NO_OHBOT:
        print("[ohbot] NO_OHBOT=1; speaking via OS TTS instead.")
        _speak_fallback(WITHHOLD_LINE)
        return
    bot = load_ohbot()
    with ohbot_lock:
        if shutting_down.is_set():
            return
        try:
            bot.move(bot.HEADTURN, 5)
            bot.say(WITHHOLD_LINE, untilDone=True, lipSync=True)
        except Exception as exc:
            print(f"[ohbot] withhold failed: {exc}")


@logcall
def deliver_reminder_spoken(text: str) -> None:
    """Speak a reminder out loud - owner-alone delivery, or a consented Yes."""

    msg = REMINDER_DISCLOSE_TEMPLATE.format(text=text)
    print(f">>> reminder disclose -> {msg!r}")
    log.info("reminder disclosed aloud", extra={"event": "delivered"})
    if NO_OHBOT:
        print("[ohbot] NO_OHBOT=1; speaking via OS TTS instead.")
        _speak_fallback(msg)
        return
    bot = load_ohbot()
    with ohbot_lock:
        if shutting_down.is_set():
            return
        try:
            bot.move(bot.HEADTURN, 5)
            bot.move(bot.HEADNOD, 5)
            bot.say(msg, untilDone=True, lipSync=True)
        except Exception as exc:
            print(f"[ohbot] reminder disclose failed: {exc}")


@logcall
def identify_bystander_averaged(
    voice_identifier: VoiceIdentifier,
    voice_db: FaceDB,
    owner_store: OwnerStore,
    audio: np.ndarray,
) -> tuple[str, float, bool, bool, int]:
    """Collapse all non-owner windows into ONE averaged embedding -> one id.

    A reminder encounter is the owner plus (typically) at most one other
    person. Identifying each ~1.6 s window separately splits a single speaker
    across several ids whenever their windows straddle the match threshold -
    common for short or played-back / far-field audio, where one speaker's own
    windows can score anywhere from ~0.6 to ~0.9 against each other. Averaging
    the non-owner windows first yields ONE stable bystander id per encounter,
    and a cleaner (noise-reduced) embedding that re-matches more reliably next
    time - which is what makes the consent memory actually stick. Trade-off:
    two DIFFERENT people talking in the same window merge into one id
    (acceptable for the owner-plus-one reminder case).

    Returns ``(bystander_id, similarity, is_new, owner_detected, n_bystander)``;
    ``bystander_id`` is "" when no non-owner voice was heard.
    """

    windows = voice_identifier.segment_and_embed(audio)
    owner_detected = False
    bystander_embs: list[np.ndarray] = []
    for win in windows:
        is_owner, _sim = owner_store.matches(
            win.embedding, threshold=VOICE_OWNER_THRESHOLD
        )
        if is_owner:
            owner_detected = True
        else:
            bystander_embs.append(win.embedding)
    if not bystander_embs:
        return "", 0.0, False, owner_detected, 0
    mean_emb = np.mean(np.stack(bystander_embs, axis=0), axis=0)
    pid, sim, is_new = voice_db.identify(mean_emb)
    log.info("bystander %s (sim=%.2f, new=%s)", pid, sim, is_new,
             extra={"event": "new_person" if is_new else "identified"})
    return pid, sim, is_new, owner_detected, len(bystander_embs)
