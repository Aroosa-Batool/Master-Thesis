# Intermediate layer

Python bridge between the Bangle.js and Ohbot. Owns all of the behavior-selection logic.

## Modules (planned)

- `ble/` — BLE client for the watch (`bleak` on Windows).
- `proxy/` — turns raw watch signals into simplified proxy states.
- `policy/` — maps `(proxy state, tie strength, context) → behavior`. **This is the research core.**
- `ohbot_client/` — sends the chosen behavior to the Ohbot side.
- `main.py` — entry point that wires everything together.

## Running

```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
pip install -r requirements.txt
python main.py
```

`requirements.txt` will be added once dependencies are pinned.

## Testing

The policy is unit-tested with synthetic inputs in `../tests/policy/`. BLE and Ohbot integration
tests run against real hardware — they are not mocked.
