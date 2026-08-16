"""Head sweep: look around the room before deciding who is present.

The camera is mounted on the Ohbot's **head**, so the robot can only see what
its head is pointed at - roughly the owner and whatever sits directly behind
them. A bystander two seats to the left is out of frame, and "no face in view"
then reads as "the owner is alone", which is the one wrong answer a
privacy-preserving disclosure gate must not give.

So before a sensitive reminder is delivered, the robot *turns its head* through
a few positions and looks at each one. Presence is decided over the whole
sweep: a bystander seen at any position counts as present. This mirrors what a
person does before saying something private - glance around the room first -
and it is legible to the participant, who sees the robot check.

Two things make the sweep more than "move, then grab a frame":

  * **Frames must be newer than the movement.** The camera rides the head, so
    every frame captured mid-turn is motion-blurred, and the capture pipeline is
    several frames deep. ``LatestFrame`` timestamps each frame as the main loop
    reads it, and the scanner waits for one captured *after* the head settled.
  * **The main loop must keep running.** It owns the capture and the preview
    window ('q' to quit), while the sweep runs on the delivery worker thread.
    The two meet only at ``LatestFrame``, which copies a frame just for the
    duration of a scan and costs nothing the rest of the time.

With ``NO_OHBOT=1`` (or ``HEAD_SCAN=0``) there is no head to turn, so a scan
degrades to a single look straight ahead - exactly the pre-sweep behavior.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from robot.core.logsetup import logcall, get_logger

log = get_logger(__name__)

# Env knobs, in the style of the other runtime switches (NO_OHBOT, CAMERA_DEVICE).
HEAD_SCAN_ENV = "HEAD_SCAN"                    # "0" -> never sweep, just look ahead
HEAD_SCAN_POSITIONS_ENV = "HEAD_SCAN_POSITIONS"  # e.g. "2,5,8"
HEAD_SCAN_SETTLE_ENV = "HEAD_SCAN_SETTLE_S"

# Debug only, and off unless set: write each sweep still to this directory so
# the settle time can be tuned by eye (a blurred or stale still means
# HEAD_SCAN_SETTLE_S is too short). This is the ONE place the system writes an
# image of anyone to disk - normal operation keeps only face embeddings - so
# treat a run with it enabled as recorded data, not as a demo.
HEAD_SCAN_SAVE_ENV = "HEAD_SCAN_SAVE_DIR"

# Ohbot HEADTURN units: 0 = fully one way, 10 = fully the other, 5 = straight
# ahead (its rest position). Left, centre, right covers the room without the
# sweep taking so long that the owner is left waiting on a due reminder.
HEAD_CENTRE = 5.0
DEFAULT_POSITIONS: tuple[float, ...] = (2.0, 5.0, 8.0)

# Seconds to let the servo travel and the picture stop shaking before a frame
# from the new position is trusted. The Ohbot SDK's move() returns immediately
# and reports no completion, so this is a wait, not a poll.
DEFAULT_SETTLE_S = 0.9

# How long to wait for a fresh frame once the head has settled, before giving up
# on that position and moving on (a stalled camera must not strand a delivery).
DEFAULT_FRAME_TIMEOUT_S = 2.0

# Ohbot move speed (0-10). Slower than the default 3 looks deliberate rather
# than twitchy, and shakes the head-mounted camera less on arrival.
SCAN_SPEED = 2


@dataclass(frozen=True)
class ScanShot:
    """One look: where the head was pointed, and what the camera saw there."""

    position: float
    frame: np.ndarray


class LatestFrame:
    """Hand-off of the newest camera frame from the main loop to a worker.

    ``set`` is called for every frame the main loop reads, so it does nothing at
    all unless a scan is in progress - no lock contention and no ~6 MB copy per
    frame in the common case.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._captured_at: float = 0.0
        self._new_frame = threading.Condition(self._lock)
        self._wanted = False

    def set(self, frame: np.ndarray) -> None:
        """Offer the newest frame. Cheap no-op while no scan is running."""

        if not self._wanted:
            return
        with self._new_frame:
            # Copy: OpenCV may hand back the same buffer on the next read(), and
            # the worker reads this frame long after the loop has moved on.
            self._frame = frame.copy()
            self._captured_at = time.monotonic()
            self._new_frame.notify_all()

    def start(self) -> None:
        """Begin retaining frames (called when a scan starts)."""

        with self._lock:
            self._frame = None
            self._captured_at = 0.0
        self._wanted = True

    def stop(self) -> None:
        """Stop retaining frames and release the last one."""

        self._wanted = False
        with self._lock:
            self._frame = None

    def get_after(self, moment: float, timeout: float) -> np.ndarray | None:
        """Wait for a frame captured after ``moment`` (a ``time.monotonic()``)."""

        deadline = time.monotonic() + timeout
        with self._new_frame:
            while self._frame is None or self._captured_at <= moment:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._new_frame.wait(remaining)
            return self._frame


def _positions_from_env() -> tuple[float, ...]:
    raw = os.environ.get(HEAD_SCAN_POSITIONS_ENV)
    if not raw:
        return DEFAULT_POSITIONS
    try:
        positions = tuple(float(p) for p in raw.split(",") if p.strip())
    except ValueError:
        raise SystemExit(
            f"[scan] {HEAD_SCAN_POSITIONS_ENV}={raw!r} is not a comma-separated "
            "list of HEADTURN positions (0-10), e.g. '2,5,8'."
        ) from None
    if not positions:
        return DEFAULT_POSITIONS
    if any(not 0.0 <= p <= 10.0 for p in positions):
        raise SystemExit(
            f"[scan] {HEAD_SCAN_POSITIONS_ENV}={raw!r} has a position outside the "
            "Ohbot HEADTURN range 0-10."
        )
    return positions


def _settle_from_env() -> float:
    raw = os.environ.get(HEAD_SCAN_SETTLE_ENV)
    if not raw:
        return DEFAULT_SETTLE_S
    try:
        return max(0.0, float(raw))
    except ValueError:
        raise SystemExit(
            f"[scan] {HEAD_SCAN_SETTLE_ENV}={raw!r} is not a number of seconds."
        ) from None


class HeadScanner:
    """Turn the head through several positions, collecting one frame at each.

    ``move_head`` is injected rather than importing the Ohbot SDK here: each app
    owns its own ``ohbot_lock`` and ``NO_OHBOT`` handling, and passing ``None``
    (no robot) is what makes the scan degrade to a single look ahead.
    """

    @logcall
    def __init__(
        self,
        latest: LatestFrame,
        move_head: Callable[[float], None] | None,
        *,
        positions: tuple[float, ...] | None = None,
        settle_s: float | None = None,
        frame_timeout_s: float = DEFAULT_FRAME_TIMEOUT_S,
        on_status: Callable[[str], None] | None = None,
        should_abort: Callable[[], bool] | None = None,
    ) -> None:
        self._latest = latest
        self._move_head = move_head
        self._positions = positions if positions is not None else _positions_from_env()
        self._settle_s = settle_s if settle_s is not None else _settle_from_env()
        self._frame_timeout_s = frame_timeout_s
        self._on_status = on_status
        self._should_abort = should_abort
        self._disabled = os.environ.get(HEAD_SCAN_ENV) == "0"

    @property
    def enabled(self) -> bool:
        """True when a sweep will actually move the head."""

        return bool(self._move_head) and not self._disabled and len(self._positions) > 1

    @property
    def positions(self) -> tuple[float, ...]:
        return self._positions

    def _status(self, message: str) -> None:
        if self._on_status is not None:
            self._on_status(message)

    def _aborted(self) -> bool:
        return bool(self._should_abort and self._should_abort())

    def _save_debug_shot(self, position: float, frame: np.ndarray) -> None:
        """Write one sweep still to HEAD_SCAN_SAVE_DIR, if that is set."""

        folder = os.environ.get(HEAD_SCAN_SAVE_ENV)
        if not folder:
            return
        import cv2  # noqa: PLC0415 - debug path only

        path = Path(folder)
        try:
            path.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%H%M%S")
            out = path / f"scan_{stamp}_pos{position:g}.jpg"
            cv2.imwrite(str(out), frame)
            print(f"[scan] wrote {out}", flush=True)
        except Exception as exc:  # noqa: BLE001 - debugging must never break a run
            print(f"[scan] could not write debug frame: {exc}", flush=True)

    @logcall
    def scan(self, fallback_frame: np.ndarray | None = None) -> list[ScanShot]:
        """Sweep the head and return what was seen at each position.

        Returns a single straight-ahead shot when there is no robot to move.
        Never raises for a missed frame: a position that yields nothing is
        skipped and reported, so a delivery still goes ahead on what was seen.
        """

        if not self.enabled:
            frame = fallback_frame
            if frame is None:
                self._latest.start()
                try:
                    frame = self._latest.get_after(0.0, self._frame_timeout_s)
                finally:
                    self._latest.stop()
            return [ScanShot(HEAD_CENTRE, frame)] if frame is not None else []

        shots: list[ScanShot] = []
        self._latest.start()
        try:
            for position in self._positions:
                if self._aborted():
                    break
                self._status(f"looking at head position {position:g}/10")
                print(f"[scan] turning head to {position:g}/10 ...", flush=True)
                self._move_head(position)
                time.sleep(self._settle_s)
                if self._aborted():
                    break
                # Only a frame captured after the head stopped shows this
                # position; anything older is the previous view or a blur.
                settled_at = time.monotonic()
                frame = self._latest.get_after(settled_at, self._frame_timeout_s)
                if frame is None:
                    print(f"[scan] no fresh frame at position {position:g}; "
                          "skipping it.", flush=True)
                    log.warning("no frame at head position %.1f", position,
                                extra={"event": "scan_frame_missed"})
                    continue
                shots.append(ScanShot(position, frame))
                self._save_debug_shot(position, frame)
        finally:
            self._latest.stop()
            # Always face forward again: the next thing the robot does is talk
            # to the owner, and a head left staring at the wall reads as broken.
            if self._move_head is not None and not self._aborted():
                self._move_head(HEAD_CENTRE)

        log.info("head scan collected %d view(s) at positions %s", len(shots),
                 [s.position for s in shots], extra={"event": "head_scan"})
        return shots
