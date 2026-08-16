"""Who is in view - over one frame, or over a whole head sweep.

Both camera apps ask the same question before disclosing a sensitive reminder:
*is anyone here besides the owner, and who?* This module answers it, and the
head sweep (``robot.core.head_scan``) is why it takes a list of frames rather
than one.

The subtlety a sweep introduces is **double counting**. The head turns through
overlapping views, so one bystander is very likely photographed twice; running
the gallery on every face independently would mint two IDs for them and produce
the bystander key ``person_004:person_005`` for a single human. In
``camera_remember`` that key IS the consent cache key, so the owner's
remembered "yes, you may speak in front of Anna" would never be found again.

So faces are clustered across frames before any of them is given an identity:

  * two faces from **different** frames are the same person when their SFace
    embeddings are at or above ``SFACE_COSINE_SAME_PERSON``;
  * two faces from the **same** frame are never merged - the detector found two
    faces in one image, so there are two people, however alike they look.

Each cluster is then identified once, using its largest (closest, least
distorted) face. With a single frame there is nothing to merge and the result
is identical to identifying each face directly.

Owner handling is unchanged: the owner's presence in the room is established by
the watch's BLE link, not the camera, so the owner may or may not be seen. If a
cluster matches the owner template above ``SFACE_OWNER_THRESHOLD`` it is
filtered out of the bystander key; everyone else is a bystander.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from robot.core.logsetup import logcall, get_logger
from robot.core.owner import OwnerStore
from robot.perception.face_db import FaceDB
from robot.perception.face_id import (
    DetectedFace,
    FaceIdentifier,
    SFACE_COSINE_SAME_PERSON,
    SFACE_OWNER_THRESHOLD,
)

log = get_logger(__name__)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a)) * float(np.linalg.norm(b))
    if denom <= 1e-12:
        return 0.0
    return float(np.dot(a, b) / denom)


@dataclass
class _Cluster:
    """One person, as seen across the sweep."""

    best: DetectedFace           # largest sighting - the one we identify from
    frames: set[int] = field(default_factory=set)

    @property
    def embedding(self) -> np.ndarray:
        return self.best.embedding

    def add(self, face: DetectedFace, frame_index: int) -> None:
        self.frames.add(frame_index)
        if face.area > self.best.area:
            self.best = face


def _cluster_faces(
    per_frame: list[list[DetectedFace]],
    threshold: float = SFACE_COSINE_SAME_PERSON,
) -> list[_Cluster]:
    """Group sightings of the same person across frames, never within one."""

    clusters: list[_Cluster] = []
    for frame_index, faces in enumerate(per_frame):
        for face in faces:
            best_cluster: _Cluster | None = None
            best_sim = threshold
            for cluster in clusters:
                # Same frame => a different person by construction.
                if frame_index in cluster.frames:
                    continue
                sim = _cosine(face.embedding, cluster.embedding)
                if sim >= best_sim:
                    best_sim = sim
                    best_cluster = cluster
            if best_cluster is None:
                clusters.append(_Cluster(best=face, frames={frame_index}))
            else:
                best_cluster.add(face, frame_index)
    return clusters


@logcall
def identify_people_in_frames(
    face_identifier: FaceIdentifier,
    face_db: FaceDB,
    owner_store: OwnerStore,
    frames: list[np.ndarray],
) -> tuple[str, list[tuple[str, float, bool, bool]], bool]:
    """Identify everyone visible across ``frames``.

    Returns ``(bystander_id, per_person, owner_detected)``:

    - ``bystander_id`` is the consent-cache key: a colon-joined sorted set of
      the person IDs of the NON-OWNER people seen anywhere in the sweep.
    - ``per_person`` is one ``(person_id, similarity, is_new, is_owner)`` tuple
      per distinct person, largest face first.
    - ``owner_detected`` is True iff one of them matched the owner template.
    """

    per_frame = []
    for frame in frames:
        if frame is None:
            continue
        faces = face_identifier.detect_and_embed(frame)
        per_frame.append(faces)

    clusters = _cluster_faces(per_frame)
    if not clusters:
        return "", [], False

    # Largest face first: closest to the camera, and a stable render order.
    clusters.sort(key=lambda c: c.best.area, reverse=True)

    if len(frames) > 1:
        merged = sum(len(f) for f in per_frame) - len(clusters)
        if merged > 0:
            log.info("head scan: %d sighting(s) merged into %d person(s)",
                     merged + len(clusters), len(clusters),
                     extra={"event": "sightings_merged"})

    # Score every person against the owner template once, then take the best
    # match above the threshold as the owner (at most one owner is present).
    owner_scores = [
        owner_store.matches(c.embedding, threshold=SFACE_OWNER_THRESHOLD)
        for c in clusters
    ]
    owner_idx = -1
    best_sim = SFACE_OWNER_THRESHOLD
    for i, (is_owner, sim) in enumerate(owner_scores):
        if is_owner and sim >= best_sim:
            best_sim = sim
            owner_idx = i

    per_person: list[tuple[str, float, bool, bool]] = []
    bystanders: list[str] = []
    for i, cluster in enumerate(clusters):
        if i == owner_idx:
            per_person.append(("owner", owner_scores[i][1], False, True))
            continue
        pid, sim, is_new = face_db.identify(cluster.embedding)
        per_person.append((pid, sim, is_new, False))
        bystanders.append(pid)

    return ":".join(sorted(set(bystanders))), per_person, owner_idx >= 0
