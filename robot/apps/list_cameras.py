"""List the cameras this machine exposes, and preview one to identify it.

Use this once after mounting the external webcam on the robot's head, to see
which index/name the camera apps will pick and to confirm - by eye - that the
picked device is really the head camera and not the laptop's built-in one.

    python -m robot.apps.list_cameras              # list, and show the pick
    python -m robot.apps.list_cameras --probe      # also test-open each index
    python -m robot.apps.list_cameras --preview 1  # live window from index 1

The listed order is the order OpenCV enumerates, so the bracketed number is the
value to pass as ``CAMERA_DEVICE`` (a name substring works too, and survives an
iPhone Continuity Camera appearing and shifting the indices).
"""

from __future__ import annotations

import argparse
import os
import sys

import cv2

from robot.perception.camera_device import (
    CAMERA_DEVICE_ENV,
    describe_cameras,
    list_cameras,
    open_camera,
    probe_cameras,
    resolve_camera,
)
from robot.core.logsetup import setup_logging, logcall, get_logger

log = get_logger(__name__)


@logcall
def preview(index: int | str) -> None:
    """Show a live window from one camera until 'q'."""

    cap = open_camera(index)
    print("[preview] press 'q' in the window to close.", flush=True)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue
            mean = float(frame.mean())
            cv2.putText(
                frame, f"camera {index}  {frame.shape[1]}x{frame.shape[0]}  "
                f"mean={mean:.0f}  q=quit",
                (16, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2,
            )
            cv2.imshow(f"camera {index}", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


@logcall
def main() -> None:
    ap = argparse.ArgumentParser(description="List / preview camera devices.")
    ap.add_argument("--probe", action="store_true",
                    help="test-open each index (slow; releases each one)")
    ap.add_argument("--preview", metavar="INDEX_OR_NAME",
                    help="open a live preview window from this camera")
    args = ap.parse_args()

    setup_logging(run_name="list_cameras")

    if args.preview is not None:
        preview(args.preview)
        return

    cameras = list_cameras()
    print("Cameras (index order = OpenCV capture index):")
    print(describe_cameras(cameras))

    if args.probe:
        print("\nTest-opening each index (this can take a few seconds)...")
        openable = probe_cameras()
        print(f"  openable indices: {openable or 'none'}")
        listed = {c.index for c in cameras}
        extra = [i for i in openable if i not in listed]
        if extra:
            print(f"  (indices {extra} open but were not in the OS listing)")

    if not cameras:
        # Nothing was enumerated - on macOS that means the listing timed out
        # (the message above says so). Anything we print about "the camera the
        # apps will use" would be a guess dressed up as a fact.
        print("\nNo cameras could be listed, so there is nothing to preview and "
              "no index to trust yet. Fix the camera service first, then re-run "
              "this command.")
        return

    # The apps use ONLY an external camera unless a human names one, so with no
    # external attached resolve_camera refuses to pick. That is the right answer
    # for an app and the wrong one for a lister, whose whole job is to report -
    # so show the refusal as information and carry on.
    try:
        picked = resolve_camera(cameras=cameras)
    except SystemExit as exc:
        print(f"\n{exc}")
        return
    env = f" (from {CAMERA_DEVICE_ENV})" if os.environ.get(CAMERA_DEVICE_ENV) else ""
    print(f"\nThe camera apps will use: {picked.label()}{env}")
    if not picked.external and any(c.external for c in cameras):
        print("  NOTE: an external camera is present but not selected - "
              f"set {CAMERA_DEVICE_ENV} to its index or name.")
    if not picked.external:
        print("  NOTE: this is not an external camera. The apps only choose one "
              "automatically when it is external (the robot's eye is the webcam "
              "on its head); this one is in use because it was named explicitly.")
    print(f"\nConfirm it is the head camera:\n"
          f"  python -m robot.apps.list_cameras --preview {picked.index}\n"
          f"Override for a run:\n"
          f"  {CAMERA_DEVICE_ENV}={picked.index} python -m robot.apps.camera_remember")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[cameras] interrupted.", file=sys.stderr)
