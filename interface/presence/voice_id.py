"""Speaker (voice) recognition - the audio analog of ``face_id.py``.

Mirrors the camera stack: where ``face_id.py`` uses YuNet to find faces
and SFace to turn each into a 128-D embedding, this module turns a chunk
of microphone audio into one or more 256-D *speaker* embeddings using
Resemblyzer's pretrained GE2E "d-vector" encoder (Wan et al. 2018) - the
same deep-embedding-plus-cosine-similarity family as SFace/FaceNet, which
keeps the thesis story consistent across the two modalities.

Each ~1.6 s voiced window becomes one embedding; cosine similarity then
tells whether two windows are the same speaker. The owner's voice is
enrolled once (``enroll_owner_voice.py``) and every other speaker heard in
a trial is treated as a bystander - exactly the owner-vs-bystander split
the camera pipeline performs per face.

Resemblyzer ships its model weights inside the pip package, so there is no
separate download step (contrast ``face_id.ensure_models()``). The first
``VoiceIdentifier()`` constructed loads the torch model, which takes a
second or two.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    from resemblyzer import VoiceEncoder, preprocess_wav
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing dependency: install with `pip install resemblyzer` "
        "(pulls in torch). See interface/requirements.txt."
    ) from exc


# Resemblyzer works internally at 16 kHz mono.
VOICE_SR = 16000

# Cosine-similarity thresholds on the 256-D d-vectors. Resemblyzer
# embeddings sit higher than SFace's: same-speaker pairs typically score
# ~0.75+, different speakers well below. These are sane starting points;
# tune per microphone and room (a close-talking headset scores higher
# than a far-field laptop mic).
#   VOICE_SAME_SPEAKER    - two windows are the same bystander (gallery re-ID)
#   VOICE_OWNER_THRESHOLD - a window is the enrolled owner
# Owner recognition wants to be reliable: a *missed* owner window gets
# misfiled as a bystander and can fire a spurious prompt, so the owner bar
# is set no higher than the same-speaker bar (the opposite trade-off to the
# camera, where a false owner match was the more harmful error).
VOICE_SAME_SPEAKER = 0.75
VOICE_OWNER_THRESHOLD = 0.73

# Ignore preprocessed (VAD-trimmed) audio shorter than this - too little
# voiced signal to embed reliably.
_MIN_VOICED_S = 0.6


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

    def __init__(self) -> None:
        # Loads the bundled GE2E weights onto CPU (or CUDA if present).
        self._encoder = VoiceEncoder(verbose=True)

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
        return np.asarray(emb, dtype=np.float32).flatten()

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
                    embedding=np.asarray(emb, dtype=np.float32).flatten(),
                    start_s=sl.start / VOICE_SR,
                    stop_s=sl.stop / VOICE_SR,
                )
            )
        return out
