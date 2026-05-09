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

## Setup

The pipeline runs on either Windows 10/11 or macOS. Each laptop needs its
own virtual environment — venvs are not portable across operating systems.

### Windows (PowerShell)

```powershell
git clone <this repo>
cd Master-Thesis
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r interface\requirements.txt
```

If activation fails with "running scripts is disabled", run once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### macOS (zsh / bash)

```bash
git clone <this repo>
cd Master-Thesis
python3 -m venv .venv
source .venv/bin/activate
pip install -r interface/requirements.txt
```

The first time you run a demo on macOS, the OS prompts for **camera** and
**Bluetooth** permission for whichever app launched Python (Terminal,
iTerm, or VS Code). Grant both. If you miss a prompt, toggle the app on
under *System Settings → Privacy & Security → Camera / Bluetooth* and
relaunch it.

You only do the above once per machine. From then on, just activate the
venv at the start of each session.

## Running the demos

The demos are layered: each one builds on the previous and is
independently runnable for debugging. Start at whichever level you want.

### 1. Presence detection only (no robot, no watch)

```
python interface/presence/check_alone.py
```

Opens the laptop webcam, draws bounding boxes around faces, and prints
`ALONE` / `NOT ALONE`. Press `q` in the camera window to quit. Useful for
sanity-checking that face detection is reliable in the demo environment.

### 2. Presence + Ohbot

Plug the Ohbot into USB, then:

```
python interface/presence/demo_with_ohbot.py
```

The robot observes the camera for ~25 seconds, then delivers the
full-disclosure message when alone and a neutral greeting when someone
else is in the room. Per-frame jitter is smoothed by a windowed verdict,
so brief misdetections do not make the robot flip-flop.

### 3. Live heart rate from the watch

First, push the broadcaster onto the watch:

1. Open https://www.espruino.com/ide/ in Chrome or Edge.
2. Connect to the Bangle over Web Bluetooth (plug icon).
3. Paste [bangle/hrm_broadcast.js](bangle/hrm_broadcast.js) into the right
   pane and click "Send to Espruino".
4. **Disconnect** the IDE — only one BLE master at a time, and the laptop
   needs the link.

Once the watch is worn snug and shows a bpm + climbing `conf` number,
verify the laptop can see it:

```
python interface/presence/scan_watch.py    # find the watch on BLE
python interface/presence/read_hr.py       # subscribe to live bpm
```

### 4. Full integrated demo

With the watch broadcasting, the Ohbot connected, and the laptop in
range:

```
python interface/presence/demo_with_watch.py
```

Fuses presence (camera) and elevated heart rate (watch). The robot
delivers the wellbeing message only when the user is **alone and
elevated**, and falls back to a neutral greeting + watch handoff when
**not alone and elevated**. Otherwise it stays idle.

## Troubleshooting

- **`save() is not defined` in the Espruino IDE.** Bangle.js 2 doesn't
  expose top-level `save()`. Just keep the IDE open during development;
  the script lives in the watch's RAM until reboot. Re-upload after each
  reboot.
- **Laptop can't find the watch.** The Espruino IDE is probably still
  connected — disconnect it before running anything from the laptop.
- **bpm shows `--` in the demo.** HRM confidence is below 30 (loose strap,
  motion, cold wrist). Tighten the strap, sit still, and watch the `conf`
  number on the watch screen climb above 30 before broadcasts start.
- **macOS camera or Bluetooth silently fails.** See *Setup → macOS*.
  Permission must be granted under System Settings, and the app you
  launched Python from has to be the one that's allowed.

## Status

Phase 3 working: laptop webcam (presence) + Bangle.js watch (live heart
rate over BLE) + Ohbot (disclosure behaviors) are integrated end-to-end
with windowed temporal smoothing on both signals. Tie-strength input and
the return-channel handoff back to the watch are next. See the proposal
in [docs/proposal.md](docs/proposal.md) for the full problem statement
and timeline.

## License

To be decided before submission.
