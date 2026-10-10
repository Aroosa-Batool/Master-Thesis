"""Expand the review draft into complete story text and auditable assignment CSVs.

Uses only Python's standard library. Does not collect participant data.
"""
from collections import Counter
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODES = ("M", "C", "F")
BASE = ("M", "C", "F", "M", "C", "F")
NAMES = {"M": "Microphone only", "C": "Camera only",
         "F": "Microphone first, camera fallback"}
ACCESS = {"M": "Microphone only", "C": "Camera only",
          "F": "Microphone and camera"}
SEQUENCES = {
    "M": "The microphone listens during the five-minute window before the reminder. "
         "Sam's voice is detected. The camera is not used.",
    "C": "The camera is open during this session. At the reminder check, the robot "
         "turns its head and the camera detects Sam's face. The microphone is not "
         "used for presence sensing.",
    "F": "The microphone listens during the five-minute window before the reminder. "
         "Sam's voice is detected, so the camera is not activated.",
}
PROMPT = ("I have noticed that someone is present with you. Do you want me to "
          "send private reminders in front of them?")
TOPICS = (
    ("Health appointment", "your mental-health appointment at 3 PM today"),
    ("Financial payment", "your overdue loan payment due today"),
    ("Personal appointment", "your confidential job interview at 4 PM today"),
)


def write_csv(name, rows):
    with (ROOT / name).open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def response(story, schedule):
    return "NO" if (story % 2 == 1) == (schedule == "A") else "YES"


def expand_story(story, mode, answer):
    home = story % 2 == 1
    topic, reminder = TOPICS[(story - 1) // 2]
    place = "Alex's living room" if home else "Alex's desk in a shared office"
    relationship = "a close friend visiting for tea" if home else "a colleague Alex knows through work"
    line = "Would you like some tea?" if home else "Shall we look at the task after this?"
    reply = "Yes, thanks." if home else "Yes, in a moment."
    outcome = (
        f'Alex taps **No**. Ohbot says only **“Hello there.”** The connected watch '
        f'displays **“Reminder: {reminder}”** as a private note. Sam does not hear '
        'the reminder content.' if answer == "NO" else
        f'Alex taps **Yes**. Ohbot says **“Here is your reminder for {reminder}.”** '
        'Sam hears the reminder content. A private note is not used for this delivery.'
    )
    image = "home" if home else "office"
    return f'''### S{story}-{mode}-{answer}: {topic}

![Alex and Sam with Ohbot and Bangle.js; setting, watch interaction, delivery.](assets/{image}-triptych.png)

*Hypothetical AI-generated scene. Read the captions for sensing state, watch messages and delivery outcome.*

**Location:** {place}. **People:** Alex and Sam, {relationship}.

**Context:** Alex previously scheduled a sensitive reminder: **“{reminder}”**. Sam remains nearby throughout sensing and delivery. Imagine you are Alex.

**Previously allowed sensing:** {ACCESS[mode]}. **Disclosure policy:** ask each time a visitor is detected; do not remember disclosure answers. This describes a prior setup choice, not an implemented watch-based sensor setup interface.

**Panel 1 — dialogue and sensing:** During the listening interval, Sam says, “{line}” Alex replies, “{reply}” Sam's face is also visible during the camera check. {SEQUENCES[mode]}

**Panel 2 — watch prompt:** Robot asks: **“{PROMPT}”** Buttons: **Yes / No**.

**Panel 3 — response and outcome:** {outcome}

[Administer the identical Q1–Q16 block from survey-draft.md.]

'''


def main():
    bank = ["# Complete stimulus bank\n\nResearcher reference: show only the six assigned "
            "stories, never the whole bank, to a participant. Apply the introduction "
            "and repeated question block in survey-draft.md.\n\n"]
    for story in range(1, 7):
        for mode in MODES:
            for answer in ("NO", "YES"):
                bank.append(expand_story(story, mode, answer))
    (ROOT / "stimulus-bank.md").write_text("".join(bank), encoding="utf-8")

    assignments, orders = [], []
    seed = (1, 2, 6, 3, 5, 4)
    predecessor = Counter()
    positions = Counter()
    for order in range(6):
        sequence = tuple((s - 1 + order) % 6 + 1 for s in seed)
        orders.append({"order_id": f"W{order + 1}",
                       **{f"position_{p}": f"S{s}" for p, s in enumerate(sequence, 1)}})
        positions.update((p, s) for p, s in enumerate(sequence, 1))
        predecessor.update(zip(sequence, sequence[1:]))
        for allocation in range(3):
            for schedule in ("A", "B"):
                cell = f"L{allocation + 1}-{schedule}-W{order + 1}"
                group = []
                for position, story in enumerate(sequence, 1):
                    mode = MODES[(MODES.index(BASE[story - 1]) + allocation) % 3]
                    answer = response(story, schedule)
                    row = {"cell_id": cell, "allocation": f"L{allocation + 1}",
                           "response_schedule": schedule, "order_id": f"W{order + 1}",
                           "position": position, "story_id": f"S{story}",
                           "condition": mode, "approach": NAMES[mode],
                           "active_sensors": "camera" if mode == "C" else "microphone",
                           "topic": TOPICS[(story - 1) // 2][0],
                           "relationship": "friend" if story % 2 else "colleague",
                           "watch_response": answer,
                           "delivery": "private" if answer == "NO" else "aloud",
                           "stimulus_id": f"S{story}-{mode}-{answer}",
                           "image": f"assets/{'home' if story % 2 else 'office'}-triptych.png"}
                    group.append(row)
                    assignments.append(row)
                for mode in MODES:
                    subset = [r for r in group if r["condition"] == mode]
                    assert len(subset) == 2
                    assert {r["watch_response"] for r in subset} == {"YES", "NO"}
                    assert {r["relationship"] for r in subset} == {"friend", "colleague"}
    assert len(assignments) == 216
    assert len(positions) == 36 and set(positions.values()) == {1}
    assert len(predecessor) == 30 and set(predecessor.values()) == {1}
    stimuli = Counter(r["stimulus_id"] for r in assignments)
    assert len(stimuli) == 36 and set(stimuli.values()) == {6}
    assert all((ROOT / r["image"]).is_file() for r in assignments)
    write_csv("story-assignments.csv", assignments)
    write_csv("order-schedule.csv", orders)
    print("Verified 36 allocation cells, 216 assignments, 36 complete stimuli; "
          "each modality has one Yes/No and one friend/colleague per participant; "
          "all story positions and immediate predecessors balance.")


if __name__ == "__main__":
    main()
