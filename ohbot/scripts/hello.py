"""Ohbot full smoke test.

Exercises all supported "basic" Ohbot functionalities that are exposed by the
official `ohbot` Python package:

- Connection init + reset
- Motor channels: head turn, head nod, eye turn, eye tilt, lid blink, top lip,
  bottom lip
- Speech output (with and without lip-sync)

This is intended as a *hardware* sanity check, not a unit test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


try:
    from ohbot import ohbot
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: install the Ohbot SDK with `python -m pip install ohbot`."
    ) from exc


@dataclass(frozen=True)
class MotorTest:
    name: str
    motor_id: int
    positions: tuple[int, int, int]
    speed: int = 5
    eye: int = 0


def _sweep_motor(test: MotorTest, *, wait_s: float = 0.5) -> None:
    low, high, mid = test.positions
    ohbot.move(test.motor_id, low, spd=test.speed, eye=test.eye)
    ohbot.wait(wait_s)
    ohbot.move(test.motor_id, high, spd=test.speed, eye=test.eye)
    ohbot.wait(wait_s)
    ohbot.move(test.motor_id, mid, spd=test.speed, eye=test.eye)
    ohbot.wait(wait_s)


def main() -> None:
    # Conservative ranges: the SDK commonly uses 0-10, with ~5 as neutral.
    # We avoid extremes to reduce the chance of stalling or mechanical strain.
    safe_low = 2
    safe_high = 8
    neutral = 5

    motor_tests: Iterable[MotorTest] = (
        MotorTest("head turn", ohbot.HEADTURN, (safe_low, safe_high, neutral)),
        MotorTest("head nod", ohbot.HEADNOD, (safe_low, safe_high, neutral)),
        MotorTest("eye turn", ohbot.EYETURN, (safe_low, safe_high, neutral)),
        MotorTest("eye tilt", ohbot.EYETILT, (safe_low, safe_high, neutral)),
        MotorTest("lid blink", ohbot.LIDBLINK, (safe_low, safe_high, neutral)),
        MotorTest("top lip", ohbot.TOPLIP, (safe_low, safe_high, neutral)),
        MotorTest("bottom lip", ohbot.BOTTOMLIP, (safe_low, safe_high, neutral)),
    )

    ohbot.init()
    try:
        ohbot.reset()
        ohbot.wait(0.75)

        for test in motor_tests:
            print(f"Testing motor: {test.name}")
            _sweep_motor(test)

        # Speech test: lip-sync on then off.
        ohbot.setVoice(language="en-GB", gender="Female")
        ohbot.say("Hello. This is a full Ohbot smoke test.", untilDone=True, lipSync=True)
        ohbot.wait(0.25)
        ohbot.say(
            "Now speaking without lip sync.",
            untilDone=True,
            lipSync=False,
        )

        ohbot.reset()
        ohbot.wait(0.5)
    finally:
        ohbot.close()


if __name__ == "__main__":
    main()
