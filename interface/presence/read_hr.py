"""Read live heart rate from the Bangle.js watch over BLE.

Phase 3, mini-step C: end-to-end verification that the watch -> laptop pipe
works. Once scan_watch.py finds the watch, this script connects to it and
prints heart-rate readings as they arrive. Stop with Ctrl+C.

Run:
    python interface/presence/read_hr.py
"""

from __future__ import annotations

import asyncio

try:
    from bleak import BleakClient, BleakScanner
except ModuleNotFoundError as exc:
    raise SystemExit("Missing dependency: install with `pip install bleak`.") from exc


HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"


def parse_hr(data: bytearray) -> int:
    # Standard HR Measurement format: byte 0 is flags. Bit 0 of flags == 0
    # means the bpm is uint8 in byte 1; == 1 means uint16 little-endian in
    # bytes 1-2. We support both so this works against off-the-shelf chest
    # straps too.
    flags = data[0]
    if flags & 0x01:
        return int.from_bytes(data[1:3], byteorder="little")
    return data[1]


def hr_callback(_sender: int, data: bytearray) -> None:
    print(f"bpm = {parse_hr(data)}")


async def main() -> None:
    print("Searching for a Bangle.js watch (15s timeout)...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, adv: bool(d.name and "bangle" in d.name.lower()),
        timeout=15.0,
    )
    if device is None:
        raise SystemExit(
            "Could not find a Bangle.js. Is hrm_broadcast.js running on the "
            "watch, and is the Espruino Web IDE disconnected?"
        )

    print(f"Connecting to {device.name} ({device.address})...")
    async with BleakClient(device) as client:
        print("Connected. Subscribing to HR notifications. Ctrl+C to stop.")
        await client.start_notify(HR_MEASUREMENT_UUID, hr_callback)
        try:
            while True:
                await asyncio.sleep(1.0)
        finally:
            await client.stop_notify(HR_MEASUREMENT_UUID)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nstopped.")
