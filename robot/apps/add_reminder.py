"""Add a reminder by *speaking* to the robot.

Records you saying a reminder out loud (e.g. "Remind me about my doctor's
appointment on July 20th at 3 PM"), transcribes it with Whisper, pulls the
date/time out of the sentence with dateparser, and saves it to
``reminders.json``. The running voice demo then delivers it at that time
under the presence-gated consent policy (owner alone -> say it right away;
bystander present -> ask the watch first).

This is a one-off setup step, like ``enroll_voice.py`` - not something
run during a live session.

Run:
    python -m robot.apps.add_reminder
    python -m robot.apps.add_reminder --seconds 10 --model small.en

Dependencies (see requirements.txt): openai-whisper, dateparser.
Whisper downloads its model (~74 MB for base.en) into ~/.cache/whisper on
first use.
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys

import numpy as np

try:
    import sounddevice as sd
except (ModuleNotFoundError, OSError) as exc:
    raise SystemExit(
        "Missing dependency: install with `pip install sounddevice` "
        "(needs the PortAudio library; on Linux: `apt install libportaudio2`)."
    ) from exc

from robot.perception.audio_device import pick_input_device
from robot.core.reminders import ReminderStore
from robot.core.sensitivity import SensitivityResult, get_classifier

# Whisper works at 16 kHz mono, same as the rest of the voice stack.
SR = 16000
from robot.paths import REMINDERS_PATH

# Lead-ins we strip from the transcript so the stored text is just the
# subject ("doctor's appointment on July 20th at 3 PM"), not the command
# wrapper ("remind me to ...").
_LEADIN_RE = re.compile(
    r"^\s*(please\s+)?"
    r"(hey\s+robot[,.]?\s+)?"
    r"((can|could)\s+you\s+)?"
    r"(add|set|create|make)?\s*(a|an)?\s*reminder\s*(for|to|about|that)?\s*"
    r"|^\s*remind\s+me\s+(to|about|that|of)?\s*",
    re.IGNORECASE,
)


def record(seconds: float) -> np.ndarray:
    """Capture ``seconds`` of mono 16 kHz audio from the default mic."""

    sd.default.device = (pick_input_device(), sd.default.device[1])
    print(f"\n[record] Speak your reminder now - recording for {seconds:.0f}s...",
          flush=True)
    audio = sd.rec(int(seconds * SR), samplerate=SR, channels=1, dtype="float32")
    sd.wait()
    print("[record] done.", flush=True)
    return audio[:, 0].copy()


def transcribe(model, audio: np.ndarray) -> str:
    """Whisper transcription of a float32 16 kHz buffer -> stripped text."""

    # fp16=False: we run on CPU (Whisper's fp16 path is CUDA-only).
    result = model.transcribe(audio, fp16=False, language="en")
    return str(result.get("text", "")).strip()


def parse_datetime(transcript: str) -> tuple[str, datetime.datetime] | None:
    """Find the date/time in ``transcript``; returns (matched_text, dt).

    Uses dateparser's in-sentence search, preferring future dates so a bare
    "at 3 PM" or "on Friday" resolves to the next occurrence rather than the
    past. Returns None if no date/time can be found.
    """

    from dateparser.search import search_dates

    found = search_dates(
        transcript,
        settings={
            "PREFER_DATES_FROM": "future",
            "RETURN_AS_TIMEZONE_AWARE": False,
        },
    )
    if not found:
        return None
    # Prefer the longest matched phrase - "July 20th at 3 PM" over a bare
    # "3 PM" - so we capture both the date and the time when both are said.
    matched_text, dt = max(found, key=lambda pair: len(pair[0]))
    return matched_text, dt


def clean_text(transcript: str) -> str:
    """Strip the command wrapper so the stored text is just the subject."""

    text = _LEADIN_RE.sub("", transcript, count=1).strip()
    text = text.rstrip(".").strip()
    if not text:
        text = transcript.strip().rstrip(".")
    return text[:1].upper() + text[1:] if text else text


def confirm_and_save(
    store: ReminderStore,
    text: str,
    dt: datetime.datetime,
    sens: SensitivityResult,
) -> str:
    """Show the parse and ask what to do. Returns 'saved', 'retry', or 'quit'.

    ``[s]`` flips the sensitivity label in case the classifier got it wrong -
    the owner stays in control of whether a reminder is spoken freely or gated.
    """

    pretty = dt.strftime("%A %d %B %Y at %H:%M")
    sensitive = sens.sensitive
    while True:
        handling = ("SENSITIVE - I'll ask on your watch before saying it aloud "
                    "if someone is with you"
                    if sensitive else
                    "non-sensitive - I'll just say it, even if someone is around")
        print("\n[reminder] I understood:")
        print(f"    subject     : {text}")
        print(f"    when        : {pretty}")
        print(f"    sensitivity : {handling}")
        print(f"                  ({sens.backend}: {sens.reason})")
        try:
            reply = input(
                "Save this reminder? [y]es / [s]witch sensitivity / "
                "[r]etry / [q]uit: "
            ).strip().lower()
        except EOFError:
            reply = "q"
        if reply.startswith("s"):
            sensitive = not sensitive
            continue
        if reply.startswith("y"):
            rem = store.add(text, dt, sensitive=sensitive)
            tag = "sensitive" if sensitive else "non-sensitive"
            print(f"[reminder] saved {rem.id} ({tag}): {text!r} due {pretty}.",
                  flush=True)
            _speak_confirmation(f"Okay, I will remind you about {text} on {pretty}.")
            return "saved"
        if reply.startswith("r"):
            return "retry"
        print("[reminder] not saved.", flush=True)
        return "quit"


def _speak_confirmation(text: str) -> None:
    """Best-effort spoken confirmation via the OS voice (no Ohbot needed)."""

    cmd = None
    if sys.platform == "darwin":
        cmd = ["say", text]
    elif sys.platform.startswith("linux"):
        cmd = ["espeak", text]
    if cmd is None:
        return
    try:
        subprocess.run(cmd, timeout=20, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Add a reminder by voice.")
    ap.add_argument("--seconds", type=float, default=8.0,
                    help="recording length (default 8s)")
    ap.add_argument("--model", type=str, default="base.en",
                    help="Whisper model (tiny.en/base.en/small.en; default base.en)")
    args = ap.parse_args()

    try:
        import whisper
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: install with `pip install openai-whisper` "
            "(uses torch, already a voice-stack dep)."
        ) from exc

    print(f"[startup] loading Whisper model '{args.model}' "
          "(first run downloads it)...", flush=True)
    model = whisper.load_model(args.model)
    # Sensitivity classifier: decides whether a reminder is presence-gated
    # (health/finance/personal) or safe to speak freely. Built once here.
    classifier = get_classifier()
    store = ReminderStore(REMINDERS_PATH)

    while True:
        audio = record(args.seconds)
        transcript = transcribe(model, audio)
        if not transcript:
            print("[reminder] heard nothing. Try again (speak clearly).", flush=True)
            if not _again():
                return
            continue
        print(f"[reminder] transcript: {transcript!r}", flush=True)

        parsed = parse_datetime(transcript)
        if parsed is None:
            print("[reminder] couldn't find a date/time in that. Say something "
                  "like 'doctor's appointment on July 20th at 3 PM'.", flush=True)
            if not _again():
                return
            continue

        _, dt = parsed
        text = clean_text(transcript)
        sens = classifier.classify(text)
        if confirm_and_save(store, text, dt, sens) == "retry":
            continue
        return


def _again() -> bool:
    try:
        return input("Record again? [y/N]: ").strip().lower().startswith("y")
    except EOFError:
        return False


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[reminder] interrupted.", file=sys.stderr)
