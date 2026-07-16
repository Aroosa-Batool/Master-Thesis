"""Persistent face gallery: embedding -> stable string ID.

Used by the demos to auto-label every face the camera sees. The first
time an embedding is seen, the gallery mints a fresh ``person_001`` /
``person_002`` / ... ID and stores the embedding under it. Subsequent
encounters of the same face (cosine similarity >= threshold) return
the same ID.

This is the stand-in for the "Bystander identity" stage of the thesis
pipeline (stage 3 in docs/meeting_brief.md). Cosine similarity on
SFace embeddings is the same family as FaceNet (Schroff 2015) with
the practical advantage that no dlib compile is needed.

The gallery file is JSON; embeddings are stored as base64-encoded
float32 blobs so the file stays compact and roundtrips exactly.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from robot.core.logsetup import logcall, get_logger

log = get_logger(__name__)


@dataclass
class _Record:
    person_id: str
    embedding: np.ndarray  # float32, shape (D,)


@logcall(level=logging.DEBUG)
def _encode_embedding(emb: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(emb, dtype=np.float32).tobytes()).decode("ascii")


@logcall(level=logging.DEBUG)
def _decode_embedding(s: str) -> np.ndarray:
    raw = base64.b64decode(s.encode("ascii"))
    return np.frombuffer(raw, dtype=np.float32).copy()


@logcall(level=logging.DEBUG)
def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity. SFace embeddings are L2-normalised, but we
    do the full computation here so this works with any embedding."""

    denom = float(np.linalg.norm(a)) * float(np.linalg.norm(b))
    if denom <= 1e-12:
        return 0.0
    return float(np.dot(a, b) / denom)


class FaceDB:
    """Persistent gallery of (person_id, embedding).

    Thread-safe via a single ``threading.Lock``. Writes go through a
    same-directory tempfile + ``os.replace`` for atomicity, same
    pattern as ``ConsentStore`` in ``policy.py`` - protects against
    half-written JSON if the process is killed mid-write.
    """

    @logcall
    def __init__(self, path: Path, match_threshold: float) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._records: list[_Record] = []
        self._next_id: int = 1
        self._match_threshold = match_threshold
        self._load()

    # --- public --------------------------------------------------------------

    @logcall
    def identify(self, embedding: np.ndarray) -> tuple[str, float, bool]:
        """Return ``(person_id, similarity, is_new)`` for an embedding.

        - If a stored embedding has cosine similarity >= the threshold,
          returns its id and ``is_new=False``.
        - Otherwise mints a new id (``person_NNN``), persists it, and
          returns ``is_new=True``.

        ``similarity`` is the best similarity observed against the
        existing gallery (0.0 if the gallery was empty).
        """

        emb = np.asarray(embedding, dtype=np.float32).flatten()
        with self._lock:
            best_id: str | None = None
            best_sim: float = -1.0
            for rec in self._records:
                sim = _cosine(emb, rec.embedding)
                if sim > best_sim:
                    best_sim = sim
                    best_id = rec.person_id

            if best_id is not None and best_sim >= self._match_threshold:
                return best_id, best_sim, False

            new_id = self._mint_id_locked()
            self._records.append(_Record(person_id=new_id, embedding=emb.copy()))
            self._save_locked()
            sim_for_caller = best_sim if best_sim >= 0 else 0.0
            log.info("new person %s added to gallery (best prior sim %.3f)",
                     new_id, sim_for_caller, extra={"event": "new_person"})
            return new_id, sim_for_caller, True

    @logcall(level=logging.DEBUG)
    def labels_for_frame(
        self, embeddings: list[np.ndarray]
    ) -> list[tuple[str, float, bool]]:
        """Convenience: identify a whole frame's worth of faces at once."""

        return [self.identify(e) for e in embeddings]

    @logcall
    def count(self) -> int:
        with self._lock:
            return len(self._records)

    # --- private -------------------------------------------------------------

    @logcall
    def _mint_id_locked(self) -> str:
        new_id = f"person_{self._next_id:03d}"
        self._next_id += 1
        return new_id

    @logcall
    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
        except Exception as exc:
            print(
                f"[face_db] could not read {self._path}: {exc}; starting fresh.",
                flush=True,
            )
            return
        try:
            self._next_id = int(data.get("next_id", 1))
            for entry in data.get("people", []):
                self._records.append(
                    _Record(
                        person_id=str(entry["id"]),
                        embedding=_decode_embedding(entry["embedding"]),
                    )
                )
            log.info("gallery loaded: %d people from %s",
                     len(self._records), self._path, extra={"event": "db_loaded"})
        except Exception as exc:
            print(
                f"[face_db] {self._path} is malformed: {exc}; starting fresh.",
                flush=True,
            )
            self._records = []
            self._next_id = 1

    @logcall
    def _save_locked(self) -> None:
        # caller holds self._lock
        data = {
            "next_id": self._next_id,
            "people": [
                {"id": r.person_id, "embedding": _encode_embedding(r.embedding)}
                for r in self._records
            ],
        }
        payload = json.dumps(data, indent=2)
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
            print(f"[face_db] could not write {self._path}: {exc}", flush=True)
