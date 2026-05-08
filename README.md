# Privacy-Aware Interactive Robot for Context-Sensitive Wellbeing Support

Master's thesis project. The system pairs a **Bangle.js** smartwatch with the **Ohbot** social
robot to deliver wellbeing support that is sensitive to both the user's state and the surrounding
social context. The research focus is *how much* to reveal and *through which channel* — not just
*whether* to respond.

## System overview

```
┌─────────────┐      BLE       ┌─────────────────────┐      USB/Serial   ┌──────────┐
│  Bangle.js  │ ─────────────▶ │  Intermediate layer │ ─────────────────▶│  Ohbot   │
│  smartwatch │ ◀───────────── │  (proxy + policy)   │                    │  robot   │
└─────────────┘                └─────────────────────┘                    └──────────┘
   sensing +                     proxy state +                              one of four
   private channel               tie strength →                             behaviors
                                 behavior choice
```

### The four robot behaviors

| Behavior            | What it does                                       | Typical context                |
| ------------------- | -------------------------------------------------- | ------------------------------ |
| Full disclosure     | Explicit verbal response                           | Strong tie, private setting    |
| Partial disclosure  | Indirect or reduced verbal response                | Mixed company, ambiguous tie   |
| No disclosure       | No sensitive information revealed                  | Weak tie or strangers present  |
| Watch notification  | Private message routed back to the Bangle.js       | Sensitive content, any context |

## Repository layout

```
.
├── bangle/             # Bangle.js (Espruino) firmware: sensing + notification UI
├── interface/          # Intermediate layer: BLE bridge, proxy-state mapping, policy
├── ohbot/              # Ohbot scripts and behavior implementations
├── docs/               # Proposal, design notes, evaluation materials
└── tests/              # Unit + integration tests, scenario scripts
```

Each component is intentionally decoupled so it can be iterated on without touching the others.

## Prerequisites

- **Bangle.js**: [Espruino Web IDE](https://www.espruino.com/ide/) (Chrome / Edge with Web Bluetooth)
- **Ohbot**: Python 3.9+, the official `ohbot` Python package, Ohbot connected over USB
- **Intermediate layer**: Python 3.10+, BLE stack (`bleak` recommended on Windows)

Exact dependency pins live in [interface/requirements.txt](interface/requirements.txt) and
[ohbot/requirements.txt](ohbot/requirements.txt).

## Quick start

> The pipeline is under active development — these steps will be filled in as components land.

1. Flash the watch app onto the Bangle.js using the Espruino Web IDE.
2. Connect Ohbot via USB and confirm the speech + servo test passes
   (`python ohbot/scripts/hello.py`).
3. Start the intermediate layer: `python interface/main.py`.
4. Trigger a scenario from `tests/scenarios/` and observe the chosen behavior.

## Status

Early scaffolding. See the proposal in [docs/proposal.md](docs/proposal.md) for the full
problem statement and timeline.

## License

To be decided before submission.
