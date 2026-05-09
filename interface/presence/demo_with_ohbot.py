"""Phase 2: presence-aware Ohbot demo.

Combines the laptop-webcam face counter from check_alone.py with the Ohbot.
When the user is alone, the robot delivers a private wellbeing message out
loud (full disclosure). When someone else is in the room, the robot greets
neutrally and the private content is held back (no disclosure — and a
printed line stands in for the future handoff to the Bangle.js watch).

Run:
    python interface/presence/demo_with_ohbot.py
Press 'q' in the video window to quit.
"""

from __future__ import annotations

import time
from collections import deque

import cv2

try:
    from ohbot import ohbot
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: install the Ohbot SDK with `pip install ohbot`."
    ) from exc


ALONE_THRESHOLD = 1
# Smooth raw frame-by-frame face counts over a sliding window so the robot
# decides on the *trend*, not on flicker. The robot only speaks when the
# window is decisively alone or decisively not-alone; the in-between band
# is treated as ambiguous and the robot stays quiet.
OBSERVATION_WINDOW_S = 25.0
ALONE_FRACTION_HIGH = 0.7  # >= this -> ALONE verdict
ALONE_FRACTION_LOW = 0.3   # <= this -> NOT ALONE verdict


def behavior_alone() -> None:
    print(">>> ALONE  -> full disclosure")
    ohbot.move(ohbot.HEADTURN, 5)
    ohbot.move(ohbot.HEADNOD, 5)
    ohbot.say(
        "I noticed your heart rate has been a bit elevated. "
        "Would you like to take a few deep breaths together?",
        untilDone=False,
        lipSync=True,
    )


def behavior_not_alone() -> None:
    print(">>> NOT ALONE  -> no disclosure (private content held back)")
    print("    [watch handoff] sensitive content would route to the Bangle.js")
    ohbot.move(ohbot.HEADTURN, 5)
    ohbot.say("Hello there.", untilDone=False, lipSync=True)


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

    ohbot.init()
    ohbot.reset()
    ohbot.setVoice(language="en-GB", gender="Female")

    print(
        f"Demo running. Observing for ~{int(OBSERVATION_WINDOW_S)}s before "
        "speaking, then only when the verdict changes. "
        "Press 'q' in the video window to quit."
    )

    observations: deque[tuple[float, bool]] = deque()
    spoken_verdict: str | None = None

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue

            now = time.monotonic()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.2,
                minNeighbors=5,
                minSize=(60, 60),
            )
            count = len(faces)
            is_alone = count <= ALONE_THRESHOLD

            observations.append((now, is_alone))
            while observations and observations[0][0] < now - OBSERVATION_WINDOW_S:
                observations.popleft()

            duration = observations[-1][0] - observations[0][0]
            fraction_alone = (
                sum(1 for _, a in observations if a) / len(observations)
            )
            have_full_window = duration >= OBSERVATION_WINDOW_S * 0.9

            verdict: str | None = None
            if have_full_window:
                if fraction_alone >= ALONE_FRACTION_HIGH:
                    verdict = "ALONE"
                elif fraction_alone <= ALONE_FRACTION_LOW:
                    verdict = "NOT ALONE"

            if verdict and verdict != spoken_verdict:
                if verdict == "ALONE":
                    behavior_alone()
                else:
                    behavior_not_alone()
                spoken_verdict = verdict

            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            raw_label = "ALONE" if is_alone else "NOT ALONE"
            line1 = f"raw: {raw_label}  faces={count}"
            if have_full_window:
                line2 = (
                    f"window {duration:.0f}s  {fraction_alone:.0%} alone  "
                    f"verdict={verdict or 'ambiguous'}"
                )
            else:
                line2 = f"observing... {duration:.0f}/{int(OBSERVATION_WINDOW_S)}s"
            line3 = f"spoken: {spoken_verdict or '(none yet)'}"
            for i, line in enumerate((line1, line2, line3)):
                cv2.putText(
                    frame,
                    line,
                    (20, 40 + i * 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2,
                )
            cv2.imshow("Presence-aware demo", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        try:
            ohbot.reset()
        finally:
            ohbot.close()


if __name__ == "__main__":
    main()
