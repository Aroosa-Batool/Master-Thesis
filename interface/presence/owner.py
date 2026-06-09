"""Persistent single-record store for the system owner's face.

The "owner" is the watch wearer - the person the consent prompts on
the Bangle.js are addressed to. They are enrolled once via
``enroll_owner.py`` and recognised in every subsequent trial frame so
``identify_people_in_frame`` can drop them from the cache key, leaving
only the bystanders. This is what makes "remember Anna's decision the
next time Anna is in the room" actually work - the owner is always in
the room, so without this filter the cache key would change every
time the owner glances away from the camera.

Storage: a single JSON file at ``interface/presence/owner_face.json``.
The embedding is averaged across N enrollment frames and L2-normalised
once, so similarity checks at recognition time are a single cosine.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import threading
from pathlib import Path

import numpy as np


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a)) * float(np.linalg.norm(b))
    if denom <= 1e-12:
        return 0.0
    return float(np.dot(a, b) / denom)


class OwnerStore:
    """Persistent single-record store for the system owner's face.

    Thread-safe: the demos load this on the main thread at startup
    and read it from the trial worker thread during recognition. The
    enrollment script is the only writer.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._embedding: np.ndarray | None = None
        self._samples: int = 0
        self._enrolled_at: str = ""
        self._load()

    # --- public --------------------------------------------------------------

    def has_owner(self) -> bool:
        with self._lock:
            return self._embedding is not None

    def samples(self) -> int:
        with self._lock:
            return self._samples

    def enrolled_at(self) -> str:
        with self._lock:
            return self._enrolled_at

    def matches(
        self, embedding: np.ndarray, threshold: float
    ) -> tuple[bool, float]:
        """Returns ``(is_owner, similarity)``.

        ``similarity`` is 0.0 if no owner is enrolled (so callers can
        log without a branch). The first return is the threshold-
        gated boolean and is False whenever no owner is enrolled.
        """

        with self._lock:
            if self._embedding is None:
                return False, 0.0
            emb = np.asarray(embedding, dtype=np.float32).flatten()
            sim = _cosine(emb, self._embedding)
        return (sim >= threshold), sim

    def save(
        self, embedding: np.ndarray, samples: int, enrolled_at: str
    ) -> None:
        emb = np.asarray(embedding, dtype=np.float32).flatten().copy()
        # Re-normalise to unit length after averaging. SFace embeddings
        # are unit vectors out of feature(), so the average of N near-
        # identical embeddings is ~unit length, but we don't rely on it.
        norm = float(np.linalg.norm(emb))
        if norm > 1e-9:
            emb = emb / norm
        with self._lock:
            self._embedding = emb
            self._samples = int(samples)
            self._enrolled_at = enrolled_at
            self._save_locked()

    def clear(self) -> None:
        with self._lock:
            self._embedding = None
            self._samples = 0
            self._enrolled_at = ""
            try:
                self._path.unlink()
            except FileNotFoundError:
                pass

    # --- private -------------------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
            raw = base64.b64decode(data["embedding"].encode("ascii"))
            self._embedding = np.frombuffer(raw, dtype=np.float32).copy()
            self._samples = int(data.get("samples", 0))
            self._enrolled_at = str(data.get("enrolled_at", ""))
        except Exception as exc:
            print(
                f"[owner] could not load {self._path}: {exc}; "
                "treat as unenrolled.",
                flush=True,
            )
            self._embedding = None

    def _save_locked(self) -> None:
        assert self._embedding is not None
        payload = json.dumps(
            {
                "enrolled_at": self._enrolled_at,
                "samples": self._samples,
                "embedding": base64.b64encode(
                    self._embedding.tobytes()
                ).decode("ascii"),
            },
            indent=2,
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd, tmp_name = tempfile.mkstemp(
                prefix=self._path.name + ".",
                suffix=".tmp",
                dir=str(self._path.parent),
            )
            try:
                with os.fdopen(fd, "w") as f:
                    f.write(payload)
                os.replace(tmp_name, self._path)
            except Exception:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
        except Exception as exc:
            print(f"[owner] could not write {self._path}: {exc}", flush=True)
