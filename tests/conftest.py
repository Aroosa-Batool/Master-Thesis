"""Shared hardware-free fakes for the reminder-pipeline tests.

Every test in this suite runs WITHOUT a microphone, webcam, watch, Ohbot,
downloaded model, or network: the heavy collaborators (sounddevice, the BLE
client, the identifiers, the speech/behaviour functions in ``robot_io``) are
replaced with the fakes below via monkeypatching. Importing the engine modules
does import their libraries (torch, OpenCV, bleak, the Ohbot SDK), but never
constructs a model or opens a device.
"""

from __future__ import annotations

import datetime
import os

# The third-party Ohbot package opens a serial port at import time on some
# versions.  All tests use fakes and must remain hardware-free.
os.environ.setdefault("NO_OHBOT", "1")

import numpy as np
import pytest

from robot.core.reminders import Reminder


class FakeWatch:
    """Stands in for ``policy.BangleClient``: scripted presence + answers.

    ``connected`` may be a bool or a list of bools consumed one per
    ``is_connected()`` call (the last value then repeats), so a test can model
    "present at the start, gone at delivery time".
    """

    def __init__(self, connected=True, answer=None):
        self._connected = connected if isinstance(connected, list) else [connected]
        self.answer = answer
        self.asked: list[str] = []
        self.notified: list[str] = []

    def is_connected(self) -> bool:
        if len(self._connected) > 1:
            return self._connected.pop(0)
        return self._connected[0]

    def ask_consent(self, message: str, timeout: float = 30.0):
        self.asked.append(message)
        return self.answer

    def notify(self, message: str) -> None:
        self.notified.append(message)


class Spy:
    """Callable that records its calls and returns a fixed value."""

    def __init__(self, result=None):
        self.calls: list[tuple] = []
        self.result = result

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result

    @property
    def called(self) -> bool:
        return bool(self.calls)


def make_reminder(rem_id="rem_001", text="doctor's appointment",
                  due_in_s=0.0, sensitive=True) -> Reminder:
    due = datetime.datetime.now() + datetime.timedelta(seconds=due_in_s)
    return Reminder(id=rem_id, text=text,
                    remind_at=due.isoformat(timespec="seconds"),
                    sensitive=sensitive)


@pytest.fixture
def silence():
    """One second of silent mono audio at the pipeline's sample rate."""

    return np.zeros(16000, dtype=np.float32)


@pytest.fixture
def quiet_voice_engine(monkeypatch):
    """Silence the speech/robot side effects of the voice engine and robot_io.

    Returns a dict of spies so tests can assert what would have been spoken.
    """

    import robot.core.robot_io as demo
    import robot.core.voice_reminder as vr

    spies = {
        "spoken": Spy(),      # deliver_reminder_spoken(text)
        "withheld": Spy(),    # behavior_withhold()
    }
    monkeypatch.setattr(demo, "deliver_reminder_spoken", spies["spoken"])
    monkeypatch.setattr(demo, "behavior_withhold", spies["withheld"])
    # Speed: idle waits poll every 0.05 s instead of seconds.
    monkeypatch.setattr(vr, "DEFAULT_POLL_S", 0.05)
    return spies
