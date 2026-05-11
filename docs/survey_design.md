# Survey Design: Privacy-Appropriate Disclosure

*Vignette study to collect human ground-truth ratings for the four robot disclosure behaviours across three social contexts. Modelled on Apthorpe et al. (2018).*

Document version: 2026-05-09.
Estimated participant runtime: 15–20 minutes.

---

## 1. Overview

- **Goal.** Establish, for each (social context × robot behaviour) cell, how participants rate the robot's response on five privacy- and wellbeing-relevant dimensions. The aggregated ratings serve as the ground truth against which both the rule-based controller and the local LLM controller are evaluated.
- **Method.** Online video-stimulus survey. Each participant rates 12 short clips.
- **Stimuli.** 4 robot behaviours × 3 social contexts = **12 clips**, each ~25 seconds.
- **Participants.** N ≈ 40 university students, recruited via mailing list and social media.
- **Platform.** Qualtrics (preferred — randomisation built in) or Google Forms (free fallback, manual randomisation).

## 2. Welcome / Consent screen (shown once, at the start)

> **Privacy and Robot Communication: A 15-minute study**
>
> Thank you for taking part. In this study you will watch 12 short videos of a small social robot and a smartwatch, and rate how appropriate the robot's behaviour feels in each situation.
>
> The study is **anonymous** — we do not collect your name, email, or any identifying information. Your answers will be analysed in aggregate and used only for academic research at [University Name].
>
> You can stop at any time without penalty. By clicking "Continue" you confirm you are over 18 and consent to participate.
>
> *(University ethics approval reference: [TO FILL IN])*
>
> [ Continue → ]

## 3. Text cards (one per social context)

Each card is a 5-second full-screen white-text-on-black slide shown immediately before the robot footage.

### Context A — Alone

> Imagine you are alone in your living room.
>
> Your smartwatch has detected that your heart rate is elevated.
>
> This is what your home robot does next.

### Context B — Weak tie present

> Imagine a person you do not know well — a delivery driver waiting briefly in your hallway — is in the room with you.
>
> Your smartwatch has detected that your heart rate is elevated.
>
> This is what your home robot does next.

### Context C — Strong tie present

> Imagine a close friend or family member is in the room with you.
>
> Your smartwatch has detected that your heart rate is elevated.
>
> This is what your home robot does next.

> **Note on tie-strength wording.** "Delivery driver" is a low-cost cue for a non-intimate, low-trust co-presence ("weak tie"). "Close friend or family member" cues high intimacy ("strong tie"). These two anchors are the most-used pair in the disclosure literature (Granovetter 1973; Marsden & Campbell 1984) and avoid the ambiguity of intermediate categories like "co-worker."

## 4. Robot behaviour scripts (one per behaviour)

The same four behaviours are filmed once and reused under each of the three context cards (so we record 4 takes, not 12).

### Behaviour 1 — Full disclosure

- **Audio.** Ohbot voice, clear, warm.
- **Movement.** Head turns toward the camera (~user POV), small nod, mouth lip-syncs while speaking.
- **Script.**
  > *"I noticed your heart rate is a bit elevated. Would you like to take a few deep breaths together?"*

### Behaviour 2 — Partial disclosure

- **Audio.** Ohbot voice, lower volume, no mention of heart rate or any sensor data.
- **Movement.** Single small head tilt toward the camera. No nod.
- **Script.**
  > *"Hey — let's check in privately later."*

### Behaviour 3 — No disclosure

- **Audio.** None.
- **Movement.** One slow blink and a small ambient head sway, so the participant can see the robot is on but choosing not to act.
- **Script.** Silent.

### Behaviour 4 — Watch notification

- **Audio.** Faint vibration sound.
- **Movement.** Ohbot stays still and silent for the full clip.
- **Watch overlay (cut to close-up of the wrist for ~5 seconds).** The watch buzzes, and the screen reads:
  > *"Heart rate elevated. Try a breathing exercise?"*
- The screen text fades, the clip ends.

## 5. The 12 stimuli (text card + behaviour pairing)

| Clip ID | Context | Behaviour | Notes |
| --- | --- | --- | --- |
| A1 | Alone | Full | Same Ohbot footage as B1, C1 |
| A2 | Alone | Partial | Same Ohbot footage as B2, C2 |
| A3 | Alone | None | Same Ohbot footage as B3, C3 |
| A4 | Alone | Watch | Same Ohbot footage as B4, C4 |
| B1 | Weak tie | Full | |
| B2 | Weak tie | Partial | |
| B3 | Weak tie | None | |
| B4 | Weak tie | Watch | |
| C1 | Strong tie | Full | |
| C2 | Strong tie | Partial | |
| C3 | Strong tie | None | |
| C4 | Strong tie | Watch | |

**Order of presentation.** Randomised per participant across all 12 clips. No grouping by context or behaviour — full random order. Survey platform handles this.

## 6. Per-clip rating items (5 questions, asked after each clip)

All items use a 7-point Likert scale: **1 = Strongly disagree**, 4 = Neutral, **7 = Strongly agree**. Wording is fixed; do not re-word during data collection or it breaks comparability.

| # | Item | Construct | Direction |
| --- | --- | --- | --- |
| 1 | "The robot's response respected my privacy in this situation." | Privacy-appropriateness | Higher is better |
| 2 | "The robot's response would have been helpful in this situation." | Helpfulness | Higher is better |
| 3 | "The robot's response felt intrusive." | Intrusiveness | **Reverse-scored** |
| 4 | "I would trust this robot to handle similar situations in the future." | Trust | Higher is better |
| 5 | "I would feel comfortable with the robot responding this way around me." | Comfort | Higher is better |

> **Analysis note.** Compute composite "privacy-appropriateness" = mean(item 1, reverse-scored item 3). Helpfulness, trust, comfort can be reported separately. Cronbach's α on the privacy composite should be reported.

## 7. End-of-survey items (asked once, after all 12 clips)

### Demographics

> 1. What is your age range? [18–24 / 25–34 / 35–44 / 45+ / Prefer not to say]
> 2. What is your gender? [Woman / Man / Non-binary / Prefer to self-describe / Prefer not to say]
> 3. How often do you use a smart speaker (Alexa, Google Home, etc.)? [Daily / Weekly / Monthly / Rarely / Never]
> 4. Have you used a wellbeing or mental-health app in the past year? [Yes / No]
> 5. Have you used a smartwatch with health-tracking features in the past year? [Yes / No]

### Open-ended

> 6. *"Is there a situation in which you would want the robot to behave differently from any of the videos you saw? Briefly describe."*
>
> [Free-text box, ~200 character limit]

### Closing

> Thank you for participating. Your responses have been recorded.
>
> *(Optional: prize-draw entry email field, kept in a separate table that cannot be linked to the responses.)*

## 8. Production notes (how to actually film the stimuli)

### Equipment

- The Ohbot, plugged in, on a clean desk.
- The Bangle.js, charged, on the experimenter's wrist.
- A laptop running [demo_with_watch.py](../interface/presence/demo_with_watch.py) in a **dev-mode override** that lets you trigger each behaviour on demand, regardless of camera/HR input. (One small flag added to the script.)
- Camera: laptop webcam *or* a phone on a small tripod for slightly better framing. Same camera for all clips.
- Plain wall behind the Ohbot. Avoid windows (changing light).

### Procedure (single half-day session)

1. Set up the desk, robot, and camera. Frame the shot so the Ohbot occupies the centre and there is empty space on both sides for clarity.
2. Record **Behaviour 1 (Full)** — single clean take, ~20 seconds. Re-take if there are line stumbles.
3. Repeat for **Partial**, **None**, **Watch**. The Watch clip needs a separate close-up of the wrist; record this in a second pass with the phone.
4. In a video editor (iMovie, DaVinci Resolve, Shotcut — all free):
   - Make 3 copies of each behaviour clip.
   - Add the appropriate context-card slide (A / B / C) at the front of each copy.
   - Export at 720p, mp4, ~1–2 MB each.
5. Upload to the survey platform. Embed each clip into a stimulus page followed by the 5 rating items.

### File naming

Suggested naming so the analysis is unambiguous:

```
clip_A1_alone_full.mp4
clip_A2_alone_partial.mp4
clip_A3_alone_none.mp4
clip_A4_alone_watch.mp4
clip_B1_weaktie_full.mp4
... etc.
```

## 9. Data outputs (what to save)

Per participant, save a single CSV row with:

- Anonymous participant ID (UUID generated by the survey platform)
- For each of 12 clips: 5 Likert ratings (60 numeric columns)
- 5 demographic items (5 columns)
- 1 open-ended response (1 text column)
- Survey start time, end time, completion time (3 columns)

Total: ~70 columns × N rows. CSV is fine; no special schema needed.

## 10. Aggregation for the controller comparison

After collection, produce a small lookup table — this is the ground truth used by the comparative analysis (`analyse_controllers.py`):

| Context | Behaviour | Privacy-appropriate (mean) | Helpful (mean) | Composite (z-score) |
| --- | --- | --- | --- | --- |
| Alone | Full | (e.g.) 5.4 | 6.1 | 0.8 |
| Alone | Partial | 4.1 | 3.8 | -0.3 |
| Alone | None | 3.2 | 1.9 | -1.1 |
| Alone | Watch | 4.8 | 5.0 | 0.2 |
| Weak tie | Full | 2.1 | 5.5 | -0.6 |
| ... | ... | ... | ... | ... |

For each context row, the **highest-composite behaviour** is the human-preferred answer. Both controllers are scored on whether they pick that behaviour for that context.

## 11. Pilot before launch (week 6)

Pilot the full survey with **n = 5 lab-mates** before opening recruitment. The goals of the pilot are:

- Catch confusing item wording.
- Verify that the four behaviours are visually distinguishable in the videos (especially Partial vs. Full and None vs. Watch).
- Time the survey end-to-end. Adjust if it exceeds 20 minutes.
- Surface technical issues with video embed / mobile playback.

Pilot data is **not** included in the main analysis. After fixes, formally launch with the public N ≈ 40.

---

*Companion documents: [proposal.md](proposal.md), [literature_review.md](literature_review.md).*
