"""YuNet face detection + SFace face embedding, wrapped for the demos.

Why this combo:
  - YuNet (cv2.FaceDetectorYN) is a small, accurate ONNX detector that
    ships with the opencv-python wheel. Replaces the demos' Haar cascade
    only where we need precise bounding boxes for embedding extraction
    (Haar still handles the cheap per-frame alone/not-alone count).
  - SFace (cv2.FaceRecognizerSF) produces 128-d L2-normalised face
    embeddings; cosine similarity threshold of ~0.363 is the standard
    same-person cutoff used by the OpenCV samples. Same family as
    FaceNet (Schroff et al. 2015) for the thesis-defensibility story.

Both models live as ONNX files. We auto-download them from the upstream
opencv_zoo repo into ``robot/state/models/`` on first use - no
pip extras, no compile step. The two files together are ~37 MB and are
gitignored (see ../../.gitignore).
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


from robot.paths import MODELS_DIR

# Two ONNX files we need. URLs point at a pinned commit so a future
# upstream rename doesn't break the demo.
YUNET_FILENAME = "face_detection_yunet_2023mar.onnx"
SFACE_FILENAME = "face_recognition_sface_2021dec.onnx"
YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/"
    "models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
SFACE_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/"
    "models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
)

# OpenCV-recommended cosine threshold: at or above this is the same
# person. Below it, treat as a new face. Tunable per lab lighting.
SFACE_COSINE_SAME_PERSON = 0.363

# Owner recognition uses a tighter threshold than generic bystander
# re-ID because a false positive on the owner is much more harmful
# (corrupts the cache key for an entire trial). False negatives just
# abort the trial cleanly so the user can re-position - cheap to
# recover from. Tune up if you see strangers being mis-IDed as the
# owner; tune down if the real owner is frequently rejected.
SFACE_OWNER_THRESHOLD = 0.50


@dataclass
class DetectedFace:
    """One detected face from a single frame."""

    bbox: tuple[int, int, int, int]  # (x, y, w, h)
    landmarks: np.ndarray  # raw 5-point landmarks YuNet emits
    confidence: float
    embedding: np.ndarray  # 128-d float32, L2-normalised by SFace

    @property
    def area(self) -> int:
        return int(self.bbox[2] * self.bbox[3])


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"[face_id] downloading {dest.name} from {url} ...", flush=True)
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            written = 0
            chunk = 64 * 1024
            with open(tmp, "wb") as f:
                while True:
                    buf = resp.read(chunk)
                    if not buf:
                        break
                    f.write(buf)
                    written += len(buf)
                    if total:
                        pct = 100 * written / total
                        sys.stdout.write(
                            f"\r[face_id]   {written/1e6:.1f}/"
                            f"{total/1e6:.1f} MB ({pct:.0f}%)"
                        )
                        sys.stdout.flush()
        sys.stdout.write("\n")
        os.replace(tmp, dest)
    except (urllib.error.URLError, TimeoutError) as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise SystemExit(
            f"[face_id] could not download {url}: {exc}.\n"
            f"Manually save the file to {dest} and rerun."
        ) from exc


def ensure_models() -> tuple[Path, Path]:
    """Returns the on-disk paths of the YuNet and SFace ONNX models.

    Downloads them on first call. Subsequent calls just verify the
    files exist and return their paths. Run this at startup so the
    demo's main loop never blocks on network I/O.

    Also sweeps any orphan ``*.part`` files left behind by a prior
    download that was killed mid-transfer (SIGKILL bypasses the
    download's own exception cleanup). Safe to remove unconditionally:
    the next download writes via mkstemp + atomic ``os.replace``, so
    the real model files are never half-written.
    """

    yunet = MODELS_DIR / YUNET_FILENAME
    sface = MODELS_DIR / SFACE_FILENAME
    if MODELS_DIR.exists():
        for orphan in MODELS_DIR.glob("*.part"):
            try:
                orphan.unlink()
                print(f"[face_id] removed orphan partial download {orphan.name}")
            except OSError:
                pass
    if not yunet.exists():
        _download(YUNET_URL, yunet)
    if not sface.exists():
        _download(SFACE_URL, sface)
    return yunet, sface


class FaceIdentifier:
    """Detect + embed faces in a BGR frame.

    Thread-safety: the underlying OpenCV detector/recognizer objects
    are not documented as thread-safe. The demos only call
    ``detect_and_embed`` from a single worker at a time (guarded by
    ``trial_lock`` + ``in_trial``), so no extra lock here.
    """

    def __init__(
        self,
        yunet_path: Path,
        sface_path: Path,
        score_threshold: float = 0.9,
        nms_threshold: float = 0.3,
        top_k: int = 5000,
    ) -> None:
        # Input size is reset per-frame; (320, 320) is just a sane default.
        self._detector = cv2.FaceDetectorYN.create(
            str(yunet_path),
            "",
            (320, 320),
            score_threshold,
            nms_threshold,
            top_k,
        )
        self._recognizer = cv2.FaceRecognizerSF.create(str(sface_path), "")

    def detect_and_embed(self, frame_bgr: np.ndarray) -> list[DetectedFace]:
        """Run detection + embedding on a single BGR frame."""

        h, w = frame_bgr.shape[:2]
        self._detector.setInputSize((w, h))
        _, raw = self._detector.detect(frame_bgr)
        if raw is None:
            return []

        out: list[DetectedFace] = []
        for row in raw:
            # YuNet output row: [x, y, w, h, le_x, le_y, re_x, re_y,
            # nose_x, nose_y, ml_x, ml_y, mr_x, mr_y, score]
            x, y, fw, fh = (int(v) for v in row[:4])
            score = float(row[-1])
            if fw <= 0 or fh <= 0:
                continue
            try:
                aligned = self._recognizer.alignCrop(frame_bgr, row)
                feature = self._recognizer.feature(aligned)
            except cv2.error:
                # Alignment can fail when a face sits half off-frame.
                continue
            emb = np.asarray(feature, dtype=np.float32).flatten()
            out.append(
                DetectedFace(
                    bbox=(x, y, fw, fh),
                    landmarks=np.asarray(row[4:14], dtype=np.float32),
                    confidence=score,
                    embedding=emb,
                )
            )
        return out
