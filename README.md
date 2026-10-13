# Presence-Aware Social Robot with Watch-Mediated Consent

A master's-thesis prototype. A desktop robot (**Ohbot**) reads out your
scheduled reminders, but it checks **who else is in the room** first. If a
reminder is private (e.g. a doctor's appointment) and someone else is present,
the robot asks for your permission **on your smartwatch** (**Bangle.js**) before
saying anything out loud. It can also **remember your answer** for each person, so
it doesn't ask again.

Everything runs **locally on the laptop**: no cloud, and no audio or video is
stored.

---

## How it works

1. **You add a reminder**, by voice or typed, e.g. *"remind me about my doctor's
   appointment at 3 PM"*. The app labels it **sensitive** or **not sensitive**.
2. **Shortly before it's due**, the robot checks whether you are nearby (your
   watch is connected) and whether anyone else is present:
   - the **microphone** listens for other voices, and
   - if it hears no one, the **camera** on the robot's head can take a quick look
     around.
3. **At the due time:**

| Situation | What happens |
| --- | --- |
| Not sensitive | The robot says it out loud. |
| Sensitive, you're alone | The robot says it out loud. |
| Sensitive, someone else is present | Your watch buzzes and asks: *"Do you want me to send private reminders in front of them?"* |
| You tap **Yes** | The robot says the reminder out loud. |
| You tap **No** or don't answer | The robot just says *"Hello there."* and the reminder appears privately on your watch. |

The app can either **remember** each person's Yes/No answer or **ask every
time**; you choose when starting it.

---

## What you need

| Device | Used for |
| --- | --- |
| **Laptop** (macOS recommended) with a microphone | Runs the app |
| **Ohbot** robot, connected by USB | Speaks and moves its head |
| **USB webcam mounted on the Ohbot's head** | Sees the room from the robot's view (only needed if you use the camera) |
| **Bangle.js** smartwatch, connected by Bluetooth | Private Yes/No prompts and notes |

---

## Setup (once per laptop)

### 1. Install the software

You need **Python 3.13**. Newer versions don't work yet.

```bash
git clone https://github.com/Aroosa-Batool/Master-Thesis.git
cd Master-Thesis
python3.13 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

The install is large (a few GB) because it includes the speech and recognition
models. Some models also download the first time you run the app, so do one run
with an internet connection before a session.

Install **espeak**, which the robot uses to speak:

```bash
brew install espeak                # macOS
sudo apt install espeak            # Linux
```

### 2. Put the app on the watch

1. Open the [Espruino Web IDE](https://www.espruino.com/ide/) in Chrome or Edge.
2. Connect to the Bangle.js (top-left icon).
3. Paste in [`bangle/consent_app.js`](bangle/consent_app.js) and click
   **Send to Espruino**. Type `save()` on the left so it survives a restart.
4. **Disconnect the Web IDE.** The watch can only talk to one device at a time,
   and the laptop needs it.

### 3. Connect the robot

Plug the Ohbot and its head camera into the laptop over USB. Plug them in
directly rather than through a hub if you can.

On macOS, allow **Camera**, **Microphone** and **Bluetooth** access for your
terminal app the first time you're asked.

---

## Running it

### The easy way: the workstation UI

On macOS, double-click **`Start Thesis UI.command`**. Or run:

```bash
python -m robot.apps.presentation_ui
```

This opens a local page in your browser (it only runs on your laptop) with four
tabs:

- **Setup**: check the devices, register your face and voice, and add reminders.
- **Presentation**: run the system live and see what it's doing at each step.
  *Quick presentation* mode shortens the waiting time for demos.
- **Algorithms**: the models used and their benchmark results.
- **Evaluation Data**: record labelled samples for testing (the only mode that
  saves recordings).

### From the terminal

```bash
python -m robot.apps.enroll_voice      # once: register your voice
python -m robot.apps.enroll_face       # once: register your face (only needed for camera mode)
python -m robot.apps.add_reminder      # add a reminder by voice
python -m robot.apps.reminder_app      # start the robot
```

`reminder_app` asks two questions at startup:

1. Should it **remember** your decisions for each person, or **ask every time**?
2. **Microphone only**, or **microphone then camera**?

### Handy options

| Setting | What it does |
| --- | --- |
| `NO_OHBOT=1` | Run without the robot; the laptop speaks instead. |
| `CAMERA_DEVICE="HDR webcam"` | Choose a camera by name if the wrong one is picked. |
| `OHBOT_PORT=...` | Tell the app which USB port the robot is on if it isn't found. |

Put the setting before the command, for example:

```bash
NO_OHBOT=1 python -m robot.apps.reminder_app
```

To check which camera will be used: `python -m robot.apps.list_cameras --preview 0`.

---

## Your data

Your face/voice profiles, reminders and remembered answers are saved only in
`robot/state/` on the laptop and are never uploaded or committed to git. To reset:

- delete `robot/state/consent_cache*.json` to forget all Yes/No answers;
- re-run `enroll_face` or `enroll_voice` to replace your profile.

---

## Troubleshooting

| Problem | Try this |
| --- | --- |
| **Watch never asks anything** | The prompt only appears for a *sensitive* reminder, when it's *due*, with *someone else present*. Check that the watch shows "Robot linked". |
| **Watch not found** | Close or disconnect the Espruino Web IDE, then restart the app. |
| **Robot doesn't start or move** | Replug the USB cable, or set `OHBOT_PORT`. Use `NO_OHBOT=1` to test without it. |
| **Robot is silent** | Make sure `espeak` is installed. |
| **Camera won't open / black image** | Close Zoom, Teams, etc. Replug the camera directly into the laptop. Check the lens isn't covered. |
| **Install fails** | Make sure you're using Python 3.13 (`python --version`). |

---

## Running the tests

The tests don't need any hardware:

```bash
python -m pytest tests/
```

---

## More documentation

Technical details are in [`docs/`](docs/README.md):

- [Codebase guide](docs/codebase_guide.md): how the code is organised and what
  each file stores
- [Design overview](docs/design_hld.md): the privacy and consent design
- [Technical overview](docs/technical_hld.md): algorithms, settings, and the
  watch protocol
- [Algorithm comparison](docs/algorithm_comparison.md): benchmark results
- [User study](user-study/README.md): study materials
