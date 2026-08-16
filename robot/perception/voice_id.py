"""Speaker (voice) recognition - the audio analog of ``face_id.py``.

Mirrors the camera stack: where ``face_id.py`` uses YuNet to find faces
and SFace to turn each into a 128-D embedding, this module turns a chunk
of microphone audio into one or more 256-D *speaker* embeddings using
Resemblyzer's pretrained GE2E "d-vector" encoder (Wan et al. 2018) - the
same deep-embedding-plus-cosine-similarity family as SFace/FaceNet, which
keeps the thesis story consistent across the two modalities.

Each ~1.6 s voiced window becomes one embedding; cosine similarity then
tells whether two windows are the same speaker. The owner's voice is
enrolled once (``enroll_voice.py``) and every other speaker heard in
a trial is treated as a bystander - exactly the owner-vs-bystander split
the camera pipeline performs per face.

Resemblyzer ships its model weights inside the pip package, so there is no
separate download step (contrast ``face_id.ensure_models()``). The first
``VoiceIdentifier()`` constructed loads the torch model, which takes a
second or two.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import numpy as np

from robot.core.logsetup import logcall, get_logger
from robot.paths import VOICE_MEAN_PATH

try:
    from resemblyzer import VoiceEncoder, preprocess_wav
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing dependency: install with `pip install resemblyzer` "
        "(pulls in torch). See requirements.txt."
    ) from exc

log = get_logger(__name__)


# Resemblyzer works internally at 16 kHz mono.
VOICE_SR = 16000

# Cosine-similarity thresholds on the 256-D d-vectors. Resemblyzer
# embeddings sit higher than SFace's. Tune per microphone and room (a
# close-talking headset scores higher than a far-field laptop mic).
#   VOICE_SAME_SPEAKER    - two windows are the same bystander (gallery re-ID)
#   VOICE_OWNER_THRESHOLD - a window is the enrolled owner
# VOICE_SAME_SPEAKER was lowered from 0.75 to 0.70 after measuring a laptop
# mic where ONE speaker's own ~1.6 s windows scored 0.72-0.88 among
# themselves (occasionally dipping to ~0.75). At 0.75 that split a single
# person across several IDs, so their consent was never remembered. 0.70
# keeps a speaker's windows together while still separating different people,
# who score ~0.5 (well below 0.70).
# Owner recognition wants to be reliable: a *missed* owner window gets
# misfiled as a bystander and can fire a spurious prompt.
VOICE_SAME_SPEAKER = 0.70
VOICE_OWNER_THRESHOLD = 0.73

# Ignore preprocessed (VAD-trimmed) audio shorter than this - too little
# voiced signal to embed reliably.
_MIN_VOICED_S = 0.6


def load_voice_mean() -> np.ndarray | None:
    """The cohort "mean voice" d-vector used to CENTER embeddings, or None.

    Built by ``python -m robot.bench.voice_similarity --save-mean`` from several
    DIFFERENT voices. Resemblyzer's raw d-vectors all sit in a narrow cone, so
    the cosine between two DIFFERENT speakers is biased high - which makes a new
    bystander look like an existing gallery entry. Subtracting this average-voice
    vector before cosine decorrelates them and widens the same-vs-different gap.
    Absent file -> centering is off (raw behaviour), so this is fully backward
    compatible; the pipeline only centers once a mean has been calibrated.
    """

    if not VOICE_MEAN_PATH.exists():
        return None
    try:
        data = json.loads(VOICE_MEAN_PATH.read_text())
        mean = np.asarray(data["mean"], dtype=np.float32).flatten()
        return mean if mean.size else None
    except Exception as exc:
        print(f"[voice_id] could not read {VOICE_MEAN_PATH}: {exc}; centering off.",
              flush=True)
        return None


def center_embedding(emb: np.ndarray, mean: np.ndarray | None) -> np.ndarray:
    """Subtract the cohort mean and re-normalise (no-op if ``mean`` is None)."""

    if mean is None or mean.shape != emb.shape:
        return emb
    centered = emb - mean
    norm = float(np.linalg.norm(centered))
    return (centered / norm).astype(np.float32) if norm > 1e-9 else emb


@dataclass
class DetectedVoice:
    """One voiced window extracted from an audio buffer."""

    embedding: np.ndarray   # 256-D float32, L2-normalised by Resemblyzer
    start_s: float          # window start within the trimmed buffer
    stop_s: float

    @property
    def duration_s(self) -> float:
        return self.stop_s - self.start_s


class VoiceIdentifier:
    """Turn an audio buffer into per-window speaker embeddings.

    Thread-safety mirrors ``FaceIdentifier``: the demo only calls
    ``segment_and_embed`` from a single trial worker at a time, so there is
    no internal lock (the torch model is used read-only).
    """

    @logcall
    def __init__(self, center: bool = True) -> None:
        # Loads the bundled GE2E weights onto CPU (or CUDA if present).
        self._encoder = VoiceEncoder(verbose=True)
        # Optional cohort-mean centering (see load_voice_mean). Off until a
        # voice_mean.json is calibrated, so default behaviour is unchanged.
        self._mean = load_voice_mean() if center else None
        state = "on" if self._mean is not None else "off (no voice_mean.json)"
        log.info("voice encoder (GE2E d-vector) loaded; centering %s", state,
                 extra={"event": "model_loaded"})
        if self._mean is not None:
            print(f"[voice_id] d-vector centering ON (using {VOICE_MEAN_PATH.name}).",
                  flush=True)

    @logcall(level=logging.DEBUG)
    def _center(self, emb: np.ndarray) -> np.ndarray:
        return center_embedding(emb, self._mean)

    @logcall(level=logging.DEBUG)
    def embed(
        self, audio: np.ndarray, source_sr: int = VOICE_SR
    ) -> np.ndarray | None:
        """One whole-utterance embedding, or None if too little voiced audio.

        Used by the enrollment verify loop. ``audio`` is float32 in
        [-1, 1]; ``source_sr`` is its sample rate before Resemblyzer
        resamples to 16 kHz.
        """

        wav = preprocess_wav(np.asarray(audio, dtype=np.float32), source_sr=source_sr)
        if len(wav) < int(_MIN_VOICED_S * VOICE_SR):
            return None
        emb = self._encoder.embed_utterance(wav)
        return self._center(np.asarray(emb, dtype=np.float32).flatten())

    @logcall(level=logging.DEBUG)
    def segment_and_embed(
        self, audio: np.ndarray, source_sr: int = VOICE_SR
    ) -> list[DetectedVoice]:
        """VAD-trim ``audio`` and embed each ~1.6 s voiced window.

        Returns one ``DetectedVoice`` per partial window - analogous to
        ``FaceIdentifier.detect_and_embed`` returning one ``DetectedFace``
        per face. Empty if the buffer holds no usable speech.

        Caveat (documented like the camera trade-offs): each window is
        assumed to contain a single dominant speaker. If the owner and a
        bystander talk over each other within the same ~1.6 s window, that
        window's embedding is a blend and may match neither cleanly. In
        practice turn-taking conversation puts them in separate windows,
        which is the case this is built for.
        """

        wav = preprocess_wav(np.asarray(audio, dtype=np.float32), source_sr=source_sr)
        if len(wav) < int(_MIN_VOICED_S * VOICE_SR):
            return []
        _, partials, slices = self._encoder.embed_utterance(
            wav, return_partials=True
        )
        out: list[DetectedVoice] = []
        for emb, sl in zip(partials, slices):
            out.append(
                DetectedVoice(
                    embedding=self._center(np.asarray(emb, dtype=np.float32).flatten()),
                    start_s=sl.start / VOICE_SR,
                    stop_s=sl.stop / VOICE_SR,
                )
            )
        return out
