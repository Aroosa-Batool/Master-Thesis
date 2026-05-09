"""Phase 3 demo: presence + real heart rate from the Bangle.js watch.

Combines:
  - Laptop webcam face count (alone vs. not alone)
  - Live heart rate from the watch via BLE (hrm_broadcast.js + bleak)
  - Ohbot disclosure behaviors

Decision rules:
  - bpm <= ELEVATED_BPM           : robot stays idle
  - bpm >  ELEVATED_BPM, alone    : full disclosure (Ohbot speaks the
                                    private wellbeing message)
  - bpm >  ELEVATED_BPM, !alone   : no disclosure (Ohbot greets neutrally;
                                    a printed line stands in for the
                                    eventual handoff to the watch)

Prereqs:
  - hrm_broadcast.js running on the Bangle.js (and saved with save()).
  - Watch worn snug, HRM has produced at least one confident reading.
  - Espruino Web IDE disconnected (only one BLE master at a time).
  - Ohbot connected via USB.

Run:
    python interface/presence/demo_with_watch.py
Press 'q' in the camera window to quit.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque

import cv2

try:
    from bleak import BleakClient, BleakScanner
except ModuleNotFoundError as exc:
    raise SystemExit("Missing dependency: install with `pip install bleak`.") from exc

try:
    from ohbot import ohbot
except ModuleNotFoundError as exc:
    raise SystemExit("Missing dependency: install with `pip install ohbot`.") from exc


ALONE_THRESHOLD = 1
# Sliding window over face-count observations: the robot decides on the trend,
# not on flicker. Robot stays quiet if the window is in the in-between band.
OBSERVATION_WINDOW_S = 15.0
ALONE_FRACTION_HIGH = 0.7   # >= this fraction of frames alone -> ALONE verdict
ALONE_FRACTION_LOW = 0.3    # <= this fraction of frames alone -> NOT ALONE verdict
ELEVATED_BPM = 100          # threshold above which the user counts as "elevated"
MIN_ELEVATED_DWELL_S = 5.0  # bpm must stay above ELEVATED_BPM for this long
HR_STALE_S = 10.0           # ignore cached bpm if the watch hasn't pushed in this long
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"


class HeartRateState:
    """Tiny thread-safe slot. BLE thread writes, camera thread reads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._bpm = 0
        self._last_update = 0.0

    def set(self, bpm: int) -> None:
        with self._lock:
            self._bpm = bpm
            self._last_update = time.monotonic()

    def get(self) -> tuple[int, float]:
        with self._lock:
            return self._bpm, self._last_update


hr_state = HeartRateState()


def parse_hr(data: bytearray) -> int:
    flags = data[0]
    if flags & 0x01:
        return int.from_bytes(data[1:3], byteorder="little")
    return data[1]


async def ble_loop() -> None:
    print("[ble] scanning for Bangle.js...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, adv: bool(d.name and "bangle" in d.name.lower()),
        timeout=15.0,
    )
    if device is None:
        print("[ble] watch not found. Demo will run with bpm=0 (idle).")
        return
    print(f"[ble] connecting to {device.name} ({device.address})...")
    async with BleakClient(device) as client:
        await client.start_notify(
            HR_MEASUREMENT_UUID,
            lambda _sender, data: hr_state.set(parse_hr(data)),
        )
        print("[ble] subscribed to heart-rate notifications.")
        while True:
            await asyncio.sleep(60)


def start_ble_thread() -> None:
    def runner() -> None:
        try:
            asyncio.run(ble_loop())
        except Exception as exc:
            print(f"[ble] thread crashed: {exc}")

    threading.Thread(target=runner, daemon=True).start()


def behavior_full_disclosure(bpm: int) -> None:
    print(f">>> ALONE + elevated ({bpm} bpm) -> full disclosure")
    ohbot.move(ohbot.HEADTURN, 5)
    ohbot.move(ohbot.HEADNOD, 5)
    ohbot.say(
        f"I noticed your heart rate is around {bpm}. "
        "Would you like to take a few deep breaths together?",
        untilDone=False,
        lipSync=True,
    )


def behavior_no_disclosure(bpm: int) -> None:
    print(f">>> NOT ALONE + elevated ({bpm} bpm) -> no disclosure")
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

    start_ble_thread()

    print(
        f"Demo running. Observing for ~{int(OBSERVATION_WINDOW_S)}s before "
        "speaking, then only when the verdict changes. Press 'q' to quit."
    )

    observations: deque[tuple[float, bool]] = deque()
    elevated_since: float | None = None
    spoken_action: str | None = None  # "alone_full" / "not_alone_no" / "idle"

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

            bpm, last_hr_ts = hr_state.get()
            fresh = (now - last_hr_ts) < HR_STALE_S
            if fresh and bpm > ELEVATED_BPM:
                if elevated_since is None:
                    elevated_since = now
            else:
                elevated_since = None
            elevated_stable = (
                elevated_since is not None
                and (now - elevated_since) >= MIN_ELEVATED_DWELL_S
            )

            presence_verdict: str | None = None
            if have_full_window:
                if fraction_alone >= ALONE_FRACTION_HIGH:
                    presence_verdict = "ALONE"
                elif fraction_alone <= ALONE_FRACTION_LOW:
                    presence_verdict = "NOT ALONE"

            if not have_full_window:
                action: str | None = None
            elif presence_verdict == "ALONE" and elevated_stable:
                action = "alone_full"
            elif presence_verdict == "NOT ALONE" and elevated_stable:
                action = "not_alone_no"
            else:
                action = "idle"

            if action and action != spoken_action:
                if action == "alone_full":
                    behavior_full_disclosure(bpm)
                elif action == "not_alone_no":
                    behavior_no_disclosure(bpm)
                # "idle" -> stay quiet, just record the transition.
                spoken_action = action

            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            raw_label = "ALONE" if is_alone else "NOT ALONE"
            line1 = (
                f"raw: {raw_label}  faces={count}  "
                f"bpm={bpm if fresh else '--'}"
            )
            if have_full_window:
                line2 = (
                    f"window {duration:.0f}s  {fraction_alone:.0%} alone  "
                    f"verdict={presence_verdict or 'ambiguous'}  "
                    f"elevated={elevated_stable}"
                )
            else:
                line2 = (
                    f"observing... {duration:.0f}/{int(OBSERVATION_WINDOW_S)}s"
                )
            line3 = f"action: {action or '...'}  spoken: {spoken_action or '(none)'}"
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
            cv2.imshow("Presence + watch demo", frame)

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
