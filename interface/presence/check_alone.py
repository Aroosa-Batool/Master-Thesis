"""Presence check: counts faces from the laptop webcam.

Step one of "make the robot react differently when the user is alone vs.
with others". This script does not talk to the Ohbot yet — it only prints
ALONE or NOT ALONE so we can confirm the camera + face detection are
reliable before wiring anything else up.

Run:
    python interface/presence/check_alone.py
Press 'q' in the video window to quit.
"""

from __future__ import annotations

import cv2


ALONE_THRESHOLD = 1  # 1 face = alone; 2+ = someone else is here.


def main() -> None:
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)
    if face_cascade.empty():
        raise SystemExit(f"Could not load face detector from {cascade_path}.")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise SystemExit(
            "Could not open webcam. Close any app using the camera "
            "(Zoom, Teams, browser tabs) and try again."
        )

    print("Webcam started. Press 'q' in the video window to quit.")
    last_state: str | None = None

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.2,
                minNeighbors=5,
                minSize=(60, 60),
            )

            count = len(faces)
            state = "ALONE" if count <= ALONE_THRESHOLD else "NOT ALONE"
            if state != last_state:
                print(f"presence: {state} (faces detected: {count})")
                last_state = state

            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(
                frame,
                f"{state}  (faces: {count})",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 0),
                2,
            )
            cv2.imshow("Presence check", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
