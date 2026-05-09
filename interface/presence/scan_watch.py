"""Scan for the Bangle.js watch over BLE.

Phase 3, mini-step B: confirm the laptop can see the watch on the air.
Run hrm_broadcast.js on the watch first, then run this script. A Bangle.js
entry should appear in the printed list.

Run:
    python interface/presence/scan_watch.py
"""

from __future__ import annotations

import asyncio

try:
    from bleak import BleakScanner
except ModuleNotFoundError as exc:
    raise SystemExit("Missing dependency: install with `pip install bleak`.") from exc


async def main() -> None:
    print("Scanning for 8 seconds...")
    devices = await BleakScanner.discover(timeout=8.0, return_adv=True)
    if not devices:
        print("No BLE devices found. Is Bluetooth on? Is anything else paired?")
        return

    found_watch = False
    for address, (device, adv) in devices.items():
        name = device.name or adv.local_name or "(no name)"
        services = list(adv.service_uuids or [])
        marker = ""
        if "bangle" in name.lower():
            marker = "  <-- looks like the watch"
            found_watch = True
        print(f"  {name:24}  {address}  services={services}{marker}")

    if not found_watch:
        print(
            "\nDid not find a Bangle.js. Things to try:\n"
            "  - Confirm hrm_broadcast.js is running on the watch (screen "
            "shows 'HR broadcast').\n"
            "  - Disconnect the Espruino Web IDE — only one BLE master can "
            "talk to the watch at a time.\n"
            "  - Rerun this script."
        )


if __name__ == "__main__":
    asyncio.run(main())
