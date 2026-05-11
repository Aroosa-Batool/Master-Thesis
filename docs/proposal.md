# Master's Thesis Proposal

**Whisper, Hint, or Stay Silent: A Multi-Channel Privacy-Aware Disclosure Policy for Wearable-Coupled Social Robots**

*Compressed 12-week plan. Document version 2026-05-09.*

---

## 1. Background and Motivation

Interactive wellbeing systems can *detect* that a user needs support — elevated heart rate, sustained inactivity, sleep disruption — but the question of *how that support should be delivered when other people are in the room* remains under-addressed. A robot that responds to physiological stress with the line "I noticed your heart rate is elevated" is appropriate when the user is alone and inappropriate when an acquaintance is present. The problem is not *whether* to respond, but **how much to reveal and through which channel**, conditioned on who is observing.

This thesis treats disclosure as a graded, context-sensitive design variable, drawing on Nissenbaum's contextual integrity framework (Nissenbaum, 2010) and recent work on graded disclosure in human-robot mediators (Dietrich, Krüger & Weisswange, 2023). It argues that for embodied wellbeing agents to function in shared physical spaces, they must reason not only about user state but about the *social audience* of every utterance.

## 2. Research Gap

A structured review of recent privacy-aware HRI, socially assistive robotics, and wearable-coupled wellbeing systems (see [literature_review.md](literature_review.md), 22 verified sources) identifies a specific unfilled combination. **No verified prior system** jointly satisfies all three of:

1. Drives a co-located social robot from **live wearable sensing**,
2. Selects among **≥3 discrete disclosure behaviours** including a **wearable-routed private channel**, and
3. Parameterises the selection on **both bystander presence and tie strength**.

The two closest neighbours each implement a strict subset:

- **Dietrich, Krüger & Weisswange (2023)** treat disclosure as graded but use a human-mediating robot, vignette-driven, no live sensing.
- **Sullivan et al. (2025)** use an LLM controller for privacy-aware support but no wearable channel and no structured tie-strength input.

The thesis is therefore framed as the first end-to-end demonstration of the full pipeline.

## 3. Contribution

1. A **four-behaviour disclosure policy** (full / partial / none / watch-routed) implemented end-to-end on Bangle.js + Ohbot.
2. A **two-axis context model** (proxy physiological state × social context) parameterising the policy.
3. An **online vignette study** (n ≈ 40) testing whether the adaptive policy is rated more privacy-appropriate than a fixed full-disclosure baseline across controlled bystander conditions.
4. An **open-source reference implementation** released with the thesis.

## 4. Research Questions

**Main RQ.** Across varying social contexts (alone / weak-tie present / strong-tie present), do participants rate an adaptive multi-channel disclosure policy as more privacy-appropriate than a fixed full-disclosure baseline, while preserving perceived helpfulness?

**Sub-questions.**

- **SQ1.** Which features of the social context — bystander presence, bystander tie strength — most strongly drive ratings of privacy-appropriateness?
- **SQ2.** Does the wearable-routed channel preserve *helpfulness* relative to full disclosure while reducing *privacy cost* in non-private contexts?

**Working hypotheses (testable in the vignette study).**

- **H1.** The adaptive policy is rated *as helpful* as full disclosure in alone conditions and *more privacy-appropriate* than full disclosure in weak-tie conditions.
- **H2.** The watch-routed channel is rated *more privacy-appropriate* than vocal full disclosure in any non-private context, with no significant loss of perceived helpfulness.

## 5. System Architecture

```
┌─────────────┐      BLE       ┌─────────────────────┐      USB/Serial   ┌──────────┐
│  Bangle.js  │ ─────────────▶ │  Intermediate layer │ ─────────────────▶│  Ohbot   │
│  smartwatch │ ◀───────────── │  (proxy + policy)   │                    │  robot   │
└─────────────┘                └─────────────────────┘                    └──────────┘
```

**The four behaviours:**

| Behaviour | Channel | Triggered when |
| --- | --- | --- |
| Full disclosure | Ohbot voice, explicit | Alone, or strong-tie present, or low-sensitivity content |
| Partial disclosure | Ohbot voice, hedged ("let's check in privately later") | Mixed company, ambiguous tie |
| No disclosure | Ohbot stays neutral | Weak tie or stranger present, sensitive content |
| Watch notification | Bangle.js vibration + on-wrist text | Sensitive content, any non-private context |

**Implementation status (2026-05-09):**

| Component | Status |
| --- | --- |
| Bangle.js HR sensing + BLE broadcast | ✅ done |
| Bystander-presence sensing (webcam, OpenCV, 25 s windowed verdict) | ✅ done |
| Ohbot full-disclosure + no-disclosure behaviours | ✅ done |
| End-to-end demo: HR + presence → behaviour | ✅ done |
| Partial-disclosure behaviour (~2 days) | ⏳ |
| Watch-routed notification: laptop → Bangle.js write characteristic, watch render + buzz (~4 days) | ⏳ |
| Tie-strength manual-input UI: simple Tk slider or web page (~1 day) | ⏳ |

## 6. Evaluation Plan: Online Vignette Study

Methodologically modelled on Apthorpe et al. (2018), which validated contextual-integrity-style privacy ratings using exactly this format. The vignette substitution is what makes a 12-week timeline feasible.

**Design.** Within-subjects, 3 social contexts × 4 robot behaviours = 12 video stimuli per participant. Each stimulus is a 15–25 second clip showing the Ohbot's response in a staged scenario. Participants rate each clip on five 7-point Likert scales: privacy-appropriateness, helpfulness, intrusiveness, trust, comfort. Order randomised. End-of-session: short demographics + one open-ended question ("when, if ever, would you want a robot to behave this way?").

**Stimuli.** Recorded in-lab using the existing system. The robot's responses are scripted-deterministic per (context × behaviour) cell; the bystander roles (alone / weak-tie / strong-tie) are signalled to the participant by a one-line context blurb above each video, not by visible confederates in the frame. This keeps stimulus production tractable.

**Participants.** N ≈ 40 university students recruited via departmental mailing list and social media, ages 18–35, completing the survey on their own laptop. Compensation: a small voucher or course credit if available.

**Baseline comparison.** The "fixed full-disclosure" policy (Ohbot speaks the full message in every context) is implicit in the design — participants rate the same content delivered four ways across three contexts, so the analysis directly compares the adaptive policy to the always-full baseline.

**Analysis.** Mixed-effects linear models with participant as random intercept; behaviour and context as fixed effects. Open-ended responses coded with a single rater plus a 20% second-rater reliability check.

**Ethics.** Anonymous online survey, no physiological data from participants, no embedded video of identifiable people. This is typically eligible for an expedited / minimal-risk review at most universities, often turned around in 2–3 weeks. Submit in week 1 to remove ethics from the critical path.

## 7. Compressed 12-Week Timeline

| Week | Dates (2026) | Deliverable |
| --- | --- | --- |
| 1 | May 11 – May 17 | Proposal sign-off with supervisor. **Submit ethics application.** Begin engineering remaining behaviours. |
| 2 | May 18 – May 24 | Implement partial-disclosure behaviour. Write Bangle.js BLE write-characteristic for watch notifications. |
| 3 | May 25 – May 31 | Implement watch-side notification rendering (display + buzz). Tie-strength input UI. End-to-end smoke test of all four behaviours. |
| 4 | Jun 1 – Jun 7 | Internal pilot (n = 2 lab-mates). Refine behaviour scripts based on pilot feedback. Begin video stimulus storyboard. |
| 5 | Jun 8 – Jun 14 | Record video stimuli (12 clips). Build the survey instrument in Qualtrics or Google Forms. Internal review of survey wording. |
| 6 | Jun 15 – Jun 21 | Ethics approval expected. Pilot the survey with n = 5 to debug ordering / wording. Finalise instrument. |
| 7 | Jun 22 – Jun 28 | **Open recruitment.** Push survey through mailing list + social media. Aim for 20+ responses by end of week. |
| 8 | Jun 29 – Jul 5 | Continue recruitment to ≥ 40. Begin draft of methodology + system chapters. |
| 9 | Jul 6 – Jul 12 | Close survey at n ≈ 40. Run quantitative analysis. Code open-ended responses. |
| 10 | Jul 13 – Jul 19 | Write results chapter. Iterate plots and tables. |
| 11 | Jul 20 – Jul 26 | Discussion + conclusion chapters. Polish introduction and lit review. |
| 12 | Jul 27 – Aug 2 | Final pass, supervisor read-through, formatting, demo recording, submission. |

Submission target: **early August 2026**.

## 8. Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Ethics approval slips past week 6 | Submit a *minimal-risk online survey* application in week 1, not a full board review. Prepare a backup of using only consenting departmental colleagues for an n = 8–12 pilot if ethics is delayed. |
| BLE write characteristic for watch notifications turns out fiddly | The Bangle.js NUS (Nordic UART Service) is well-documented; budget 1 extra day in week 3 if needed. Worst case: trigger the watch via a serial-over-BLE message format. |
| Recruitment slow, n < 30 by week 8 | Open the survey to a second department, post in r/SampleSize, offer a £5 voucher draw. Even n = 25 is publishable for a within-subjects vignette study. |
| Video stimuli vary in quality between behaviour conditions and bias ratings | Record all 12 in a single session with identical lighting, framing, and the same scripted user-side context. Use a black background and identical camera angle. |
| Participants rate "privacy" idiosyncratically because the term is fuzzy | Mirror Apthorpe et al.'s exact wording for the privacy-appropriateness item. Pilot the survey in week 6 specifically to catch this. |
| Partial-disclosure behaviour is hard to script in a way that's distinguishable from full disclosure | Draft three candidate scripts in week 2, pilot all three in week 4, choose the one that pilot participants reliably distinguish from full disclosure. |

## 9. Key References

Full list with 22 verified entries: [literature_review.md](literature_review.md). Core reference set for this proposal:

- Nissenbaum, H. (2010). *Privacy in Context: Technology, Policy, and the Integrity of Social Life.* Stanford University Press.
- Dietrich, M., Krüger, J., & Weisswange, T. H. (2023). Graded disclosure in human-robot mediation.
- Sullivan et al. (2025). LLM-driven privacy-aware support agents.
- Apthorpe, N., Shvartzshnaider, Y., Mathur, A., Reisman, D., & Feamster, N. (2018). Discovering smart home Internet of Things privacy norms using contextual integrity. *PACM IMWUT.* (Methodological template.)
- Chita-Tegmark, M., & Scheutz, M. (2021). Social-context-aware health support as a design problem.
- Riek, L. D. (2017). Healthcare robotics. *CACM.*
- Lutz, C., & Tamò-Larrieux, A. (2021). The robot privacy paradox.
- Granovetter, M. S. (1973). The strength of weak ties. *American Journal of Sociology.*
- Schmidt, P. et al. (2018). WESAD: A multimodal dataset for wearable stress and affect detection. *ICMI.*
- Palen, L., & Dourish, P. (2003). Unpacking "privacy" for a networked world. *CHI.*

---

*This proposal supersedes earlier versions. The full literature review and the working implementation are tracked in this repository.*
