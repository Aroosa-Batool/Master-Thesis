"""Shared microphone-input-device selection for the voice scripts.

PortAudio's default *input* can resolve to ``-1`` on some macOS setups even
when a working microphone is present, which makes ``sd.InputStream`` raise
``Error querying device -1``. ``pick_input_device()`` resolves a valid input
device once - honouring ``VOICE_INPUT_DEVICE`` - so the demo, the owner
enroller, and the reminder-adder all select the mic identically.

    sd.default.device = (pick_input_device(), sd.default.device[1])
"""

from __future__ import annotations

import os

from robot.core.logsetup import logcall, get_logger

try:
    import sounddevice as sd
except (ModuleNotFoundError, OSError) as exc:
    raise SystemExit(
        "Missing dependency: install with `pip install sounddevice` "
        "(needs the PortAudio library; on Linux: `apt install libportaudio2`)."
    ) from exc

log = get_logger(__name__)


@logcall
def pick_input_device() -> int:
    """Return a valid input-device index for ``sd.InputStream``.

    Honour ``VOICE_INPUT_DEVICE`` (an index, or a case-insensitive substring
    of the device name) when set; otherwise use PortAudio's default input
    when it is valid; otherwise fall back to the first device that reports
    input channels (printing which one it chose).
    """

    devices = sd.query_devices()
    want = os.environ.get("VOICE_INPUT_DEVICE")
    if want:
        try:
            return int(want)
        except ValueError:
            for i, d in enumerate(devices):
                if d["max_input_channels"] > 0 and want.lower() in d["name"].lower():
                    return i
            raise SystemExit(
                f"[audio] no input device matches VOICE_INPUT_DEVICE={want!r}."
            )
    try:
        default_in = int(sd.default.device[0])
    except (TypeError, ValueError):
        default_in = -1
    if default_in >= 0:
        log.info("using default input device %d", default_in,
                 extra={"event": "device_selected"})
        return default_in
    for i, d in enumerate(devices):
        if d["max_input_channels"] > 0:
            print(
                f"[audio] no valid default input device; using {i} "
                f"({d['name']!r}). Override with VOICE_INPUT_DEVICE.",
                flush=True,
            )
            log.info("selected fallback input device %d (%r)", i, d["name"],
                     extra={"event": "device_selected"})
            return i
    raise SystemExit("[audio] no input-capable audio device found.")
