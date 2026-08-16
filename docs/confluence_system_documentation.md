# Presence-Aware Social Robot with Watch-Mediated Consent

## Document control

| Field | Value |
| --- | --- |
| Document type | System and operations documentation |
| Project | MSc thesis prototype: Presence-Aware Social Robot with Watch-Mediated Consent |
| Status | Research prototype / draft for evaluation |
| Version | 1.2 |
| Last updated | 16 July 2026 |
| Document owner | [Add name] |
| Intended audience | Thesis supervisors, researchers, developers, and demo operators |
| Repository | `Master-Thesis` |

## 1. Executive summary

This prototype studies how a social robot can deliver private scheduled
reminders without disclosing their content to nearby people without the owner's
consent.

The system combines:

- a Bangle.js smartwatch as an owner-presence proxy and for private Yes/No
  decisions and private notifications;
- a laptop for presence sensing, identity matching, consent policy, and local
  persistence;
- a webcam or microphone for detecting and identifying bystanders; and
- an Ohbot desktop robot for spoken output and movement.

The trigger is a scheduled reminder. The owner records a reminder ahead of time
- for example a doctor's appointment - and the laptop transcribes it, extracts
its due time, and classifies it as sensitive or non-sensitive. When the reminder
becomes due, a non-sensitive reminder is simply spoken. A sensitive reminder is
delivered only when it is safe: if the owner is alone it is spoken, but if a
bystander is present the system asks the owner privately on the watch before
speaking. A positive or negative answer can be remembered for that bystander, so
the robot does not need to ask again during a later encounter. Timeouts and
missing answers do not create consent records; the reminder is instead pushed
privately to the wrist.

The same reminder-triggered policy is available through two presence modalities:
a camera pipeline that gates on who the webcam sees, and a voice pipeline that
gates on who the microphone hears. Owner presence in the room is established by
the watch's BLE link, and a due reminder is held until the watch is in range.

## 2. Purpose and scope

### 2.1 Purpose

The system is designed to investigate whether private, watch-mediated consent
and per-bystander consent memory can reduce privacy risks and repeated
interruptions in human-robot interaction.

### 2.2 In scope

- Reminder-due triggering with local sensitivity classification of reminder
  content.
- Camera-based face presence and identity matching.
- Microphone-based voice presence and speaker matching.
- Owner enrollment for camera and voice modalities.
- Private watch consent prompts.
- Cache-memory and re-consent policies.
- Spoken Ohbot output with an operating-system speech fallback.
- Local scheduled reminders created from speech.
- Local JSON persistence for identity, consent, and reminder state.
- Reproducible camera and voice algorithm benchmarks.

### 2.3 Out of scope

- Clinical or medical interpretation of reminder content.
- Production-grade biometric recognition.
- Multi-owner or multi-subject consent arbitration.
- Authenticated or security-hardened BLE communication.
- Cloud synchronization or remote state management.
- Guaranteed reminder delivery.
- Large-scale identity galleries.

## 3. Goals and design principles

| Principle | Application in this system |
| --- | --- |
| Privacy by default | Private content is withheld unless the applicable policy has an affirmative decision. |
| Private decision channel | The consent question and answer are handled on the watch, not spoken by the robot. |
| Purpose-scoped consent | Decisions are stored by detected bystander group and content type. Reminder consent is remembered per bystander and reused across reminders. |
| No inferred consent | A timeout, disconnect, or missing response is not stored as a negative preference. |
| Data minimization | Raw camera frames and audio are processed in memory and are not saved by the live applications. Identity is represented by embeddings. |
| Local processing | Presence, recognition, consent policy, transcription, and state storage run on the laptop. Model weights may be downloaded during setup. |
| Auditability | Runtime state is stored in small JSON files that can be inspected and deleted. |
| Deployability | The primary stack is CPU-compatible and installed through Python packages, plus a small number of system dependencies. |

## 4. System context

| Component | Responsibility | Connection |
| --- | --- | --- |
| Bangle.js smartwatch | Owner-presence proxy, private consent prompt, private notification display, buzzer | Bluetooth Low Energy using Nordic UART Service |
| Laptop | Application orchestration, camera/mic capture, recognition, policy, persistence, UI, model inference | Central host |
| Webcam | Face presence and identity input | Local camera interface |
| Microphone | Voice presence, speaker identity, and reminder-command input | PortAudio through `sounddevice` |
| Ohbot | Spoken public output, lip synchronization, and head movement | USB serial |
| Local JSON files | Owner templates, identity galleries, consent decisions, reminders | Laptop filesystem |

### 4.1 High-level data flow

```text
Bangle.js -- consent replies --------> Laptop policy
Bangle.js <-- consent prompts / private notes -- Laptop policy

Webcam ---- face observations ------> Laptop identity and presence
Microphone - voice observations ----> Laptop identity and presence

Laptop ---- speech and movement ----> Ohbot
Laptop <--- read/write -------------- Local JSON state
```

The watch connection is used as a best-effort proxy for the owner's presence.
The camera or microphone answers the separate question: "Who else can currently
see or hear the robot?"

## 5. Architecture and module responsibilities

| Repository path | Responsibility |
| --- | --- |
| `bangle/consent_app.js` | Bangle.js idle "Robot linked / consent ready" screen, consent UI, and private-note UI. |
| `robot/paths.py` | Centralised on-disk paths for runtime state and downloaded model weights under `robot/state`. |
| `robot/core/policy.py` | BLE lifecycle, incoming line parser, owner-presence (BLE link) check, consent request/response correlation, one-way watch notification, and consent persistence. |
| `robot/apps/camera_remember.py` | Camera-based, reminder-triggered cache-memory application. |
| `robot/apps/camera_reask.py` | Camera-based, reminder-triggered always-ask (re-consent) baseline. |
| `robot/core/robot_io.py` | Shared voice support module: Ohbot glue, on-disk paths, reminder templates, spoken/withhold behaviours, and averaged bystander identification. Imported by the shared voice engine `robot/core/voice_reminder.py`; a support module, no longer run directly. |
| `robot/perception/face_id.py` | YuNet face detection, SFace embedding, and automatic model acquisition. |
| `robot/perception/voice_id.py` | Resemblyzer preprocessing, voiced-window segmentation, and speaker embeddings. |
| `robot/perception/face_db.py` | Modality-independent embedding gallery and stable `person_NNN` assignment. The name is historical; it is also used for voices. |
| `robot/core/owner.py` | Modality-independent owner-template persistence and cosine matching. |
| `robot/apps/enroll_face.py` | Camera owner enrollment and verification. |
| `robot/apps/enroll_voice.py` | Voice owner enrollment and verification. |
| `robot/perception/audio_device.py` | Shared microphone-device resolution. |
| `robot/core/reminders.py` | Reminder model, due/pending queries, and atomic JSON storage. |
| `robot/apps/add_reminder.py` | Reminder recording, local Whisper transcription, date parsing, sensitivity classification, confirmation, and storage. |
| `robot/core/sensitivity.py` | Local sentence-transformer sensitivity classifier (embedding + cosine against labelled prototypes, with a high-precision keyword override and keyword fallback). |
| `robot/core/voice_reminder.py` | Shared voice engine: due-time polling, continuous pre-reminder recording, voice-presence analysis, and presence-gated reminder delivery. Wrapped by the two voice apps below. |
| `robot/apps/mic_remember.py` | Voice-based, reminder-triggered cache-memory application. Thin wrapper over `robot/core/voice_reminder.py`. |
| `robot/apps/mic_reask.py` | Voice-based, reminder-triggered always-ask (re-consent) baseline. Thin wrapper over `robot/core/voice_reminder.py`. |
| `robot/bench/` | Algorithm benchmark, evaluation-set capture, and result tables. |
| `ohbot/ohbotData/` | Ohbot SDK motor, speech, and settings assets. |

## 6. Functional workflows

### 6.1 Camera cache-memory workflow

Entry point: `robot/apps/camera_remember.py`

1. The application opens the webcam and initializes the Ohbot unless
   `NO_OHBOT=1` is set.
2. YuNet and SFace model files are downloaded on first use if absent.
3. The enrolled owner template, face gallery, consent cache, and reminder store
   are loaded.
4. The application scans for and connects to the Bangle.js watch.
5. Haar face detection runs on each frame only to show a live face count on the
   heads-up display; it no longer drives the trigger.
6. Every `REMINDER_POLL_S` the application re-reads `reminders.json` and checks
   whether any reminder is due.
7. When a reminder becomes due, delivery proceeds only if the watch is connected
   (the owner-presence proxy); otherwise the reminder is held.
8. The reminder's sensitivity label is read, or classified live if it is
   missing. A non-sensitive reminder is spoken immediately, with no presence
   check and no consent.
9. For a sensitive reminder, a copy of the current frame is passed to a daemon
   delivery worker.
10. YuNet detects precise faces and SFace creates one embedding per face.
11. The highest-similarity face above the owner threshold is removed; if the
    owner is not on camera every detected face is treated as a bystander.
12. Remaining faces are matched to the gallery or assigned new `person_NNN`
    identifiers, and sorted unique bystander IDs form a group key such as
    `person_001:person_003`.
13. If no bystander is in view the owner is taken to be alone and the reminder is
    spoken.
14. Otherwise the application looks up the group key with content type
    `reminder`.
15. A cached Yes discloses without asking; a cached No withholds (a private note
    to the wrist) without asking.
16. A cache miss produces a private Yes/No prompt on the watch.
17. Explicit Yes/No answers are stored. No response or disconnect is not stored.
18. The reminder is marked delivered after the attempt.

Camera behavior: on a Yes or an owner-alone scene the robot speaks the reminder
("Here is your reminder. \<text>."). On a No or no reply the reminder is pushed
privately to the wrist with `notify("Reminder: <text>")` and the robot says the
neutral line "Hello there."

### 6.2 Camera re-consent workflow

Entry point: `robot/apps/camera_reask.py`

This flow uses the same camera, owner enrollment, face embedding, bystander
gallery, reminder trigger, watch, and robot behavior as the camera cache-memory
flow. The difference is that it does not use `ConsentStore` and always asks the
watch for a new decision whenever a sensitive reminder is due with a bystander
present.

The shared `face_db.json` is still used to identify and log people, but a
previous Yes or No never suppresses a later prompt.

### 6.3 Voice reminder workflow

Entry points: `robot/apps/mic_remember.py` (cache-memory) and
`robot/apps/mic_reask.py` (re-consent) - two thin wrappers over the shared voice
engine `robot/core/voice_reminder.py`. The engine, together with the shared
support module `robot/core/robot_io.py` (Ohbot glue, on-disk paths, reminder
templates, spoken/withhold behaviours, and averaged bystander identification),
drives the workflow below; `robot_io` is imported (`import robot.core.robot_io as
demo`) and is no longer run directly.

1. The runner loads the owner voice template, speaker gallery, voice consent
   cache, and reminder store.
2. It pins a valid input device but does not open the microphone; the mic stays
   off while waiting.
3. The runner polls the local clock; a reminder counts as approaching once the
   current time is within the lead window (default five minutes, `--lead`) of
   its due time.
4. When a reminder approaches, its sensitivity label is read, or classified
   live if it is missing. A non-sensitive reminder waits out the window with the
   mic closed and is simply spoken at its due time.
5. For a sensitive reminder, the runner requires the watch connection as its
   owner-presence signal, then records the whole pre-reminder window
   continuously - there is no on/off sampling, so a bystander who speaks at any
   instant is captured.
6. At the due time the entire recording is analysed once. A dual energy test
   (sustained OR bursty, see below) decides whether any voice is present; if so,
   Resemblyzer embeds the non-owner voiced windows, owner-matching windows are
   subtracted, the remaining windows are averaged into one embedding, and the
   result is matched to `voice_db.json` to remember the bystander.
7. The consent decision is deferred to the due time: the watch buzzes when the
   reminder is due, not minutes early.
8. If no non-owner voice was heard the owner is assumed alone and the reminder
   is spoken.
9. If a bystander was heard, consent is keyed by the bystander and content type
   `reminder`: a remembered Yes/No is reused, and an unknown bystander is asked
   on the watch.
10. Yes speaks the reminder; No or no reply pushes it privately to the wrist
    with `notify(...)` and the robot says the neutral line "Hello there."

Cache-memory vs re-consent: the workflow above is the cache-memory voice app
`mic_remember`, which stores each bystander's Yes/No in the voice consent cache
and reuses it (step 9). Its re-consent counterpart `mic_reask` runs the same
voice pipeline, owner enrollment, speaker gallery, reminder trigger, watch, and
robot behaviour, but does not use `ConsentStore`: it asks the watch for a new
decision every time a sensitive reminder is due with a bystander present, and
stores nothing. The shared `voice_db.json` is still used to identify and log
speakers, but a previous Yes or No never suppresses a later prompt. This mirrors
the camera pair (`camera_remember` / `camera_reask`); `mic_reask` is the voice
equivalent of the camera re-consent baseline (section 6.2).

Voice detection: the dual energy test is tuned to catch a distant, quiet
bystander. A recording counts as containing a voice if a sustained fraction of
100 ms blocks exceed the RMS gate (`--gate` / `--min-voiced`) OR at least a
couple of blocks exceed a louder peak (`--peak`) - the peak test rescues
far-field speech whose average energy is low but whose syllables still peak.

The voice modality does not perform source separation or full diarization. A
bystander who stays completely silent for the whole window cannot be detected,
and two simultaneous speakers merge into a single bystander identity.

Delivery is retried on transient failure: a reminder whose delivery raises is
left pending and retried up to a capped number of attempts, and it is held (not
delivered) whenever the owner is out of BLE range at the moment of delivery.

### 6.4 Reminder creation workflow

Entry point: `robot/apps/add_reminder.py`

1. The script records a fixed-length clip from the configured microphone.
2. Whisper transcribes the float32 audio locally in English.
3. dateparser searches the transcript for a future date/time.
4. The command prefix is removed from the stored reminder text.
5. The sensitivity classifier (`robot/core/sensitivity.py`) labels the reminder
   sensitive or non-sensitive.
6. The terminal displays the interpreted subject, time, and sensitivity label
   with a short reason.
7. The operator chooses save, switch the sensitivity label (press `s`), retry,
   or quit.
8. A saved reminder receives an ID such as `rem_001` and is written to
   `reminders.json` together with its `sensitive` flag.

The default recording duration is eight seconds and the default Whisper model
is `base.en`.

The classifier runs locally and offline. A sentence-transformer
(`all-MiniLM-L6-v2`) embeds the reminder text and compares it by cosine
similarity to small labelled prototype sets of sensitive and everyday reminders,
with a high-precision keyword override for explicit medical or financial terms.
On a near-tie it defaults to sensitive, the privacy-safe choice. If
sentence-transformers is unavailable it falls back to a keyword heuristic and
prints that it has done so. This reuses the same embedding-plus-cosine approach
as the voice (Resemblyzer d-vector) and face (SFace) identity models. The owner
can flip the classifier's label at the confirm step.

### 6.5 Shared reminder delivery policy

Both presence modalities apply the same policy when a reminder becomes due.

1. Owner presence in the room is the watch BLE link. A due reminder is held
   until the watch is in range.
2. A non-sensitive reminder is spoken with no presence check and no consent.
3. A sensitive reminder with no bystander sensed (owner alone) is spoken.
4. A sensitive reminder with a bystander present is gated on watch consent:
   - a remembered decision for that bystander is reused (cache-memory flows
     only);
   - Yes: the Ohbot speaks the reminder ("Here is your reminder. \<text>.");
   - No or no reply: the reminder is pushed privately to the wrist
     (`notify()`: "Reminder: \<text>") and the Ohbot only greets neutrally
     ("Hello there.").
5. Explicit Yes/No answers are stored (cache-memory flows); a timeout or missing
   answer is treated as no decision and is not stored.

The consent prompt text is: "I have noticed that someone is present with you. Do
you want me to send private reminders in front of them?"

Delivery semantics differ slightly by modality. The camera demos mark a reminder
delivered after a single attempt, even when policy execution raises an
exception. The voice runner instead leaves a reminder pending and retries on
transient failure up to a capped number of attempts, and holds (does not
deliver) a reminder whenever the owner is out of BLE range at the moment of
delivery. Watch `notify(...)` does not acknowledge successful display.

## 7. Consent decision model

### 7.1 Consent key

```text
ConsentKey(
    bystander_id = sorted unique bystander IDs joined with ":",
    content_type = purpose-specific content identifier
)
```

Examples:

```text
(person_001, reminder)
(person_001:person_003, reminder)
```

A person and a group containing that person are separate consent contexts.
Permission for `person_001` does not imply permission for
`person_001:person_003`. All reminders share the single `reminder` content type,
so a stored decision for a bystander is reused for every reminder while that
bystander is present.

### 7.2 Decision matrix

| Context | Stored value / answer | Public robot action | Private watch action | Persist decision? |
| --- | --- | --- | --- | --- |
| Non-sensitive reminder | Not applicable | Speak reminder | None | No consent needed |
| Sensitive reminder, no bystander sensed | Not applicable | Speak reminder | None | No consent needed |
| Sensitive reminder, bystander, cache hit | Yes | Speak reminder | None | Already stored |
| Sensitive reminder, bystander, cache hit | No | Say neutral greeting | Show reminder note | Already stored |
| Sensitive reminder, bystander, cache miss | Yes | Speak reminder | Consent prompt | Yes |
| Sensitive reminder, bystander, cache miss | No | Say neutral greeting | Consent prompt, then reminder note | Yes |
| Sensitive reminder, bystander, cache miss | Timeout/no reply | Do not speak reminder | Best-effort reminder note | No |

## 8. Triggering and holding

### 8.1 Reminder trigger

A reminder fires when it becomes due: its scheduled time has arrived - or, for
the voice runner, the lead window before it has opened - and it has not yet been
delivered. Delivery additionally requires the watch to be connected as the
owner-presence proxy. The reminder store is re-read from disk on a short interval
(`REMINDER_POLL_S`, 1.0 seconds in the camera demos), so a reminder added while a
session is running is picked up without a restart.

Whether a reminder prompts on the watch depends on its sensitivity and who is
sensed at the due time. A non-sensitive reminder, or a sensitive reminder with
the owner alone, is delivered with no prompt. Only a sensitive reminder with a
bystander present and no remembered decision produces a consent prompt.

### 8.2 Holding and re-attempts

Each reminder fires at most once: once it is delivered - or given up after
repeated failures - it is marked delivered and is not retried. A due reminder
that cannot yet be delivered is held rather than dropped, and re-attempted when
conditions allow. Holds occur when:

- the watch (owner-presence proxy) is not connected at the due time;
- the owner leaves BLE range during the voice runner's monitoring window; or
- a transient microphone, BLE, or embedding error occurs during voice delivery
  (retried up to a capped number of attempts).

The camera demos serialize delivery so only one delivery worker runs at a time;
a newly due reminder is not delivered while another is still being handled.

## 9. Hardware and software prerequisites

### 9.1 Hardware

- Bangle.js smartwatch.
- Ohbot desktop robot and USB cable, unless using `NO_OHBOT=1`.
- Laptop with Bluetooth Low Energy.
- Webcam for camera workflows.
- Microphone for voice and reminder workflows.

### 9.2 Software

- Modern Python. The code uses Python 3.10+ syntax; the documented benchmark
  environment used CPython 3.13.
- Python dependencies from `requirements.txt` at the repository root.
- espeak for Ohbot speech on macOS/Linux.
- PortAudio system library on Linux for `sounddevice`.
- Chrome or Edge with Web Bluetooth for initially loading the watch script.

### 9.3 Python dependencies

The main requirements include:

- NumPy;
- OpenCV;
- bleak;
- Ohbot SDK;
- sounddevice;
- Resemblyzer and its Torch dependency;
- openai-whisper; and
- dateparser.

## 10. Installation

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

System speech dependency:

```bash
# macOS
brew install espeak

# Debian/Ubuntu
sudo apt install espeak libportaudio2
```

First-run downloads can include:

- YuNet and SFace ONNX files under `robot/state/models/`;
- the configured Whisper model under the user's Whisper cache; and
- optional benchmark challenger models when benchmark scripts are used.

## 11. Watch setup

1. Open `https://www.espruino.com/ide/` in Chrome or Edge.
2. Connect to the Bangle.js through Web Bluetooth.
3. Paste `bangle/consent_app.js` into the editor.
4. Select **Send to Espruino**.
5. Optionally run `save()` in the Espruino REPL to survive a reboot.
6. Disconnect the Web IDE before starting a Python application. Only one BLE
   central should own the watch connection.

Expected watch idle screen:

- `Robot linked`; and
- `consent ready`.

## 12. Operating procedures

### 12.1 Camera enrollment

```bash
python -m robot.apps.enroll_face
```

- Sit alone and look toward the camera.
- The script collects 12 eligible face embeddings.
- Zero or multiple faces pause sampling.
- After saving, use the verification view to compare owner and other faces.
- Press `q` to exit.

### 12.2 Voice enrollment

```bash
python -m robot.apps.enroll_voice
```

- Speak alone in full sentences.
- The script collects 20 voiced-window embeddings.
- After saving, use the verification view with owner and non-owner speech.
- Press `q` to exit.

### 12.3 Camera cache-memory session

```bash
python -m robot.apps.camera_remember
```

### 12.4 Camera re-consent session

```bash
python -m robot.apps.camera_reask
```

### 12.5 Create a reminder

```bash
python -m robot.apps.add_reminder
```

Example phrase:

```text
Remind me about my doctor's appointment on July 20th at 3 PM.
```

Optional arguments:

```bash
python -m robot.apps.add_reminder --seconds 10 --model small.en
```

### 12.6 Voice reminder sessions

Cache-memory (remembers a bystander's Yes/No and reuses it):

```bash
python -m robot.apps.mic_remember
```

Re-consent (asks the watch every time, stores nothing):

```bash
python -m robot.apps.mic_reask
```

Optional arguments (either app):

```bash
python -m robot.apps.mic_remember --lead 120 --gate 0.02
```

Stop the reminder runner with `Ctrl-C`.

### 12.7 Run without the Ohbot

```bash
NO_OHBOT=1 python -m robot.apps.camera_remember
NO_OHBOT=1 python -m robot.apps.mic_remember
```

macOS uses `say`; Linux uses `espeak`.

## 13. Configuration

### 13.1 Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `OHBOT_PORT` | `Pico` | Serial-port hint passed to `ohbot.init`. |
| `NO_OHBOT` | Unset | Set to `1` to skip Ohbot initialization and use OS TTS. |
| `VOICE_INPUT_DEVICE` | PortAudio default | Numeric input-device index or case-insensitive substring of the device name. |
| `CAMERA_DEVICE` | First external camera, else index 0 | Numeric capture index or case-insensitive substring of the camera name. The default selects the USB webcam mounted on the robot's head, skipping the built-in and any phone Continuity Camera. |
| `CAMERA_RES` | Camera default | Requested capture resolution as `WIDTHxHEIGHT` (for example `1280x720`). |
| `HEAD_SCAN` | Enabled | Set to `0` to disable the head sweep performed before a sensitive delivery. Implicitly disabled under `NO_OHBOT=1`. |
| `HEAD_SCAN_POSITIONS` | `2,5,8` | Comma-separated Ohbot `HEADTURN` positions (0–10, 5 = straight ahead) visited during the sweep. |
| `HEAD_SCAN_SETTLE_S` | `0.9` | Seconds allowed for the head to stop moving before a frame from that position is used. |

### 13.2 Key camera and policy constants

| Constant | Value | Meaning |
| --- | --- | --- |
| `REMINDER_POLL_S` | 1.0 seconds | Interval for re-reading `reminders.json` from the camera loop. |
| `SFACE_COSINE_SAME_PERSON` | 0.363 | Face gallery same-person threshold. |
| `SFACE_OWNER_THRESHOLD` | 0.50 | Owner face threshold. |
| `CONSENT_TIMEOUT_S` | 30.0 seconds | Laptop consent wait before safe fallback. |

### 13.3 Key voice constants

| Constant | Value | Meaning |
| --- | --- | --- |
| `VOICE_SR` | 16,000 Hz | Audio sample rate. |
| Voice block | 100 ms | Energy-analysis block duration. |
| `DEFAULT_LEAD_S` (`--lead`) | 300 seconds (5 min) | Continuous pre-reminder recording window. |
| `DEFAULT_POLL_S` (`--poll`) | 2.0 seconds | Idle clock-check interval while the mic is off. |
| `MIN_RECORD_S` | 5.0 seconds | Minimum recording for a past-due or collapsed window. |
| `DEFAULT_RMS_GATE` (`--gate`) | 0.02 | RMS gate for the sustained-speech test. |
| `DEFAULT_VOICED_FRACTION_MIN` (`--min-voiced`) | 0.06 | Fraction of blocks over the gate for sustained speech. |
| `DEFAULT_PEAK_RMS` (`--peak`) | 0.035 | RMS for the bursty/distant-speech test. |
| `PEAK_MIN_BLOCKS` | 2 | Loud blocks over the peak that count as a voice. |
| `MAX_DELIVERY_ATTEMPTS` | 3 | Retry cap for a failing voice delivery. |
| `VOICE_SAME_SPEAKER` | 0.70 | Speaker gallery threshold. |
| `VOICE_OWNER_THRESHOLD` | 0.73 | Owner voice threshold. |

Thresholds are source constants; the repository does not currently provide an
external runtime configuration file.

## 14. BLE watch protocol

Communication uses newline-delimited UTF-8 over the Nordic UART Service.

| Direction | Frame or expression | Meaning |
| --- | --- | --- |
| Watch to laptop | `CONSENT:<id>:YES` | Positive answer for the correlation ID. |
| Watch to laptop | `CONSENT:<id>:NO` | Negative answer for the correlation ID. |
| Laptop to watch | `consent("<id>","<message>");` | Buzz and display a Yes/No prompt. |
| Laptop to watch | `notify("<message>");` | Buzz and display a one-way private note with an OK button. |

Nordic UART UUIDs:

```text
Watch to laptop notifications: 6e400003-b5a3-f393-e0a9-e50e24dcca9e
Laptop to watch writes:         6e400002-b5a3-f393-e0a9-e50e24dcca9e
```

Protocol behavior:

- Prompt IDs are generated as `p1`, `p2`, and so on per process.
- JavaScript strings are encoded with JSON escaping.
- Laptop-to-watch payloads are split into writes of at most 20 bytes.
- A five-millisecond delay is inserted between chunks.
- A leading newline flushes a stale partial Espruino REPL line.
- The watch disables REPL echo on load and on BLE reconnect.
- A second overlapping `consent(...)` call is immediately answered No by the
  watch.
- The laptop owns the 30-second prompt timeout.
- `notify(...)` has no response or delivery acknowledgement.

## 15. Concurrency model

| Execution context | Responsibilities |
| --- | --- |
| Main thread | Camera status and HUD, reminder polling, and delivery dispatch with OpenCV UI (camera demos); clock polling and continuous recording (voice runner). |
| BLE background thread | asyncio event loop, scan/connect, UART notifications, chunked writes, and consent futures. |
| Delivery daemon worker (camera) | Embedding, identity matching, cache lookup, blocking consent wait, and speech. |
| PortAudio recording (voice runner) | Fills the recording buffer in the background during a monitoring window. |

Synchronization rules:

- Only one delivery worker may own the delivery slot (camera demos).
- Ohbot SDK calls are serialized with `ohbot_lock`.
- JSON stores and audio buffers use dedicated locks.
- Delivery workers receive frame copies or audio snapshots rather than live
  mutable capture buffers.
- Worker threads are daemons so a pending consent prompt cannot prevent process
  exit.
- Shutdown waits up to ten seconds for the Ohbot lock before relying on process
  exit to release the serial port.

## 16. Runtime data and retention

All runtime state is stored under `robot/state/`.

| File | Data | Sensitivity | Reset effect |
| --- | --- | --- | --- |
| `owner_face.json` | Averaged 128-D owner face embedding and enrollment metadata | Biometric | Requires camera re-enrollment |
| `face_db.json` | Bystander face embeddings and stable IDs | Biometric | Forgets camera identities; existing camera consent keys become orphaned |
| `consent_cache.json` | Camera reminder Yes/No values by bystander group | Privacy preference | Camera flow asks again |
| `owner_voice.json` | Averaged 256-D owner voice embedding and metadata | Biometric | Requires voice re-enrollment |
| `voice_db.json` | Bystander speaker embeddings and stable IDs | Biometric | Forgets voice identities; existing voice consent keys become orphaned |
| `consent_cache_voice.json` | Voice reminder Yes/No values by bystander group | Privacy preference | Voice flow asks again |
| `reminders.json` | Reminder ID, text, naive local due time, sensitivity label, and delivered flag | Potentially highly sensitive | Removes scheduled reminder history |
| `models/*.onnx` | YuNet and SFace weights | Non-personal model data | Re-downloaded on demand |

Biometric embeddings remain personal/biometric data even though they are
base64-encoded rather than stored as raw images or audio.

The owner, identity, consent, and reminder stores use same-directory temporary
files followed by `os.replace` for atomic updates. A malformed file is logged
and treated as empty in memory.

The repository `.gitignore` covers the entire `robot/state/` directory — the
biometric stores, consent caches, and `reminders.json` alike — so runtime state
(including reminder content) is never committed.

### 16.1 Consent JSON example

```json
{
  "person_001": {
    "reminder": "YES"
  },
  "person_001:person_003": {
    "reminder": "NO"
  }
}
```

### 16.2 Reminder JSON example

```json
{
  "next_id": 2,
  "reminders": [
    {
      "id": "rem_001",
      "text": "Doctor's appointment on July 20th at 3 PM",
      "remind_at": "2026-07-20T15:00",
      "delivered": false,
      "sensitive": true
    }
  ]
}
```

Reminder timestamps are naive laptop-local datetimes with minute precision.
There is no timezone or daylight-saving migration mechanism.

## 17. Privacy and security considerations

### 17.1 Privacy controls

- Consent is requested through a private watch interface.
- Sensitive-reminder disclosure is withheld on timeout or missing consent; the
  reminder is instead delivered privately to the wrist.
- Non-answers are not stored as decisions.
- Consent is scoped by detected bystander group and content purpose.
- Raw live media is not persisted by the application flows.
- State can be reset by deleting the relevant local JSON files.

### 17.2 Residual risks

| Risk | Impact |
| --- | --- |
| BLE range used as owner-presence proxy | The watch can be connected while the owner is outside the intended room, or disconnected while the owner is present. |
| BLE is not authenticated by this application | A nearby attacker may be able to interfere with the research protocol. |
| Face/speaker threshold error | A person can be merged, duplicated, or mistaken for the owner/bystander. |
| Silent bystander in a voice workflow | The system can assume owner-alone and disclose a reminder aloud. |
| Durable consent has no expiry | A past decision remains active until the JSON cache is deleted. |
| No consent management UI | Inspection and revocation require filesystem access. |
| Unacknowledged watch notification | The laptop cannot prove that a private note was displayed or read. |
| Unignored reminder file | Sensitive text can be committed accidentally. |
| Local JSON is not encrypted | A user with filesystem access can read preferences and reminder text. |

This is a GDPR-informed research design, not a claim of legal compliance.

## 18. Failure handling

| Failure | Current behavior |
| --- | --- |
| Watch not found at startup | The demo runs, but reminders are held: the watch is both the owner-presence proxy and the consent channel, so a due reminder is not delivered until the watch is in range. |
| BLE disconnect during prompt | Pending consent resolves as no decision; it is not cached. |
| Consent timeout | Private content is not spoken; no consent value is cached. |
| Watch `notify(...)` write failure | Error is logged; no retry or acknowledgement exists. |
| Camera cannot open | Application exits with guidance to close other camera users, a list of the cameras found, and the `CAMERA_DEVICE` override. |
| Camera opens but never delivers a frame | Application exits after a 5-second warm-up window instead of spinning silently on failed reads. |
| Camera delivers all-black frames | Startup warns (lens cover / privacy shutter) and continues; no face can be detected in a black frame. |
| Head sweep gets no frame at a position | That position is logged and skipped; the delivery proceeds on the positions that did return a view. |
| Head move fails mid-sweep | The error is printed and the sweep continues; the head is returned to centre in a `finally` block. |
| Quit pressed during a sweep | The sweep aborts at the next position boundary and the delivery worker unwinds. |
| Microphone default is invalid | The shared selector uses `VOICE_INPUT_DEVICE`, then a valid default, then the first input device. |
| Face model download fails | Application exits and prints the expected manual destination. |
| Owner template missing | Corresponding demo exits and requests enrollment. |
| JSON load fails | Error is logged and the store starts empty in memory. |
| Ohbot unavailable | Initialization may block/fail; rerun with `NO_OHBOT=1`. |
| Reminder policy raises | Traceback is printed and the reminder is still marked delivered. |

The BLE client performs one startup scan and has no explicit rescan/reconnect
loop. If the watch is absent at startup or the connection is lost, restart the
Python process after making the watch available.

## 19. Troubleshooting

### Watch never prompts

- Disconnect the Espruino Web IDE.
- Confirm the watch displays `Robot linked` / `consent ready`.
- Confirm the application HUD shows `watch=OK`.
- Confirm a reminder is actually due (check `reminders.json` and the next-due
  line in the console).
- Ensure the reminder is sensitive and a non-owner face or voice is present; a
  non-sensitive reminder or an owner-alone scene is delivered without a prompt.
- Restart the Python process if the watch was absent or disconnected; automatic
  reconnection is not implemented.

### Ohbot initialization hangs or fails

- Confirm the USB cable and serial device.
- Set `OHBOT_PORT` to a useful serial-port hint.
- Use `NO_OHBOT=1` to validate the remaining pipeline.
- Confirm espeak is installed.

### Camera does not open

- Close Zoom, Teams, browsers, or other camera applications.
- Grant camera permission to the terminal or IDE.
- Run `python -m robot.apps.list_cameras` to see the cameras found and which one
  the apps will select, and `--preview <index>` to confirm it visually.
- Set `CAMERA_DEVICE` to an index or name substring to pin a specific camera.

### The wrong camera is used, or the preview is black

- The apps prefer the external (head-mounted) webcam; check the USB cable if the
  listing does not show it.
- An all-black preview usually means the lens cover or privacy shutter is closed.

### Microphone does not open

- Grant microphone permission to the terminal or IDE.
- List PortAudio devices and set `VOICE_INPUT_DEVICE` to an index or name
  substring.
- On Debian/Ubuntu, install `libportaudio2`.

### Voice trials abort with no speech

- Speak for long enough to produce at least one usable voiced window.
- Reduce background noise and repeat ambient calibration.
- Confirm the input device is the intended microphone.

### Owner is treated as a bystander

- Re-enroll under representative lighting or acoustic conditions.
- Review owner similarity values in the enrollment verification screen.
- Tune thresholds only with recorded evaluation evidence.

### Consent is unexpectedly reused

- Inspect the relevant `consent_cache*.json` file.
- Confirm the bystander group key and `content_type`.
- Delete the relevant consent cache to force new decisions.

## 20. Known limitations and technical debt

1. Haar is used continuously for the camera HUD face count even though
   repository benchmarks show YuNet is faster on the measured hardware.
2. The first unmatched identity embedding is frozen; matched embeddings do not
   update the gallery.
3. Cosine similarity logic is duplicated in `robot/perception/face_db.py` and
   `robot/core/owner.py`.
4. Voice presence cannot detect silent bystanders.
5. Overlapping speakers are not separated.
6. The watch has no prompt timeout; it relies on the laptop timeout.
7. Watch private notifications have no delivery acknowledgement or retry.
8. The BLE client does not implement an explicit reconnect loop.
9. Camera reminder delivery marks an errored attempt as delivered; the voice
   runner retries a capped number of times before giving up.
10. Reminder timestamps have no timezone metadata.
11. Consent has no expiry, revocation UI, or policy migration mechanism.
12. The repository has benchmark tooling but no automated unit or integration
    test suite.
13. Recognition accuracy/EER results require a labelled evaluation set and are
    still pending in the committed comparison narrative.

## 21. Benchmarking and evaluation

### 21.1 Benchmark commands

```bash
python robot/bench/bench_camera.py
python robot/bench/bench_voice.py
```

Examples with options:

```bash
python robot/bench/bench_camera.py --res 1280x720 --repeats 100
python robot/bench/bench_camera.py --only yunet,mediapipe,sface
python robot/bench/bench_voice.py --repeats 500
```

### 21.2 Evaluation data

The capture helper stores personal face or voice evaluation material under the
gitignored `robot/bench/eval_data/` path.

For defensible accuracy and robustness results, collect:

- at least three people;
- at least two environmental conditions; and
- at least four face images or voice clips per person and condition.

The benchmark harness can then report detection rate, equal error rate, and
d-prime in addition to latency, throughput, memory, and model size.

### 21.3 Current benchmark interpretation

The committed benchmark narrative reports that:

- all shipped lightweight models fit the real-time budget on the measured
  Apple M4 system;
- Haar was slower than YuNet for the measured camera-presence workload;
- ArcFace and SCRFD impose substantially higher memory/latency costs;
- RMS, WebRTC, and Silero VAD are all fast enough that accuracy should drive the
  VAD choice; and
- x-vector was a promising fast speaker-embedding alternative pending accuracy
  evaluation.

Use `docs/algorithm_comparison.md` and
`robot/bench/README.md` for the full method and results.

## 22. Demo readiness checklist

### Before the session

- [ ] Python environment activated and dependencies installed.
- [ ] Bangle.js charged and `consent_app.js` running.
- [ ] Espruino Web IDE disconnected.
- [ ] Owner enrolled for the selected modality.
- [ ] Correct camera or microphone permissions granted.
- [ ] Ohbot connected, or `NO_OHBOT=1` selected.
- [ ] Relevant consent and gallery reset policy decided before participant use.
- [ ] At least one reminder scheduled for the session with the intended
      sensitivity label (`python -m robot.apps.add_reminder`).
- [ ] No real `reminders.json` content is staged for version control.

### During the session

- [ ] HUD reports `watch=OK`.
- [ ] A scheduled reminder has reached its due time and been delivered on the
      intended presence path.
- [ ] Watch decisions are made only by the owner.
- [ ] Operator does not type consent decisions into the terminal.
- [ ] Trial result and bystander key are recorded in the study log if required.

### After the session

- [ ] Stop the application cleanly.
- [ ] Apply the study's retention/deletion policy to biometric and consent JSON.
- [ ] Check `git status` before committing or sharing the repository.
- [ ] Remove participant reminders and evaluation recordings when no longer
      required.

## 23. Repository documentation map

| Document | Purpose |
| --- | --- |
| `README.md` | Operator quick start and overview. |
| `docs/codebase_guide.md` | Source-level entry points, modules, schemas, and current caveats. |
| `docs/design_hld.md` | Requirements, privacy model, design decisions, threat model, and GDPR framing. |
| `docs/technical_hld.md` | Algorithms, thresholds, interfaces, concurrency, and deployment. |
| `docs/algorithm_comparison.md` | Literature-backed algorithm comparison and empirical results. |
| `docs/literature_review.md` | Research background, gaps, and candidate research questions. |
| `robot/bench/README.md` | Benchmark and evaluation-data operating instructions. |

## 24. Glossary

| Term | Definition |
| --- | --- |
| Bystander | A non-owner person whose presence may make spoken content a privacy disclosure. |
| Cache-memory policy | Policy that stores and reuses a bystander-specific Yes/No decision. |
| Consent key | Combination of a sorted bystander-group ID and a purpose-specific content type. |
| Content type | Purpose identifier; reminders use the single content type `reminder`. |
| Embedding | Numeric vector representing face or voice characteristics for similarity matching. |
| Nordic UART Service | BLE service used as a bidirectional text channel between watch and laptop. |
| Owner | The enrolled watch wearer and subject of the private content. |
| Owner subtraction | Removing an owner-matching face or voice window before building the bystander key. |
| Re-consent policy | Baseline policy that requests a new watch answer every time and stores no decision. |
| Trial | One triggered identity, consent, and robot-action evaluation. |
| VAD | Voice activity detection; determines whether an audio block contains speech-like energy. |

## 25. Approval and change history

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 14 July 2026 | [Add name] | Initial consolidated system documentation derived from the repository. |
| 1.1 | 16 July 2026 | [Add name] | Removed heart-rate detection; documented the reminder-due trigger, local sensitivity classifier, and the shared presence-gated delivery policy. |
| 1.2 | 16 July 2026 | [Add name] | Reorganised the codebase into the `robot/` Python package; updated all module paths, run commands (`python -m robot.apps.<name>`), imports, and runtime-state locations (`robot/state/`). |

