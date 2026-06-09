# Presence-Aware Social Robot with Watch-Mediated Consent

A master's-thesis prototype in which a desktop social robot (**Ohbot**) reacts to
the wearer's **heart rate** and to **who else is in the room**, but only ever
discloses private wellbeing prompts *out loud* after the wearer gives **consent
on their smartwatch** (a **Bangle.js**). The robot then **remembers each
person's decision** so it never asks twice about the same bystander.

The design goal is a GDPR-flavoured privacy model: sensitive content is never
surfaced in front of a third party without an explicit, in-the-moment, *private*
"yes" from the data subject — and that "yes" (or "no") is given on the watch, not
spoken aloud and not typed on the laptop.

> **Input policy:** the laptop terminal never takes interactive input during a
> session. Every decision is made **on the watch** (Yes/No buttons); the only
> laptop interaction is pressing `q` in the camera preview window to quit.

---

## Table of contents

- [What it does](#what-it-does)
- [How it works](#how-it-works)
- [Hardware](#hardware)
- [Repository layout](#repository-layout)
- [Setup](#setup)
- [Running a session](#running-a-session)
- [What the robot says](#what-the-robot-says)
- [Configuration reference](#configuration-reference)
- [Watch ⇄ laptop protocol](#watch--laptop-protocol)
- [Runtime state files](#runtime-state-files)
- [Troubleshooting](#troubleshooting)

---

## What it does

The end-to-end behaviour, in order:

1. **Read heart rate from the watch.** The Bangle.js streams live BPM to the
   laptop over Bluetooth Low Energy (BLE).
2. **Connect the Ohbot to the watch pipeline.** One laptop process holds the BLE
   link to the watch *and* the USB serial link to the Ohbot, so the robot can act
   on watch events.
3. **Detect an elevated heart rate.** BPM above a threshold, sustained for a few
   seconds, is what arms the robot to act.
4. **Enroll the owner once, by camera.** Before the first session you sit in
   front of the webcam and the system learns your face, so it can later tell *you*
   (the watch-wearer) apart from other people.
5. **Sense who is present.** The webcam watches the scene and decides whether
   anyone is in view.
6. **Ask for consent on the watch (GDPR step).** If the wearer's heart rate is
   elevated **and** someone else is present, the robot does **not** blurt out a
   private message. Instead the watch **buzzes and shows a Yes/No prompt**:
   *"I have noticed that someone is present with you. Do you want me to send
   private reminders in front of them?"*
7. **Yes → the robot suggests a wellbeing action.** The Ohbot speaks the private
   prompt out loud, e.g. *"...would you like to take a few deep breaths
   together?"*
8. **Remember the decision per person.** The answer is cached against that
   specific bystander. The **next** time the same person is present, the robot
   **does not ask again** — it just repeats the remembered behaviour.
9. **No → the robot stays neutral.** The Ohbot simply greets: *"Hello there."*
   and the private content is withheld.

---

## Two consent policies

The project ships **two** runtime scripts that share an identical sensing and
face-recognition pipeline and differ only in *how consent is handled*:

| Script | Consent behaviour | Memory |
| --- | --- | --- |
| [`demo_cache_memory.py`](interface/presence/demo_cache_memory.py) | Asks the first time it sees a given person; reuses that answer afterwards. | **Remembers** each person's Yes/No (`consent_cache.json`). |
| [`demo_reconsent.py`](interface/presence/demo_reconsent.py) | Asks **every single time** the situation arises, even for the same person. | **Forgets** — no decision is ever stored. |

Both still **recognise** people (the owner is filtered out and bystanders get
stable IDs in the shared `face_db.json` gallery); the difference is purely whether
a recognised person's earlier answer is reused (`cache_memory`) or ignored
(`reconsent`). The `reconsent` script is the privacy baseline the cache-memory
policy is compared against in the thesis.

---

## How it works

```
   ┌──────────────┐   BLE (Nordic UART)    ┌───────────────────────────────┐
   │  Bangle.js   │ ─── BPM:<n> ─────────▶ │           Laptop              │
   │   watch      │ ◀── consent(id,msg) ── │  demo_cache_memory.py         │
   │              │ ─── CONSENT:id:YES ──▶ │                               │
   │ HR + buzzer  │                        │  ┌─────────┐  ┌─────────────┐ │
   │ Yes/No touch │                        │  │ BLE     │  │ webcam      │ │
   └──────────────┘                        │  │ client  │  │ presence +  │ │
                                           │  │ (HR +   │  │ face ID     │ │
   ┌──────────────┐   USB serial           │  │ consent)│  │ (YuNet/SFace)│ │
   │    Ohbot     │ ◀───────────────────── │  └─────────┘  └─────────────┘ │
   │  (speech +   │                        │        consent cache (memory) │
   │   motors)    │                        └───────────────────────────────┘
   └──────────────┘
```

The laptop runs the orchestration ("intermediate layer"). Each piece:

- **Presence sensing.** Every camera frame is run through a fast Haar-cascade face
  detector to get a face count. A 15-second sliding window votes on whether a face
  is reliably *in view* (≥70 % of frames) or reliably *absent* (≤30 %), so the
  robot reacts to a stable situation rather than to one flickery frame.
- **Owner vs. bystander.** *Owner presence in the room* is taken from the **BLE
  link**: while the watch is connected (Bangle.js reaches ~10 m ≈ "same room"),
  the owner is assumed present even if not on camera. *Who is on camera* is
  resolved at decision time with **YuNet** (precise face boxes) + **SFace**
  (128-D face embeddings). Any face matching the enrolled owner template is
  filtered out; every other face is a **bystander** and is given a stable
  `person_NNN` ID in a local face gallery.
- **The trigger.** The robot starts a "trial" only when **all** of these hold:
  the heart rate is elevated and stable, a face is reliably in view, and the watch
  is connected. It fires once per encounter and re-arms when the scene changes
  (camera empties, HR settles, watch drops, or a new person arrives).
- **Consent + memory.** On a trial, the system builds a key from the bystander
  ID(s). If that key already has a remembered Yes/No, it acts immediately with no
  prompt. Otherwise it asks the watch and stores whatever the user taps. The store
  is a small JSON file, so memory survives restarts.
- **Privacy-safe defaults.** If the watch doesn't answer within the timeout, or
  the BLE link drops mid-prompt, the robot **withholds** (treats it as "no") and
  does **not** cache that non-answer as a preference.

> **Note on the heart-rate gate:** the robot only acts on a *genuinely* elevated,
> sustained reading (see [Configuration](#configuration-reference)). If you want to
> exercise the consent/memory flow without raising your pulse, see
> [Troubleshooting](#troubleshooting).

---

## Hardware

| Device | Role | Connection |
| --- | --- | --- |
| **Bangle.js** smartwatch | Heart-rate source + private Yes/No consent screen + buzzer | BLE |
| **Ohbot** desktop robot | Speech (espeak TTS + lip-sync) and head/eye motion | USB serial |
| **Laptop** with webcam | Runs the pipeline; webcam does presence + face ID | — |

Tested on **macOS** and **Linux** (the BLE layer, `bleak`, also abstracts
Windows, but the lab kit runs on macOS/Linux).

---

## Repository layout

```
.
├── bangle/
│   └── consent_app.js          # Runs ON the watch: HR broadcast + Yes/No consent
├── interface/
│   ├── requirements.txt        # Laptop deps (opencv, bleak, ohbot)
│   └── presence/
│       ├── demo_cache_memory.py  # ▶ MAIN APP — full pipeline, REMEMBERS each decision
│       ├── demo_reconsent.py     # Baseline — same pipeline but ALWAYS re-asks (no memory)
│       ├── enroll_owner.py       # One-time owner face enrollment (run first)
│       ├── policy.py             # BLE client (HR + ask_consent) + consent memory store
│       ├── face_id.py            # YuNet detection + SFace embeddings (auto-downloads models)
│       ├── face_db.py            # Bystander face gallery (stable person IDs)
│       └── owner.py              # Owner face template store + matcher
├── ohbot/
│   ├── requirements.txt        # Ohbot-only dep (subset of interface/requirements.txt)
│   └── ohbotData/              # Ohbot SDK runtime templates (motors, voice, settings)
└── docs/
    └── literature_review.md    # Thesis background reading
```

Generated/local files that are **not** committed (see `.gitignore`): the
downloaded ONNX models (`interface/presence/models/`), the runtime JSON state
(`owner_face.json`, `face_db.json`, `consent_cache.json`), and the Ohbot TTS
output (`ohbotspeech.wav`).

---

## Setup

### 1. Laptop Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r interface/requirements.txt
```

This installs `opencv-python`, `bleak` (BLE), and `ohbot`. The YuNet + SFace face
models (~37 MB total) are **downloaded automatically** on first run into
`interface/presence/models/`.

### 2. Speech engine (espeak)

The Ohbot SDK is configured to synthesize speech with **espeak**, so the espeak
binary must be installed:

```bash
# macOS
brew install espeak
# Debian/Ubuntu
sudo apt install espeak
```

### 3. Flash the watch app

1. Open the **Espruino Web IDE** (<https://www.espruino.com/ide/>) in Chrome/Edge.
2. Connect to the Bangle.js over Web Bluetooth (top-left icon).
3. Paste [`bangle/consent_app.js`](bangle/consent_app.js) into the right-hand
   editor and click **Send to Espruino**.
4. (Optional) type `save()` in the left REPL so it survives a watch reboot.
5. **Disconnect the Web IDE** — only one BLE master can hold the watch at a time,
   and the laptop app needs the link.

### 4. Plug in the Ohbot

Connect the Ohbot over USB. If your serial port isn't auto-detected, set a hint
(see [Configuration](#configuration-reference)).

---

## Running a session

### Step 1 — Enroll the owner (once)

```bash
cd interface/presence
python enroll_owner.py
```

Sit **alone** in front of the camera and look at it. The script captures ~12 face
samples, averages them into an owner template (`owner_face.json`), then shows a
quick live "OWNER / other" similarity check so you can confirm it discriminates
you from others. Press `q` to finish. Re-run any time to re-enroll.

### Step 2 — Run the robot

```bash
cd interface/presence
python demo_cache_memory.py     # remembers each person's decision
# or, for the always-ask baseline (never remembers):
# python demo_reconsent.py
```

You'll see a camera preview with a live status overlay (face count, BPM, watch
link, the rolling presence verdict, and the last trial's result). Wear the watch
snugly so the HRM gets a confident reading. **Press `q` in the camera window to
quit** — that's the only laptop input.

When the conditions line up (elevated HR + someone present + watch connected) the
**watch buzzes and shows the consent prompt**. Tap **Yes** or **No** on the watch:

- **Yes** → the Ohbot speaks the deep-breathing suggestion, and the choice is
  remembered for that person.
- **No** → the Ohbot says "Hello there.", and that's remembered too.
- **Same person again** → no prompt; the robot repeats the remembered behaviour.

---

## What the robot says

| Situation | Channel | Message |
| --- | --- | --- |
| Consent request | **Watch** (buzz + Yes/No) | *"I have noticed that someone is present with you. Do you want me to send private reminders in front of them?"* |
| Consent **Yes** | **Ohbot** (spoken) | *"I noticed your heart rate has been a bit elevated, around `<bpm>`. Would you like to take a few deep breaths together?"* |
| Consent **No** | **Ohbot** (spoken) | *"Hello there."* |

---

## Configuration reference

### Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `OHBOT_PORT` | `Pico` | Serial-port hint passed to `ohbot.init()`. |
| `NO_OHBOT` | unset | Set to `1` to skip the Ohbot entirely and speak via the OS voice (`say` on macOS, `espeak` on Linux). Lets you test the watch consent + memory flow without the robot plugged in. |

Example — run without the robot:

```bash
NO_OHBOT=1 python demo_cache_memory.py
```

### Tunable thresholds

Defined at the top of [`demo_cache_memory.py`](interface/presence/demo_cache_memory.py)
and [`face_id.py`](interface/presence/face_id.py):

| Constant | Value | Meaning |
| --- | --- | --- |
| `ELEVATED_BPM` | `100` | BPM above this counts as "elevated". |
| `MIN_ELEVATED_DWELL_S` | `5.0` | How long BPM must stay elevated before acting. |
| `HR_STALE_S` | `10.0` | Ignore the cached BPM if the watch hasn't pushed in this long. |
| `OBSERVATION_WINDOW_S` | `15.0` | Length of the presence sliding window. |
| `FACE_VISIBLE_FRACTION_HIGH` | `0.7` | ≥ this fraction of frames with a face ⇒ "face in view". |
| `FACE_VISIBLE_FRACTION_LOW` | `0.3` | ≤ this fraction ⇒ "no faces". |
| `CONSENT_TIMEOUT_S` | `30.0` | How long to wait for a watch tap before defaulting to withhold. |
| `SFACE_COSINE_SAME_PERSON` | `0.363` | Cosine threshold for "same bystander" re-identification. |
| `SFACE_OWNER_THRESHOLD` | `0.50` | Tighter threshold for matching the enrolled owner. |

---

## Watch ⇄ laptop protocol

Communication is line-oriented over the **Nordic UART Service (NUS)**:

- **Watch → laptop**
  - `BPM:<n>` — a confident heart-rate sample.
  - `CONSENT:<id>:YES` / `CONSENT:<id>:NO` — the user's answer to prompt `<id>`.
- **Laptop → watch**
  - `consent("<id>","<message>")\n` — a JS call the watch's REPL evaluates; it
    buzzes, shows the Yes/No prompt, and replies with a `CONSENT:` line. Strings
    are JSON-encoded so quotes/newlines are escaped safely, and writes are chunked
    to ≤20 bytes for the Espruino BLE UART.

NUS characteristics: RX (watch→laptop notify) `6e400003-…`, TX (laptop→watch
write) `6e400002-…`.

---

## Runtime state files

These live next to the code in `interface/presence/` and are gitignored (local,
per-machine state — not source):

| File | Created by | Contents |
| --- | --- | --- |
| `models/*.onnx` | `face_id.ensure_models()` | YuNet + SFace weights, auto-downloaded once. |
| `owner_face.json` | `enroll_owner.py` | Averaged owner face embedding + enrollment metadata. |
| `face_db.json` | `demo_cache_memory.py` | Bystander face gallery (stable `person_NNN` IDs). |
| `consent_cache.json` | `demo_cache_memory.py` | The remembered Yes/No decisions, keyed by bystander. |

Delete `consent_cache.json` to make the robot "forget" all preferences; delete
`face_db.json` to reset bystander identities; re-run `enroll_owner.py` to replace
the owner template.

---

## Troubleshooting

- **The watch never prompts / nothing happens.** All trigger conditions must hold
  at once: BPM sustained above `ELEVATED_BPM`, a face reliably in view for the full
  window, and the watch BLE-connected. The status overlay shows each input
  (`bpm=…`, `verdict=…`, `watch=OK/OFFLINE`). To exercise the flow **without**
  raising your heart rate, temporarily force the gate by setting
  `elevated_stable = True` just after it's computed in
  [`demo_cache_memory.py`](interface/presence/demo_cache_memory.py) (revert before
  real use).
- **Watch not found / consent never delivered.** Make sure the **Espruino Web IDE
  is disconnected** — only one BLE master may hold the watch. Confirm
  `consent_app.js` is running (the watch shows a "HR broadcast" screen with a BPM).
- **No BPM / "no signal" on the watch.** The HRM ignores low-confidence samples;
  wear the watch snug and still for a few seconds.
- **Ohbot init hangs.** The robot is likely not on the expected serial port. Set
  `OHBOT_PORT`, or run with `NO_OHBOT=1` to use the laptop voice instead.
- **No speech even with the robot.** Ensure **espeak** is installed (the SDK uses
  it to synthesize). On macOS, audio is played via `afplay` of the generated
  `ohbotspeech.wav`.
- **Camera won't open.** Close anything else using the webcam (Zoom, Teams,
  browser tabs). On macOS the first run prompts for Camera permission for your
  terminal / IDE.
