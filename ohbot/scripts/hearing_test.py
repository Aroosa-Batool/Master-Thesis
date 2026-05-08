"""Laptop-mic "hearing" smoke test for Ohbot.

Ohbot basic doesn't have a microphone. This script uses the *laptop* microphone as
an audio input channel and triggers an Ohbot reaction when it detects a loud
sound (e.g., a clap).

What it does:
- Calibrates ambient noise for a couple seconds
- Listens for a loud event (RMS energy above a threshold)
- On detection: blink + head nod + say "I heard that"

Notes (macOS):
- The first run may prompt for Microphone permission for your terminal/VS Code.
- This script intentionally does NOT record/save audio. It only computes simple
  volume statistics in-memory.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


def _require_deps() -> tuple[object, object]:
    try:
        import numpy as np  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise SystemExit(
            "Missing dependency: numpy. Install with `python -m pip install numpy`."
        ) from exc

    try:
        import sounddevice as sd  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise SystemExit(
            "Missing dependency: sounddevice. Install with `python -m pip install sounddevice`."
        ) from exc

    return np, sd


try:
    from ohbot import ohbot
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: install the Ohbot SDK with `python -m pip install ohbot`."
    ) from exc


@dataclass(frozen=True)
class Config:
    sample_rate_hz: int = 16_000
    block_ms: int = 50
    calibrate_seconds: float = 2.0
    listen_timeout_seconds: float = 20.0

    # Thresholding: event if rms > (mean + std_multiplier * std)
    std_multiplier: float = 6.0

    # Absolute floor to avoid hypersensitivity in near-silence
    min_event_rms: float = 0.02


def _rms(np: object, block) -> float:
    # sounddevice provides float32 in [-1, 1] by default.
    arr = block
    if getattr(arr, "ndim", 1) > 1:
        arr = arr[:, 0]
    return float(getattr(np, "sqrt")(getattr(np, "mean")(arr * arr)))


def main() -> None:
    np, sd = _require_deps()
    cfg = Config()

    block_size = int(cfg.sample_rate_hz * (cfg.block_ms / 1000.0))

    print("Initializing Ohbot...")
    ohbot.init()

    try:
        print(
            f"Calibrating ambient noise for {cfg.calibrate_seconds:.1f}s... (stay quiet)"
        )
        cal_rms: list[float] = []

        with sd.InputStream(
            channels=1,
            samplerate=cfg.sample_rate_hz,
            blocksize=block_size,
            dtype="float32",
        ) as stream:
            start = time.monotonic()
            while time.monotonic() - start < cfg.calibrate_seconds:
                block, _overflowed = stream.read(block_size)
                cal_rms.append(_rms(np, block))

            mean = float(np.mean(cal_rms)) if cal_rms else 0.0
            std = float(np.std(cal_rms)) if cal_rms else 0.0
            threshold = max(cfg.min_event_rms, mean + cfg.std_multiplier * std)

            print(
                "Listening for a clap... "
                f"(threshold rms={threshold:.4f}, timeout={cfg.listen_timeout_seconds:.0f}s)"
            )

            heard = False
            start = time.monotonic()
            while time.monotonic() - start < cfg.listen_timeout_seconds:
                block, _overflowed = stream.read(block_size)
                level = _rms(np, block)
                if level > threshold:
                    heard = True
                    break

        if heard:
            print("Heard a loud event — reacting.")
            # Small, safe reaction.
            ohbot.move(ohbot.LIDBLINK, 8)
            ohbot.wait(0.2)
            ohbot.move(ohbot.LIDBLINK, 2)

            ohbot.move(ohbot.HEADNOD, 7)
            ohbot.wait(0.25)
            ohbot.move(ohbot.HEADNOD, 5)

            ohbot.say("I heard that.", untilDone=True, lipSync=True)
        else:
            print("No loud event detected within timeout.")
            ohbot.say("I did not hear anything.", untilDone=True, lipSync=False)

    finally:
        ohbot.close()


if __name__ == "__main__":
    main()
