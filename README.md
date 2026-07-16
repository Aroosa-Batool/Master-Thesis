# Presence-Aware Social Robot with Watch-Mediated Consent

A master's-thesis prototype in which a desktop social robot (**Ohbot**) delivers
scheduled **private reminders** (e.g. a doctor's appointment), reacting to **who
else is in the room**, but only ever discloses a *sensitive* reminder *out loud*
after the wearer gives **consent on their smartwatch** (a **Bangle.js**). The
robot then **remembers each person's decision** so it never asks twice about the
same bystander.

The design goal is a GDPR-flavoured privacy model: sensitive content is never
surfaced in front of a third party without an explicit, in-the-moment, *private*
"yes" from the data subject — and that "yes" (or "no") is given on the watch, not
spoken aloud and not typed on the laptop.

> **Input policy:** the laptop terminal never takes consent input during a live
> session. Every disclosure decision is made **on the watch** (Yes/No buttons);
> the live camera/voice demos only use `q` in their OpenCV window to quit.
> One-time enrollment and reminder creation do use terminal confirmation.

---

## Table of contents

- [What it does](#what-it-does)
- [How it works](#how-it-works)
- [Hardware](#hardware)
- [Repository layout](#repository-layout)
- [Documentation](#documentation)
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

1. **Add a reminder ahead of time.** You speak a reminder to the robot (e.g.
   *"remind me about my doctor's appointment at 3 PM"*); Whisper transcribes it,
   dateparser extracts the time, and a local **AI classifier labels it sensitive
   or not** (health/finance/personal vs. an everyday errand). See
   [Voice reminders](#voice-reminders-schedule-private-content-by-voice).
2. **Connect the Ohbot to the watch pipeline.** One laptop process holds the BLE
   link to the watch *and* the USB serial link to the Ohbot, so the robot can act
   on watch events.
3. **Enroll the owner once.** Before the first session you enroll your face
   (camera) or voice, so the system can later tell *you* (the watch-wearer) apart
   from other people.
4. **Sense who is present.** When a reminder is due, the robot senses whether
   anyone else is around — the **webcam** watches for faces, or the **microphone**
   listens for other voices.
5. **When a reminder becomes due, deliver it.** A **non-sensitive** reminder is
   simply spoken. A **sensitive** one is presence-gated: with the owner alone it
   is spoken; with someone else present the robot does **not** blurt it out —
   instead the watch **buzzes and shows a Yes/No prompt**: *"I have noticed that
   someone is present with you. Do you want me to send private reminders in front
   of them?"*
6. **Yes → the robot speaks the reminder.** *"Here is your reminder. …"*
   **No → it stays neutral** (*"Hello there."*) and the reminder is delivered
   **privately to the wrist** instead.
7. **Remember the decision per person.** The answer is cached against that
   specific bystander. The **next** time the same person is present, the robot
   **does not ask again** — it reuses the remembered choice.

---

## Four delivery apps: two consent policies × two modalities

The project's delivery apps form a **2×2** — the **same** consent-memory contrast
runs in **both** sensing modalities, giving **four** runnable apps that share an
identical sensing and recognition pipeline and differ only in *how consent is
handled* and *which sensor* detects presence (all launch as
`python -m robot.apps.<name>`):

| | **Camera** (webcam) | **Microphone** (voice) |
| --- | --- | --- |
| **Remembers** preference (cache-memory) | [`camera_remember`](robot/apps/camera_remember.py) | [`mic_remember`](robot/apps/mic_remember.py) |
| **Re-asks** every time (re-consent) | [`camera_reask`](robot/apps/camera_reask.py) | [`mic_reask`](robot/apps/mic_reask.py) |

The two **columns** differ only in the sensor (and embedding model); the two
**rows** differ only in how a recognised person's earlier answer is treated:

| Policy | Consent behaviour | Memory |
| --- | --- | --- |
| **remember** (cache-memory) | Asks the first time it sees/hears a given person; reuses that answer afterwards. | **Remembers** each person's Yes/No (`consent_cache*.json`). |
| **reask** (re-consent) | Asks **every single time** the situation arises, even for the same person. | **Forgets** — no decision is ever stored. |

All four still **recognise** people (the owner is filtered out and bystanders get
stable IDs in the shared per-modality gallery); the difference is purely whether
a recognised person's earlier answer is reused (`cache_memory`) or ignored
(`reconsent`). The **remember** apps store a bystander's Yes/No and reuse it —
the thesis's "remembers their privacy preferences" (the Privacy Management arm);
the **reask** apps ask the watch every time and store nothing — the Consent
baseline the cache-memory policy is compared against. That contrast now exists in
**both** modalities (four apps), not just the camera; the voice re-ask app
(`mic_reask`) is new, where previously only the camera had a re-consent baseline.

---

## Sensing modalities — camera and voice

"Is someone present with the user, and who are they?" can be answered two ways.
Both feed the **same** downstream logic (reminder due → presence check → watch
consent → disclose/withhold → per-person memory); they differ only in the sensor
and the embedding model.

| | **Camera** (`camera_remember.py`) | **Voice** (`mic_remember.py`) |
| --- | --- | --- |
| Sensor | Webcam | Microphone |
| Presence cue | A face is in view | Someone is speaking |
| Identity model | YuNet detect + **SFace** 128-D face embedding | **Resemblyzer** 256-D speaker "d-vector" |
| Owner enrollment | [`enroll_face.py`](robot/apps/enroll_face.py) | [`enroll_voice.py`](robot/apps/enroll_voice.py) |
| Owner vs. bystander | per **face**, cosine similarity | per **~1.6 s voiced window**, cosine similarity |
| Quit | `q` in the camera window | `Ctrl-C` in the terminal |

Both modalities use the **same** owner-vs-bystander idea (subtract the enrolled
owner; everyone else is a bystander with a stable auto-minted ID) and in fact
**reuse the same code** for it — `face_db.py` (the embedding gallery) and
`owner.py` (the owner template) are embedding-agnostic, so the voice pipeline
just points them at separate files. The two modalities keep **independent**
state, so a voice `person_001` and a face `person_001` never collide:

| | Camera | Voice |
| --- | --- | --- |
| Owner template | `owner_face.json` | `owner_voice.json` |
| Bystander gallery | `face_db.json` | `voice_db.json` |
| Consent memory | `consent_cache.json` | `consent_cache_voice.json` |

> **Voice has one inherent limit:** it can only notice a bystander who actually
> **speaks**. A silently-present third party is invisible to the microphone —
> that case is exactly what the camera modality covers. (Owner presence in the
> room is established by the **watch BLE link** in both modalities, so the owner
> need not be the one talking / on camera.)

---

## How it works

```
   ┌──────────────┐   BLE (Nordic UART)    ┌───────────────────────────────┐
   │  Bangle.js   │ ◀── consent(id,msg) ── │           Laptop              │
   │   watch      │ ─── CONSENT:id:YES ──▶ │  camera_remember.py /             │
   │              │ ◀── notify(msg) ─────── │  mic_remember.py             │
   │ buzzer +     │                        │  ┌─────────┐  ┌─────────────┐ │
   │ Yes/No touch │                        │  │ BLE     │  │ webcam/mic  │ │
   └──────────────┘                        │  │ client  │  │ presence +  │ │
                                           │  │ (consent│  │ face/voice  │ │
   ┌──────────────┐   USB serial           │  │  +notify)│  │ ID          │ │
   │    Ohbot     │ ◀───────────────────── │  └─────────┘  └─────────────┘ │
   │  (speech +   │                        │   reminders + consent cache   │
   │   motors)    │                        └───────────────────────────────┘
   └──────────────┘
```

The laptop runs the orchestration ("intermediate layer"). Each piece:

- **The trigger.** Delivery is triggered by a **reminder becoming due** — a
  scheduled piece of private content added ahead of time with
  [`add_reminder.py`](robot/apps/add_reminder.py). Each
  reminder is labelled **sensitive or not** by a local AI classifier; only
  sensitive reminders are presence-gated.
- **Presence sensing.** When a sensitive reminder is due, the robot checks who
  else is around. In the **camera** demo every frame runs a fast Haar detector for
  a face count, and YuNet+SFace identify who is in view at delivery time. In the
  **voice** runner the mic records the window before the reminder and Resemblyzer
  identifies any other speaker.
- **Owner vs. bystander.** *Owner presence in the room* is taken from the **BLE
  link**: while the watch is connected (Bangle.js reaches ~10 m ≈ "same room"),
  the owner is assumed present even if not on camera / not talking — so a due
  reminder is **held** until the watch is in range. *Who else is present* is
  resolved at delivery time; any face/voice matching the enrolled owner is
  filtered out, and every other one is a **bystander** with a stable `person_NNN`
  ID in a local gallery.
- **Consent + memory.** With a bystander present, the system builds a key from the
  bystander ID(s). If that key already has a remembered Yes/No it acts immediately
  with no prompt; otherwise it asks the watch and stores whatever the user taps.
  The store is a small JSON file, so memory survives restarts.
- **Privacy-safe defaults.** If the watch doesn't answer within the timeout, or
  the BLE link drops mid-prompt, the robot **withholds** (delivers the reminder
  privately to the wrist) and does **not** cache that non-answer as a preference.

---

## Hardware

| Device | Role | Connection |
| --- | --- | --- |
| **Bangle.js** smartwatch | Private Yes/No consent screen + wrist notifications + buzzer | BLE |
| **Ohbot** desktop robot | Speech (espeak TTS + lip-sync) and head/eye motion | USB serial |
| **Laptop** with webcam and microphone | Runs the pipeline; camera or mic senses presence and identity | — |

Tested on **macOS** and **Linux** (the BLE layer, `bleak`, also abstracts
Windows, but the lab kit runs on macOS/Linux).

---

## Repository layout

```
.
├── README.md
├── requirements.txt            # Laptop deps (opencv, bleak, ohbot, voice) — was interface/requirements.txt
├── bangle/
│   └── consent_app.js          # Runs ON the watch: Yes/No consent prompt + notify()
├── ohbot/
│   ├── requirements.txt        # Ohbot-only dep (subset of requirements.txt)
│   └── ohbotData/              # Ohbot SDK runtime templates (motors, voice, settings)
├── docs/
│   ├── README.md               # Documentation index
│   ├── codebase_guide.md       # Entry points, modules, state, and current caveats
│   ├── design_hld.md           # Requirements, consent model, and privacy rationale
│   ├── technical_hld.md        # Algorithms, interfaces, concurrency, and deployment
│   ├── algorithm_comparison.md # Benchmark-backed algorithm selection
│   └── literature_review.md    # Thesis background reading
└── robot/                      # The Python package — run apps as: python -m robot.apps.<name>
    ├── __init__.py
    ├── paths.py                # Centralised state/model paths (robot/state)
    ├── apps/                   # ▶ Runnable entry points (python -m robot.apps.<name>)
    │   │   # ── Camera modality (reminder-triggered) ─────────────────
    │   ├── camera_remember.py      # ▶ camera app — REMEMBERS each bystander's consent
    │   ├── camera_reask.py         # camera baseline — RE-ASKS every time (no memory)
    │   ├── enroll_face.py          # one-time owner FACE enrollment
    │   │   # ── Voice modality (reminder-triggered) ──────────────────
    │   ├── add_reminder.py         # ▶ add a reminder by voice (Whisper + dateparser)
    │   ├── mic_remember.py         # ▶ voice app — REMEMBERS consent (cache-memory)
    │   ├── mic_reask.py            # voice baseline — RE-ASKS every time (no memory)
    │   └── enroll_voice.py         # one-time owner VOICE enrollment
    ├── core/                   # Domain + robot I/O + consent
    │   ├── reminders.py            # reminder store (JSON, time-based)
    │   ├── sensitivity.py          # AI classifier: is a reminder sensitive? (text embedding + cosine)
    │   ├── voice_reminder.py       # shared voice engine behind mic_remember / mic_reask
    │   ├── policy.py               # BLE client (is_connected + ask_consent + notify) + consent memory
    │   ├── owner.py                # Owner template store + matcher (reused for face AND voice)
    │   └── robot_io.py             # Ohbot glue + reminder speech — SUPPORT module (imported by voice_reminder)
    ├── perception/             # Sensing + identity
    │   ├── face_id.py              # YuNet detection + SFace face embeddings (auto-downloads)
    │   ├── face_db.py              # Embedding gallery → stable IDs (reused for faces AND voices)
    │   ├── voice_id.py             # Resemblyzer speaker (d-vector) embeddings
    │   └── audio_device.py         # mic input-device selection (shared by the voice scripts)
    ├── bench/                  # Algorithm-comparison benchmark
    └── state/                  # GITIGNORED runtime data + downloaded ONNX weights
        ├── reminders.json, face_db.json, voice_db.json, owner_face.json,
        │   owner_voice.json, consent_cache.json, consent_cache_voice.json
        └── models/*.onnx           # YuNet + SFace weights, auto-downloaded once
```

Generated/local files include the downloaded ONNX models
(`robot/state/models/`), biometric templates/galleries, consent caches, and
scheduled reminders (`reminders.json`, which can hold private text) — all of
which live under `robot/state/` and are gitignored — plus the Ohbot TTS output
(`ohbotspeech.wav`).

---

## Documentation

For a single page that can be copied into Confluence, use
[`docs/confluence_system_documentation.md`](docs/confluence_system_documentation.md).
Use [`docs/README.md`](docs/README.md) as the full documentation index. The
[`codebase guide`](docs/codebase_guide.md) maps entry points to modules and
documents runtime JSON schemas and current implementation caveats. The
[`design HLD`](docs/design_hld.md) captures the privacy and interaction intent;
the [`technical HLD`](docs/technical_hld.md) covers algorithms, protocols,
thresholds, and concurrency. Algorithm evidence and reproduction instructions
live in [`docs/algorithm_comparison.md`](docs/algorithm_comparison.md) and the
[`benchmark README`](robot/bench/README.md).

---

## Setup

### 1. Laptop Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

This installs `opencv-python`, `bleak` (BLE), and `ohbot`, plus the voice-modality
deps `sounddevice` (mic) and `resemblyzer` (speaker embeddings — pulls in
**torch**, so the install is a few hundred MB). The YuNet + SFace face models
(~37 MB) are **downloaded automatically** on first run into
`robot/state/models/`; Resemblyzer's speaker weights ship inside the
package (no download).

`sounddevice` needs the **PortAudio** system library — bundled in the
macOS/Windows wheels; on Debian/Ubuntu install it with
`sudo apt install libportaudio2`. If you only ever run the **camera** demos, you
can skip the voice deps (`sounddevice`, `resemblyzer`) and the camera scripts
still work.

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
python -m robot.apps.enroll_face
```

Sit **alone** in front of the camera and look at it. The script captures ~12 face
samples, averages them into an owner template (`owner_face.json`), then shows a
quick live "OWNER / other" similarity check so you can confirm it discriminates
you from others. Press `q` to finish. Re-run any time to re-enroll.

### Step 2 — Add a reminder, then run the robot

Delivery is **reminder-triggered**, so first add a reminder (see
[Voice reminders](#voice-reminders-schedule-private-content-by-voice) for detail):

```bash
python -m robot.apps.add_reminder    # say e.g. "remind me about my doctor's appointment in 3 minutes"
```

Then run the camera app:

```bash
python -m robot.apps.camera_remember     # remembers each person's decision
# or, for the always-ask baseline (never remembers):
# python -m robot.apps.camera_reask
```

You'll see a camera preview with a live overlay (face count, watch link, the next
reminder's due time, and the last delivery result). **Press `q` in the camera
window to quit** — that's the only laptop input.

When a reminder becomes due, the robot delivers it based on **who the camera
sees** (owner presence is the watch BLE link, so a due reminder is held until the
watch is in range):

- **Non-sensitive reminder** → spoken normally, no consent.
- **Sensitive + owner alone** (no bystander in view) → spoken.
- **Sensitive + a bystander in view** → the **watch buzzes and shows the consent
  prompt**. Tap **Yes** → the Ohbot speaks the reminder (remembered for that
  person); **No** → the reminder is pushed **privately to the wrist** and the
  Ohbot only greets (*"Hello there."*).
- **Same person again** → no prompt; `camera_remember.py` reuses the remembered
  answer, while `camera_reask.py` re-asks every time.

### Voice modality (instead of the camera)

The voice equivalent is the **reminder runner** — the same watch consent + memory,
but it senses bystanders by **microphone** instead of camera. Enroll your voice
once, then use it exactly like the camera app; see
[Voice reminders](#voice-reminders-schedule-private-content-by-voice):

```bash
python -m robot.apps.enroll_voice    # speak alone for a bit; 'q' in the window to finish
python -m robot.apps.mic_remember    # voice, REMEMBERS consent (cache-memory)
python -m robot.apps.mic_reask       # voice, RE-ASKS every time (re-consent)
# NO_OHBOT=1 python -m robot.apps.mic_remember   # run without the robot
```

### Voice reminders (schedule private content by voice)

You can also ask the robot to **hold a private reminder** — e.g. a doctor's
appointment — and have it surfaced later under the same consent policy. Add one
by speaking:

```bash
python -m robot.apps.add_reminder    # say: "Remind me about my doctor's appointment on July 20th at 3 PM"
```

It records you, transcribes the command with **Whisper**, extracts the date/time
with **dateparser**, and classifies whether the reminder is **sensitive** with a
local AI classifier (see below). The confirm step shows the parse *and* the
sensitivity label; press `s` to flip the label if the classifier got it wrong,
then save to `reminders.json`. (Say a *date*, not just a time — "at 9 am" alone
can misparse; the confirm step also lets you retry.)

**Sensitivity classifier ([`sensitivity.py`](robot/core/sensitivity.py)).**
Not every reminder is private. "Doctor's appointment" or "Take medication at 8 PM"
should be gated; "Buy milk" or "Water the plants" can just be said. A
sentence-transformer embeds the reminder text and compares it (cosine similarity)
against small labelled example sets for each class — the **same
embedding-plus-cosine method** the voice (`voice_id.py`) and face (`face_id.py`)
pipelines use, now applied to text. It runs **fully locally**: the reminder text
never leaves the device, so the classifier itself doesn't leak what it is trying
to protect. Borderline cases default to *sensitive* (a needless consent tap is
cheap; blurting a doctor's appointment aloud is the harm). Tune it by editing the
example lists or `DECISION_MARGIN`. If `sentence-transformers` isn't installed it
falls back to a transparent keyword heuristic (and says so).

Then run the reminder runner. It **keeps the microphone off** until a reminder is
actually due:

```bash
python -m robot.apps.mic_remember   # NO_OHBOT=1 to use the OS voice instead of the robot
```

Its pipeline per reminder: poll the clock (no audio) → check the reminder's
**sensitivity** → confirm the owner is present (watch connected). A
**non-sensitive** reminder is simply spoken at its time — the mic never opens. A
**sensitive** one opens a **monitoring window** (default **5 min**, `--lead`)
ending at the reminder's time: the mic records **continuously** for the whole
window (no on/off gaps), and the recording is analysed **once, at the due time**.
Any non-owner voice heard *anywhere* in the window is **remembered**, so it does
not matter whether they speak at the start or the end. The window **only detects
who is present**; the consent prompt is **deferred to the due time**, so the watch
buzzes when the reminder is actually due — not minutes early. The reminder is
spoken at its scheduled time.

| Reminder | Who's around | What the robot does **at the due time** |
| --- | --- | --- |
| Non-sensitive | (not checked) | Speaks it aloud at its time — no presence check, no consent, mic stays off |
| Sensitive | Owner alone (no other voice heard all window) | Speaks the reminder aloud — no one to overhear |
| Sensitive | A bystander was heard during the window | A **remembered** bystander reuses their stored **Yes/No** (no prompt); an **unknown** one is **asked on the watch now**: **Yes** → speak aloud; **No / no-reply** → **private note to the wrist** (and a neutral *"Hello there."*) |
| Sensitive | Owner left during the window | **Holds** — not spoken to an empty room; retried when the owner is back |

The sensitivity label is normally computed once at add time and stored on the
reminder; a reminder saved before the classifier existed is classified live in
the runner instead.

**Known limitations (voice-only, on purpose):** the mic is on for the whole
window (nothing missed in a gap), but a longer recording takes a few seconds to
embed at the due time; a bystander who is present but **silent** the whole window
can't be heard (the camera pipeline covers silent presence); all non-owner voices
in the window are averaged into **one** id, so two different simultaneous
bystanders merge (fine for owner-plus-one); and "same person" reuse is
voice-similarity based (`VOICE_SAME_SPEAKER`), so a weak re-match mints a new id
and re-asks.

**Voice detection (tuned for a distant bystander).** The recording counts as
containing a voice if **either** ≥ `--min-voiced` of the 100 ms blocks clear
`--gate` (*sustained* close talking) **or** ≥ 2 blocks exceed `--peak`
(*bursty/distant* talking, whose average is low but whose syllables peak) — a real
far-field voice was being missed by a sustained-only test. The analysis logs
`frac`, the loud-block count, and `block RMS peak/mean`, so a non-detection is
diagnosable: a **peak near 0** means
the mic isn't *hearing* the source (a device/level problem — check
`VOICE_INPUT_DEVICE`/volume; playing a video does **not** inject audio into the
mic, it must be picked up acoustically), whereas a **peak above the gate that
still doesn't trigger** just wants lower thresholds. Raise the three knobs to
ignore louder background media; lower them to catch a fainter bystander.

A reminder that errors during delivery is **left pending and retried** (up to
`MAX_DELIVERY_ATTEMPTS`), so a transient hiccup doesn't silently lose it. Watch
notification is fire-and-forget, so this remains a best-effort prototype rather
than guaranteed delivery. Decisions are remembered per bystander in
`consent_cache_voice.json` (the voice modality's own consent cache).

> Requires the voice-reminder deps (`openai-whisper`, `dateparser`,
> `sentence-transformers` — included in
> [`requirements.txt`](requirements.txt)) and the updated
> `bangle/consent_app.js` flashed to the watch (the No-path uses its `notify()`
> function). Whisper downloads its model (~140 MB for `base.en`) into
> `~/.cache/whisper`, and the sensitivity classifier downloads a ~80 MB MiniLM
> model to the HuggingFace cache, both on first use.

---

## What the robot says

| Situation | Channel | Message |
| --- | --- | --- |
| Consent request (bystander present) | **Watch** (buzz + Yes/No) | *"I have noticed that someone is present with you. Do you want me to send private reminders in front of them?"* |
| Reminder **Yes** / owner alone / non-sensitive | **Ohbot** (spoken) | *"Here is your reminder. `<text>`."* |
| Reminder **No** / no reply | **Watch** (private note) | *"Reminder: `<text>`"* |
| Reminder **No** | **Ohbot** (spoken) | *"Hello there."* |

---

## Configuration reference

### Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `OHBOT_PORT` | `Pico` | Serial-port hint passed to `ohbot.init()`. |
| `NO_OHBOT` | unset | Set to `1` to skip the Ohbot entirely and speak via the OS voice (`say` on macOS, `espeak` on Linux). Lets you test the watch consent + memory flow without the robot plugged in. |
| `VOICE_INPUT_DEVICE` | PortAudio default | Microphone device index or case-insensitive name substring; shared by all voice scripts. |

Example — run without the robot:

```bash
NO_OHBOT=1 python -m robot.apps.camera_remember
```

### Tunable thresholds

Defined at the top of [`camera_remember.py`](robot/apps/camera_remember.py)
and [`face_id.py`](robot/perception/face_id.py):

| Constant | Value | Meaning |
| --- | --- | --- |
| `REMINDER_POLL_S` | `1.0` | How often the camera loop re-reads `reminders.json` for a due reminder. |
| `CONSENT_TIMEOUT_S` | `30.0` | How long to wait for a watch tap before defaulting to withhold. |
| `SFACE_COSINE_SAME_PERSON` | `0.363` | Cosine threshold for "same bystander" re-identification. |
| `SFACE_OWNER_THRESHOLD` | `0.50` | Tighter threshold for matching the enrolled owner. |

(The voice runner adds its own knobs — `--lead`, `--gate`, `--min-voiced`,
`--peak`; see [Voice reminders](#voice-reminders-schedule-private-content-by-voice).)

---

## Watch ⇄ laptop protocol

Communication is line-oriented over the **Nordic UART Service (NUS)**:

- **Watch → laptop**
  - `CONSENT:<id>:YES` / `CONSENT:<id>:NO` — the user's answer to prompt `<id>`.
- **Laptop → watch**
  - `consent("<id>","<message>")\n` — a JS call the watch's REPL evaluates; it
    buzzes, shows the Yes/No prompt, and replies with a `CONSENT:` line. Strings
    are JSON-encoded so quotes/newlines are escaped safely, and writes are chunked
    to ≤20 bytes for the Espruino BLE UART.
  - `notify("<message>")\n` — a one-way JS call that buzzes and shows a private
    note with an OK button. It sends no acknowledgement to the laptop.

NUS characteristics: RX (watch→laptop notify) `6e400003-…`, TX (laptop→watch
write) `6e400002-…`.

---

## Runtime state files

These live under `robot/state/` as local, per-machine state (gitignored):

| File | Created by | Contents |
| --- | --- | --- |
| `models/*.onnx` | `face_id.ensure_models()` | YuNet + SFace weights, auto-downloaded once. |
| `owner_face.json` | `enroll_face.py` | Averaged owner **face** embedding + metadata. |
| `face_db.json` | `camera_remember.py` | Bystander **face** gallery (stable `person_NNN` IDs). |
| `consent_cache.json` | `camera_remember.py` | Remembered Yes/No decisions (camera), keyed by bystander. |
| `owner_voice.json` | `enroll_voice.py` | Averaged owner **voice** embedding + metadata. |
| `voice_db.json` | `mic_remember.py` | Bystander **voice** gallery (stable `person_NNN` IDs). |
| `consent_cache_voice.json` | `mic_remember.py` | Remembered Yes/No decisions (voice), keyed by bystander. |
| `reminders.json` | `add_reminder.py` | Scheduled reminders (text + due time + delivered flag + sensitivity label). |

These all live under `robot/state/`, which is gitignored, so the biometric
templates, consent caches, and `reminders.json` alike stay out of commits. The
exact JSON schemas and reset implications are documented in
[`docs/codebase_guide.md`](docs/codebase_guide.md#7-runtime-data-and-schemas).

Delete a `consent_cache*.json` to make the robot "forget" all preferences for that
modality; delete a `*_db.json` to reset bystander identities; re-run the matching
`enroll_face`/`enroll_voice` script to replace an owner template.

---

## Troubleshooting

- **The watch never prompts / nothing happens.** The prompt only appears for a
  **sensitive** reminder that is **due** while a **bystander is present** and the
  **watch is connected**. Confirm a reminder is actually due (its time has
  arrived) — the camera overlay shows the next due time, and `mic_remember.py`
  logs it. A non-sensitive reminder, or the owner alone, is spoken with no prompt.
- **Watch not found / consent never delivered.** Make sure the **Espruino Web IDE
  is disconnected** — only one BLE master may hold the watch. Confirm
  `consent_app.js` is running (the watch shows a "Robot linked" screen).
- **Ohbot init hangs.** The robot is likely not on the expected serial port. Set
  `OHBOT_PORT`, or run with `NO_OHBOT=1` to use the laptop voice instead.
- **No speech even with the robot.** Ensure **espeak** is installed (the SDK uses
  it to synthesize). On macOS, audio is played via `afplay` of the generated
  `ohbotspeech.wav`.
- **Camera won't open.** Close anything else using the webcam (Zoom, Teams,
  browser tabs). On macOS the first run prompts for Camera permission for your
  terminal / IDE.
