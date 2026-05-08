# Ohbot side

Scripts that drive the Ohbot using the official `ohbot` Python package. Each of the four
behaviors is implemented here as a primitive and triggered by the intermediate layer.

## Behaviors

| Module                  | Behavior            |
| ----------------------- | ------------------- |
| `behaviors/full.py`     | Full disclosure     |
| `behaviors/partial.py`  | Partial disclosure  |
| `behaviors/none_.py`    | No disclosure       |
| `behaviors/handoff.py`  | Defer to watch notification |

These are pure motor/voice primitives — they receive a request to perform behavior X and do it.
The decision *which* behavior to perform stays in `interface/policy/`.

## Setup

```bash
pip install ohbot
python scripts/hello.py     # smoke test, moves head and says hello
```

## Notes

We're targeting the **basic** Ohbot. Don't assume features from the upgraded variant unless we
verify the hardware supports them.
