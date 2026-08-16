"""Is this sound a HUMAN VOICE, or just something loud? - a neural VAD gate.

The presence pipeline used to answer "is anyone here?" with **energy alone**: a
block-RMS gate plus a peak test (``voice_reminder.presence_metrics``). Energy
cannot tell a person from an appliance, and the identity stage that follows only
ever asks *"is this the owner?"* - so anything loud that is **not** the owner was
filed as a bystander. A coffee grinder, a vacuum, a fan or a blender would each
mint a ``person_NNN`` voiceprint and make the robot believe someone was standing
there, which withholds a reminder the owner should have heard.

Resemblyzer's own preprocessing does not save us either. It trims with
``webrtcvad`` at mode 3, a classical GMM VAD; measured on this project's own
synthetic noise it keeps **99.8% of pure broadband noise** as "speech", because
loud aperiodic noise looks like a fricative to it. There was therefore no test
anywhere in the pipeline for *"is this speech at all?"* - only for *"is this the
owner?"*.

This module adds that missing test, using **Silero VAD** (Silero Team, 2021) - a
small pretrained neural voice-activity detector that classifies 32 ms chunks by
their *content* rather than their loudness. Measured on the same signals:

    signal                     energy gate    Silero
    real speech                VOICE          4.90 s of 5 s   -> speech
    coffee grinder             VOICE          0.00 s          -> not a voice
    fan / vacuum               VOICE          0.00 s          -> not a voice
    blender (harsh + whine)    VOICE          0.00 s          -> not a voice
    speech buried in noise     VOICE          4.80 s          -> speech

The last row matters as much as the noise rows: the gate must not throw away a
real bystander who happens to be talking in a noisy kitchen. It does not - it
recovers the speech and discards the noise around it.

Cost is negligible: the model loads in ~0.02 s and scores a full 5-minute
monitoring window in ~0.8 s, so the check adds no perceptible delay to a delivery.
The weights ship **inside the pip package** (``silero-vad``), so there is no
download at run time and no network dependency.

Backends
--------
``silero``  (default) - the neural VAD described above.
``energy``  - the legacy behaviour: every sample counts as speech, so the decision
              falls back to the RMS gate alone. This exists so the two can be
              A/B'd on the same recording, and as a graceful degradation if the
              package is missing. It is the behaviour that mistook a grinder for a
              person, so choosing it prints a warning and it is named in the logs.

Select with the ``SPEECH_VAD`` environment variable::

    SPEECH_VAD=energy python -m robot.apps.mic_remember    # legacy, for comparison

Usage::

    detector = get_speech_detector()
    speech = detector.speech_only(audio)     # human-speech samples, noise removed
    if detector.speech_seconds(audio) < MIN_SPEECH_S:
        ...                                  # loud, but nobody spoke
"""

from __future__ import annotations

import os

import numpy as np

from robot.core.logsetup import get_logger, logcall
from robot.perception.voice_id import VOICE_SR

log = get_logger(__name__)


SPEECH_VAD_ENV = "SPEECH_VAD"            # "silero" (default) | "energy"
BACKEND_SILERO = "silero"
BACKEND_ENERGY = "energy"

# Per-chunk speech probability above which Silero calls a 32 ms chunk speech.
# 0.5 is the model's own default and is what the numbers in the docstring were
# measured at; raise it to be stricter about faint/ambiguous speech.
DEFAULT_SPEECH_THRESHOLD = 0.5

# How much human speech must be present before we are willing to say "a person is
# here". Resemblyzer needs ~0.6 s of voiced audio to embed a speaker reliably
# (``voice_id._MIN_VOICED_S``), so anything under that could not produce a
# trustworthy voiceprint anyway - and a lone 200 ms blip is far more likely to be
# a door or a clatter than a bystander.
MIN_SPEECH_S = 0.6

# Silero is trained on 16 kHz (and 8 kHz) audio and requires one of those rates.
# The whole voice pipeline already runs at VOICE_SR = 16 kHz, so this only guards
# against a caller passing something else.
SUPPORTED_SR = (8000, 16000)


class SpeechDetector:
    """Find the stretches of an audio buffer that are actually human speech.

    Built once and reused - the model is tiny but constructing it per call would
    still be wasteful. Thread-safety mirrors ``VoiceIdentifier``: the pipeline
    analyses one recording at a time on one worker, and the model is used
    read-only.
    """

    @logcall
    def __init__(
        self,
        threshold: float = DEFAULT_SPEECH_THRESHOLD,
        min_speech_s: float = MIN_SPEECH_S,
        backend: str | None = None,
    ) -> None:
        self.threshold = threshold
        self.min_speech_s = min_speech_s
        want = (backend or os.environ.get(SPEECH_VAD_ENV, BACKEND_SILERO)).lower()
        self._model = None
        self._get_speech_timestamps = None

        if want == BACKEND_ENERGY:
            self.backend = BACKEND_ENERGY
            print("[vad] SPEECH_VAD=energy: the neural speech gate is OFF. Presence "
                  "falls back to loudness alone, which CANNOT tell a person from a "
                  "grinder/fan/vacuum. Use this only to compare against the fixed "
                  "behaviour.", flush=True)
            log.warning("speech gate disabled; energy-only presence",
                        extra={"event": "vad_backend"})
            return

        try:
            import torch                                    # noqa: PLC0415
            from silero_vad import get_speech_timestamps, load_silero_vad  # noqa: PLC0415

            self._torch = torch
            self._model = load_silero_vad()
            self._get_speech_timestamps = get_speech_timestamps
            self.backend = BACKEND_SILERO
            log.info("Silero VAD loaded (threshold %.2f, min speech %.2fs)",
                     self.threshold, self.min_speech_s,
                     extra={"event": "model_loaded"})
        except Exception as exc:
            # Degrade rather than crash: a study session must not die because an
            # optional package is missing. But say so loudly - in this mode the
            # grinder bug is back.
            self.backend = BACKEND_ENERGY
            print(f"[vad] WARNING: could not load Silero VAD ({exc}). Falling back "
                  "to loudness-only presence, which mistakes appliances "
                  "(grinder/fan/vacuum) for people. Fix with:\n"
                  "    pip install silero-vad", flush=True)
            log.warning("Silero VAD unavailable (%s); energy-only presence", exc,
                        extra={"event": "vad_backend"})

    @property
    def enabled(self) -> bool:
        """True when a real speech-vs-noise test is being applied."""

        return self.backend == BACKEND_SILERO

    @logcall
    def speech_regions(
        self, audio: np.ndarray, sr: int = VOICE_SR
    ) -> list[tuple[int, int]]:
        """The ``(start, end)`` sample ranges of ``audio`` that are human speech.

        Returns one range covering everything under the ``energy`` backend (no
        content test available), and an empty list when nobody spoke.
        """

        audio = np.asarray(audio, dtype=np.float32).flatten()
        if len(audio) == 0:
            return []
        if not self.enabled:
            return [(0, len(audio))]
        if sr not in SUPPORTED_SR:
            raise ValueError(
                f"[vad] Silero VAD supports {SUPPORTED_SR} Hz, got {sr}."
            )
        stamps = self._get_speech_timestamps(
            self._torch.from_numpy(audio), self._model,
            sampling_rate=sr, threshold=self.threshold,
        )
        return [(int(s["start"]), int(s["end"])) for s in stamps]

    @logcall
    def speech_only(self, audio: np.ndarray, sr: int = VOICE_SR) -> np.ndarray:
        """``audio`` with everything that is not human speech removed.

        The speech stretches are concatenated, which is exactly what Resemblyzer's
        own ``trim_long_silences`` does before embedding, so the result is a valid
        input to the speaker encoder. Empty when nobody spoke - and an empty buffer
        can never mint a bystander voiceprint, which is the whole point.
        """

        audio = np.asarray(audio, dtype=np.float32).flatten()
        regions = self.speech_regions(audio, sr)
        if not regions:
            return np.zeros(0, dtype=np.float32)
        if len(regions) == 1 and regions[0] == (0, len(audio)):
            return audio
        return np.concatenate([audio[a:b] for a, b in regions]).astype(np.float32)

    @logcall
    def speech_seconds(self, audio: np.ndarray, sr: int = VOICE_SR) -> float:
        """How many seconds of ``audio`` are human speech."""

        return sum(b - a for a, b in self.speech_regions(audio, sr)) / float(sr)

    @logcall
    def has_speech(self, audio: np.ndarray, sr: int = VOICE_SR) -> bool:
        """True when at least ``min_speech_s`` of human speech is present."""

        if not self.enabled:
            return True          # no content test; the caller's energy gate decides
        return self.speech_seconds(audio, sr) >= self.min_speech_s


_detector: SpeechDetector | None = None


def get_speech_detector(**kwargs) -> SpeechDetector:
    """The process-wide detector, built on first use.

    Lazily constructed so importing this module (or the voice engine) never loads
    a model; the first presence check pays the ~0.02 s.
    """

    global _detector
    if _detector is None:
        _detector = SpeechDetector(**kwargs)
    return _detector
