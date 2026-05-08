# Bangle.js side

Espruino apps that run on the Bangle.js. Two responsibilities:

1. **Sense** — read the sensor signals the policy needs (heart rate, motion, etc.) and stream
   them to the intermediate layer over BLE.
2. **Notify** — render the "watch notification" behavior privately on the wrist when the policy
   decides full disclosure on Ohbot would be inappropriate.

## Files

- `app.js` — main watch app entry point (TODO).
- `protocol.md` — wire format for the BLE link (see also `../docs/protocol.md`).

## Loading onto the watch

Use the [Espruino Web IDE](https://www.espruino.com/ide/) over Web Bluetooth (Chrome / Edge).

## Notes

- Keep the on-watch payload minimal. The policy lives in the intermediate layer, not here.
- No raw audio or text content is ever sent over BLE.
