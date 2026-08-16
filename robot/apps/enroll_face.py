"""One-shot owner enrollment for the consent demo.

Captures the watch-wearer's face from the webcam and writes the
averaged SFace embedding to ``owner_face.json``. After this runs once,
``camera_remember.py`` can tell the owner
apart from bystanders in the camera frame, which is what makes the
"remember Anna's decision next time Anna is in the room" behavior
robust (without owner filtering, the cache key would change every
time the owner glanced away from the camera).

Capture procedure:
  - Opens the webcam with a live preview.
  - Asks you to sit alone in front of the camera, looking at it.
  - Captures TARGET_SAMPLES (default 12) embeddings, spaced ~300 ms
    apart, ONLY from frames that contain exactly one face. If a frame
    has zero or 2+ faces, the sample counter holds (it doesn't reset)
    so a brief detection glitch is tolerated, but persistent multi-
    face frames stall the capture and surface the issue to you.
  - On enough samples, averages the embeddings and writes the file.
  - Then enters a brief "verify" loop that draws the live similarity
    of any detected face vs. the saved owner embedding, so you can
    sanity-check it before exiting.

Run:
    python -m robot.apps.enroll_face

Press 'q' at any time to abort. Re-run to re-enroll (will overwrite).
"""

from __future__ import annotations

import datetime
import logging
import os
import sys
import time

import cv2
import numpy as np

from robot.perception.camera_device import open_camera
from robot.perception.face_id import FaceIdentifier, SFACE_COSINE_SAME_PERSON, ensure_models
from robot.core.owner import OwnerStore
from robot.core.logsetup import setup_logging, logcall, get_logger
from robot.core import presentation_telemetry as telemetry


from robot.paths import OWNER_FACE_PATH

log = get_logger(__name__)

TARGET_SAMPLES = 12
SAMPLE_INTERVAL_S = 0.30
# Drop the minimum-confidence face cutoff for enrollment: we want
# good samples, not borderline ones. The demos use the YuNet default
# (0.9) which we keep here.
MIN_FACE_SCORE = 0.9
# Reject samples whose largest face is smaller than this fraction of
# the frame area - enforces "sit close to the camera, look at it".
MIN_FACE_AREA_FRAC = 0.01
UI_JOB = os.environ.get("THESIS_UI_JOB") == "1"


@logcall(level=logging.DEBUG)
def draw_status(
    frame: np.ndarray,
    lines: list[tuple[str, tuple[int, int, int]]],
) -> None:
    for i, (text, color) in enumerate(lines):
        cv2.putText(
            frame,
            text,
            (20, 36 + i * 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            color,
            2,
        )


@logcall
def capture_owner_samples(
    cap: cv2.VideoCapture,
    identifier: FaceIdentifier,
) -> list[np.ndarray]:
    """Run the capture loop. Returns the collected embeddings.

    Returns an empty list if the user aborts with 'q'.
    """

    log.info("owner face capture started (target %d samples)", TARGET_SAMPLES,
             extra={"event": "capture_started"})
    samples: list[np.ndarray] = []
    last_sample_at: float = 0.0
    last_face_count: int = 0

    while len(samples) < TARGET_SAMPLES:
        ok, frame = cap.read()
        if not ok:
            continue
        now = time.monotonic()
        faces = identifier.detect_and_embed(frame)
        last_face_count = len(faces)
        h, w = frame.shape[:2]
        frame_area = h * w

        eligible_face = None
        if len(faces) == 1 and faces[0].confidence >= MIN_FACE_SCORE:
            face = faces[0]
            if (face.area / frame_area) >= MIN_FACE_AREA_FRAC:
                eligible_face = face

        if eligible_face is not None and (now - last_sample_at) >= SAMPLE_INTERVAL_S:
            samples.append(eligible_face.embedding.copy())
            last_sample_at = now
            print(
                f"[enroll] captured sample {len(samples)}/{TARGET_SAMPLES} "
                f"(face score={eligible_face.confidence:.2f})",
                flush=True,
            )
            log.info("captured sample %d/%d (face score=%.2f)", len(samples),
                     TARGET_SAMPLES, eligible_face.confidence,
                     extra={"event": "sample_captured"})

        # HUD overlay
        for face in faces:
            x, y, fw, fh = face.bbox
            color = (0, 255, 0) if eligible_face is face else (0, 165, 255)
            cv2.rectangle(frame, (x, y), (x + fw, y + fh), color, 2)

        if len(faces) == 0:
            msg = ("No face detected. Look at the camera.", (0, 0, 255))
        elif len(faces) > 1:
            msg = (
                f"{len(faces)} faces in frame. Be ALONE for enrollment.",
                (0, 0, 255),
            )
        elif eligible_face is None:
            msg = (
                "Face too small or low confidence. Sit closer / steady.",
                (0, 165, 255),
            )
        else:
            msg = ("Capturing... hold still.", (0, 255, 0))

        draw_status(
            frame,
            [
                (
                    f"Owner enrollment - sample {len(samples)}/{TARGET_SAMPLES}",
                    (255, 255, 255),
                ),
                msg,
                ("'q' to abort", (200, 200, 200)),
            ],
        )
        telemetry.frame(frame, max_fps=6.0)
        telemetry.emit(
            "job_progress", progress=len(samples) / TARGET_SAMPLES,
            detail=f"Face samples: {len(samples)}/{TARGET_SAMPLES}",
        )
        if not UI_JOB:
            cv2.imshow("Owner enrollment", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                return []

    print(
        f"[enroll] captured {len(samples)} samples; "
        f"(last frame had {last_face_count} face(s))",
        flush=True,
    )
    return samples


@logcall
def verify_loop(
    cap: cv2.VideoCapture,
    identifier: FaceIdentifier,
    store: OwnerStore,
) -> None:
    """After enrollment, show live cosine similarity to the saved owner.

    Lets you eyeball whether the threshold (0.363) discriminates you
    from background props / other people if anyone walks in.
    """

    print(
        "[enroll] verify loop running. Move around, have someone else step "
        "in, then press 'q' to exit.",
        flush=True,
    )
    verify_started = time.monotonic()
    while True:
        ok, frame = cap.read()
        if not ok:
            continue
        faces = identifier.detect_and_embed(frame)
        for face in faces:
            is_owner, sim = store.matches(
                face.embedding, threshold=SFACE_COSINE_SAME_PERSON
            )
            color = (0, 255, 0) if is_owner else (0, 0, 255)
            label = f"{'OWNER' if is_owner else 'other'}  sim={sim:.2f}"
            x, y, fw, fh = face.bbox
            cv2.rectangle(frame, (x, y), (x + fw, y + fh), color, 2)
            cv2.putText(
                frame,
                label,
                (x, max(20, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
            )
        draw_status(
            frame,
            [
                (
                    f"Verify - threshold sim >= {SFACE_COSINE_SAME_PERSON:.2f} = OWNER",
                    (255, 255, 255),
                ),
                ("'q' to exit", (200, 200, 200)),
            ],
        )
        telemetry.frame(frame, max_fps=6.0)
        if UI_JOB and time.monotonic() - verify_started >= 8.0:
            return
        if not UI_JOB:
            cv2.imshow("Owner enrollment", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                return


@logcall
def main() -> None:
    setup_logging(run_name="enroll_face")
    print("[enroll] preparing face detector + recogniser (YuNet + SFace)...", flush=True)
    yunet, sface = ensure_models()
    identifier = FaceIdentifier(yunet, sface)
    store = OwnerStore(OWNER_FACE_PATH)

    if store.has_owner():
        print(
            f"[enroll] An owner is already enrolled "
            f"(samples={store.samples()}, at={store.enrolled_at()}).",
            flush=True,
        )
        if UI_JOB:
            reply = "yes" if os.environ.get("THESIS_UI_OVERWRITE") == "1" else ""
        else:
            try:
                reply = input(
                    "Type 'yes' to OVERWRITE the existing enrollment, "
                    "anything else to cancel: "
                ).strip().lower()
            except EOFError:
                reply = ""
        if reply != "yes":
            print("[enroll] cancelled; existing enrollment kept.", flush=True)
            return

    print("[enroll] opening webcam...", flush=True)
    # Enrol through the SAME camera the apps will recognise you with: lens and
    # mounting height change the embedding enough to matter at the owner
    # threshold, so a built-in-camera enrollment ages badly on the head camera.
    cap = open_camera()
    telemetry.sensor("camera", True)

    try:
        samples = capture_owner_samples(cap, identifier)
        if not samples:
            print("[enroll] aborted; no enrollment written.", flush=True)
            return

        mean = np.mean(np.stack(samples, axis=0), axis=0)
        # OwnerStore.save() re-normalises to unit length internally.
        enrolled_at = datetime.datetime.now().isoformat(timespec="seconds")
        store.save(mean, samples=len(samples), enrolled_at=enrolled_at)
        print(
            f"[enroll] wrote {OWNER_FACE_PATH} ({len(samples)} samples).",
            flush=True,
        )
        log.info("owner enrolled with %d samples", len(samples),
                 extra={"event": "owner_enrolled"})

        verify_loop(cap, identifier, store)
        telemetry.emit("job_result", result="Face enrollment and verification complete")
    finally:
        cap.release()
        telemetry.sensor("camera", False)
        telemetry.clear_frame()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[enroll] interrupted.", file=sys.stderr)
