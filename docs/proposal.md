# Master's Thesis Proposal

**Working title:** *Ask, Cache, or Predict? Three Disclosure Policies for Wearable-Coupled Social Robots*

### Title options under consideration

One of the following will be selected before the thesis cover page is finalised. All five describe the same work; they differ in framing and tone.

1. ***Ask, Cache, or Predict? Three Disclosure Policies for Wearable-Coupled Social Robots*** — verb-triplet hook, names the three conditions, clean structure. Safe-but-strong default.
2. ***From Cache to Cognition: On-Device LLM Consent Memory for Embodied Wellbeing Agents*** — alliterative; "On-Device" signals the privacy story in the title; current AI vocabulary.
3. ***Contextual Integrity at the Edge: Symbolic and Neural Consent Memory in Wearable-Mediated Social Robots*** — theory-anchored (Nissenbaum); maximum academic gravitas; "Symbolic and Neural" is the ML-paper version of "rule vs. LLM".
4. ***Just-in-Time vs. Just-in-Case Consent: On-Device LLM Memory in Wearable-Coupled Social Robots*** — plays on a known phrase from the consent-design literature; signals deep reading.
5. ***Should the Robot Predict? On-Device Language Models as Adaptive Consent Memory in Embodied AI*** — question hook; reframes the LLM as *memory*, not a controller — a subtle but smart positioning.

*12-week plan. Document version 2026-05-14 (v8). Supersedes earlier versions.*

---

## Quick read — the thesis in 90 seconds

**Premise.** A social robot helping a user in a shared room must decide what to reveal about the user's wellbeing state when other people are present. The Ohbot speaks aloud (everyone hears); the Bangle.js smartwatch can buzz the user privately. The robot's decision turns on three things: *what* is being revealed, *who* is in the room, and *what the user previously consented to.*

**The thesis question.** When the same companion keeps showing up, should the robot ask every time (Re-Consent), remember literal past answers (Cache-Memory), or predict the user's likely answer using a local language model (Learned-Memory)? The thesis compares all three.

**Method.** Within-subjects laboratory study, n = 16. Each participant goes through 3 blocks (one per policy, order counterbalanced via Latin square), 6 robot interactions per block. The same trials are run under each policy so the comparison is direct. A seeded consent history at block start removes the cold-start confound.

**Submission target.** Early August 2026 (12 weeks from May 11).

### End-to-end pipeline

```
┌────────────────────────────────────────────────────────────────┐
│ 1. Bangle.js senses heart rate, broadcasts over BLE            │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ 2. Laptop perception:                                          │
│      camera face count  +  mic voice activity                  │
│      → companion present? Yes/no, windowed over 25 s           │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ 3. Bystander re-identification via face embedding (FaceNet)    │
│      → "this is the same companion as last Tuesday"            │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ 4. Policy router — chooses one of:                             │
│      • Re-Consent     (always ask on watch)                    │
│      • Cache-Memory   (exact-match lookup; ask on miss)        │
│      • Learned-Memory (local LLM predicts from history;        │
│                        ask only when confidence < τ)           │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ 5. (Optional) Watch consent prompt → user taps Yes/No          │
│      Only fires when the policy says so. Response over BLE.    │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ 6. Ohbot speaks the wellbeing message or stays silent          │
│      User rates the experience on 3 Likert items               │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ 7. Decision logged → consent history / memory store grows      │
└────────────────────────────────────────────────────────────────┘
```

### Status at a glance

Legend: ✅ done · ⏳ in progress · □ not started · ⏸ blocked

**System components**

- ✅ Bangle.js HR sensing + BLE broadcast
- ✅ Bangle.js ↔ laptop BLE pipe
- ✅ Camera-based bystander presence (windowed verdict)
- ✅ Ohbot speech behaviours
- ⏳ Microphone voice-activity detection
- □ Multi-modal sensor fusion (camera + mic)
- □ Face-embedding bystander re-identification
- □ Watch consent UI (render + Yes/No buttons + BLE response)
- □ Cache-memory store
- □ Local LLM consent predictor (Ollama + Llama 3.2)
- □ Three-way policy router

**Documents**

- ✅ Proposal v8 (this file)
- ✅ Literature review — 22 verified sources, in `docs/literature_review.md`
- ⏳ Survey design — `docs/survey_design.md` currently vignette-flavoured, needs rewriting for the in-person procedure
- ⏸ Ethics application — to be drafted and submitted this week

### Immediate next steps (week 1, May 11–17)

| Task | Owner | Status |
|---|---|---|
| Send proposal v8 + supervisor email | Aroosa | Today |
| Pick one of the 5 title options | Aroosa | This week |
| Submit ethics application | Aroosa | By Friday |
| Microphone VAD prototype (`pip install webrtcvad` + ~50-line script) | Aroosa | This week |
| Rewrite `docs/survey_design.md` for the in-person procedure | Aroosa | Next week |
| Supervisor sign-off on three-policy design + on-device LLM use | Supervisor | Awaiting reply |

### What blocks the timeline

1. **Supervisor sign-off** on the three-policy design and the on-device LLM choice.
2. **Ethics approval** — must submit this week; typical turnaround ~3 weeks.

Everything else is unblocked: microphone VAD, multi-modal fusion, face-embedding re-identification, and the watch consent UI can all proceed in weeks 1–4 regardless of pending decisions on policy details.

---

## 1. Background and Motivation

A social robot supporting a user's wellbeing in a shared home — alongside a partner, a flatmate, a regular visitor — repeatedly faces the same question: *should it reveal what it has learned about the user in front of the other person who is also in the room?* Answering once is easy. Answering it across many interactions, in front of the same recurring companions, raises a harder design choice: **how should the robot handle repeated consent decisions over time?**

Three positions are obviously plausible:

1. **Ask every time.** Maximum informed consent, at the cost of effort and consent fatigue.
2. **Cache the answer.** After the first decision, reuse it. Convenient, but acts on potentially stale preferences.
3. **Predict the answer.** Learn from the user's past decisions and only ask when uncertain. Convenient *and* responsive — if the prediction is good.

This thesis is a head-to-head comparison of all three, instantiated in a co-located social robot supported by a wearable smartwatch, where the wrist is the private channel for consent and the robot's spoken behaviour is the public output controlled by the consent decision.

## 2. Research Gap

Prior work in privacy-aware HRI studies **what** a robot should disclose and **to whom** (Dietrich, Krüger & Weisswange, 2023; Lutz & Tamò-Larrieux, 2021). Prior work in permission design studies the consent-fatigue/informed-consent trade-off in browsers and smartphones. Prior work in on-device LLMs benchmarks their decision-making capacity but mostly in unconstrained scenarios (Sullivan et al., 2025).

**No verified prior work runs a head-to-head three-way comparison** of (a) no-memory re-consent, (b) deterministic cache-based memory, and (c) ML-driven learned memory inside a single co-located robot system that uses a wearable as the consent channel. The thesis fills exactly that gap.

## 3. Contribution

1. A **wearable-mediated consent flow** in which the robot asks the user (via the watch) for permission to disclose sensitive content in front of a detected companion, and the user responds privately on the wrist.
2. A **multi-modal bystander pipeline** fusing camera face detection and microphone voice-activity detection, with **face-embedding-based re-identification** (FaceNet-style) so the same companion can be matched across encounters.
3. **Three disclosure policies**, evaluated head-to-head:
   - **Re-Consent.** Robot asks on the watch every time, regardless of history.
   - **Cache-Memory.** After the first consent for a `(bystander, content_type)` pair, cache the decision. Reuse without asking on later encounters.
   - **Learned-Memory.** A local LLM (Llama 3.2 3B via Ollama, on-device) predicts the user's decision from the consent history. The watch is used only when the predictor's confidence is below threshold.
4. A **within-subjects user study** (n = 16, range 12–20) measuring privacy-appropriateness, helpfulness, comfort, perceived control, and intent-to-continue across all three policies, plus a quantitative evaluation of the LLM predictor's agreement with the user's actual decisions.
5. An **open-source reference implementation** released with the thesis.

## 4. Research Questions

**Main RQ.** When a social robot, coupled with a smartwatch and multi-modal bystander sensing, must decide whether to disclose sensitive content in front of a recurring companion, how do three disclosure policies — re-consent, cache-memory, and learned-memory — compare on user-rated privacy-appropriateness, helpfulness, and perceived control?

**Sub-questions.**

- **SQ1.** Does any memory-based policy (cache or learned) outperform re-consent on perceived helpfulness without significant loss of privacy-appropriateness? *(Does memory help?)*
- **SQ2.** Does the LLM-driven learned-memory policy outperform the deterministic cache on perceived privacy-appropriateness in contexts where the user's preferred answer changes across encounters? *(Does ML in the decision layer help?)*
- **SQ3.** How well does the local LLM consent predictor, conditioned on the user's consent history, agree with the user's actual decision? *(Quantitative ML evaluation.)*
- **SQ4.** Does multi-modal presence sensing (camera + microphone) detect "companion present" more reliably than camera alone?
- **SQ5.** Does re-consent show measurable consent fatigue within a single 6-interaction block?

**Working hypotheses.**

- **H1.** Both memory policies beat re-consent on helpfulness and convenience, while staying within ±0.5 Likert points on privacy-appropriateness.
- **H2.** Learned-memory beats cache-memory specifically on the high-sensitivity-content subset, because cache cannot distinguish content types it has not yet seen.
- **H3.** The local LLM predictor agrees with the user's actual consent ≥ 70% of the time after the first 3 calibration interactions.
- **H4.** Re-consent shows a measurable fall in consent-tap response time across the block, consistent with consent fatigue.

## 5. System Architecture

```
┌─────────────┐      BLE       ┌────────────────────────────────────────────────────┐    USB    ┌──────────┐
│  Bangle.js  │ ─────────────▶ │  Intermediate layer                                │ ─────────▶│  Ohbot   │
│  smartwatch │ ◀───────────── │                                                    │           │  robot   │
└─────────────┘                │  ┌─────────────┐  ┌──────────────────────────────┐ │           └──────────┘
   private +                   │  │ Perception  │  │ Decision                      │ │
   consent channel             │  │ camera+mic, │→ │ face embedding lookup         │ │
                               │  │ multi-modal │  │ → policy router:              │ │
                               │  │ fusion      │  │   re-consent | cache | LLM    │ │
                               │  └─────────────┘  │ → consent memory store        │ │
                               │                   └──────────────────────────────┘ │
                               └────────────────────────────────────────────────────┘
```

### The ML stack, explicitly

| Component | Model / Library | Where it runs | Why ML |
|---|---|---|---|
| Face detection + count | MediaPipe Face Detection (OpenCV Haar fallback) | Laptop, real-time | Robustness across lighting and angle. |
| **Face embedding for re-ID** | FaceNet (Schroff et al., 2015) via DeepFace or InsightFace | Laptop, on-demand | Cosine similarity in embedding space is the standard way to match "same person across encounters." |
| Microphone VAD | webrtcvad | Laptop, real-time | Lightweight; standard. |
| (Optional) Speaker embedding | ECAPA-TDNN via pyannote.audio | Laptop, on-demand | Off-camera bystander detection. Stretch goal — week 5. |
| **Consent predictor** | Llama 3.2 3B via Ollama, few-shot prompted with consent history | Laptop, ~500 ms per call | Generalises across bystanders and content types. On-device to preserve the privacy claim. |

### Implementation status (2026-05-12)

| Component | Status |
| --- | --- |
| Bangle.js HR sensing + BLE broadcast | ✅ done |
| Bangle.js → laptop BLE pipe | ✅ done |
| Camera face-count presence verdict, windowed | ✅ done |
| Ohbot speech behaviours | ✅ done |
| Microphone VAD | ⏳ ~3 days |
| Multi-modal fusion (camera + mic) | ⏳ ~2 days |
| Face embedding for bystander re-ID | ⏳ ~4 days |
| **Cache-memory store (face embedding → decision log)** | ⏳ ~2 days |
| **Local LLM consent predictor (Ollama + Llama 3.2 + prompt design)** | ⏳ ~4 days |
| **Three-way policy router (re-consent / cache / learned)** | ⏳ ~2 days |
| Watch consent UI (Bangle.js render + buttons + BLE response) | ⏳ ~5 days |
| Internal pilot (n = 2) | ⏳ week 5 |

Total new engineering: ~22 working days ≈ 4.5 weeks. Fits inside weeks 2–6.

### The consent flow under each policy

**Re-Consent.** Sensitive event → always send consent question to watch → user taps Yes/No → robot acts.

**Cache-Memory.** Sensitive event → check memory store keyed on `(bystander_embedding, content_type)`. If hit → reuse decision. If miss → send consent question to watch, store the answer, act.

**Learned-Memory.** Sensitive event → query the LLM predictor with `(bystander_embedding_id, content_type, consent_history)` as few-shot context. The predictor returns `(predicted_decision, confidence)`. If `confidence ≥ τ` → act on prediction without asking. Else → send consent question to watch, log the answer, act.

## 6. Evaluation Plan

A within-subjects laboratory study comparing the three policies. Within-subjects is necessary because the construct of interest — *how the user feels after repeated interactions* — only exists across multiple encounters.

**Participants.** n = 16 (range 12–20), university students, ages 18–30. A single trained researcher plays the recurring companion role across all sessions (avoids participant-pair recruitment friction).

**Design.** Three within-subjects blocks (Re-Consent / Cache-Memory / Learned-Memory), order counterbalanced via a 3 × 3 Latin square (3 orderings, ~5 participants per ordering). Each block contains 6 robot interactions with a scripted mix of high- and low-sensitivity content.

**Procedure (≈ 65 min per participant).**

1. Briefing + consent (10 min).
2. Block A → ratings → Block B → ratings → Block C → ratings (45 min total).
3. Exit interview (10 min): which policy felt best and why; how did each one feel relative to the others.

**Measures.**

- *Per interaction:* 3 × 7-point Likert (privacy-appropriate, helpful, intrusive).
- *Per block:* 5 × 7-point Likert (overall comfort, trust, perceived control, perceived effort, intent to keep using).
- *Predictor agreement (SQ3):* for each Learned-Memory interaction where the predictor acted without asking, log the prediction. At the end of the session, ask retrospectively *"would you have wanted to be asked here?"* → gives an agreement-rate metric.
- *Fatigue (SQ5):* consent-tap response time on the watch, plotted over the Re-Consent block.
- *Qualitative:* exit interview, audio-recorded, coded thematically with a 20% second-rater reliability check.

**Analysis.** Linear mixed-effects models with participant as random intercept; policy and content-sensitivity as fixed effects. Pairwise contrasts (Re-Consent vs. Cache; Cache vs. Learned; Re-Consent vs. Learned) with Bonferroni correction. Predictor agreement reported as accuracy + confusion matrix. Themes from interviews triangulated with quantitative ratings.

### Fair comparison via pre-seeded consent history

The three policies behave very differently when the consent log is empty: Cache always misses, the LLM has nothing to predict from, and only Re-Consent works normally. Running 6 fresh trials per block in that cold-start state would systematically underweight the memory-based policies, because most of their trials would just collapse to "ask on the watch." That confounds the comparison.

To remove this, **each policy block begins with a pre-seeded consent history**. Before the block starts, the participant reads:

> *"Imagine you have used this robot for two weeks. In that time you have decided:*
> *— share bpm with Anna [Yes], share sleep with Anna [No], share weight with Anna [No]*
> *— share bpm with Bob [Yes], share sleep with Bob [No]*
> *Today you will experience one of three settings."*

Behind the scenes, the cache is populated with the five entries, and the LLM's prompt includes them as few-shot examples. The **same** seeded history is given to all three policies — the only thing that differs between policies is the mechanism that consults it.

Within each block, the **same six trials are presented in the same order across all participants and all policies**, with the bystander–content combinations chosen so that:

- **2 trials exactly match the seeded history.** Cache hits cleanly; LLM predicts with high confidence; only Re-Consent still asks. Tests "memory at its easiest."
- **2 trials test pattern generalisation** (e.g. new bystander, content type the user has a pattern for). Cache misses (and falls through to asking); LLM may still predict. Tests "where does ML help over a hash table."
- **2 trials are genuinely novel** (new bystander, new content). Both memory policies should defer; LLM should report low confidence and route to the watch. Tests "graceful fallback when the predictor doesn't know."

This 2 + 2 + 2 structure lets us see, per policy, how often the user is bothered vs. how often the system acts autonomously, and — for Learned-Memory — whether the autonomous decisions actually agree with what the user would have chosen. It also makes the Cache-vs-Learned contrast genuinely measurable rather than a cold-start artefact.

**Ethics.** University ethics approval required. In-person but minimal-risk (no physiological recordings beyond the watch, no identifying audio retained, confederate briefed, debrief at end). Submit application in week 1 to keep it off the critical path.

## 7. Compressed 12-Week Timeline

| Week | Dates (2026) | Deliverable |
| --- | --- | --- |
| 1 | May 11 – May 17 | Proposal sign-off. **Ethics application submitted.** Begin VAD + face-embedding prototypes. |
| 2 | May 18 – May 24 | Multi-modal presence fusion working. Pick face-embedding library; verify re-ID on 5 lab-mates. |
| 3 | May 25 – May 31 | Cache-memory store. **Local LLM predictor:** install Ollama, design prompt, accuracy spot-check on 20 synthetic cases. |
| 4 | Jun 1 – Jun 7 | Watch consent UI: render question + Yes/No buttons on Bangle.js; response back via BLE. |
| 5 | Jun 8 – Jun 14 | Three-way policy router. Internal pilot (n = 2). |
| 6 | Jun 15 – Jun 21 | Refine stimuli + study script based on pilot. Build the tablet rating form. Ethics approval expected. |
| 7 | Jun 22 – Jun 28 | Recruit participants. Full procedure pilot (one session). |
| 8 | Jun 29 – Jul 5 | **Study sessions 1–8.** |
| 9 | Jul 6 – Jul 12 | **Study sessions 9–16.** Begin transcription. |
| 10 | Jul 13 – Jul 19 | Quantitative analysis. Predictor-vs-user agreement. Thematic coding. |
| 11 | Jul 20 – Jul 26 | Results + Discussion chapters. ML chapter (predictor design + evaluation). |
| 12 | Jul 27 – Aug 2 | Final pass, supervisor read-through, formatting, demo recording, submission. |

Submission target: **early August 2026**.

## 8. Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Face-embedding re-ID is unreliable in real lighting | Fallback: confederate wears a known BLE tag; identity becomes trivial. Adds 1 day. |
| Local LLM predictor too slow on the laptop | Use Llama 3.2 1B instead of 3B, or pre-compute predictions for the fixed interaction conditions. Latency budget is ~1 s. |
| LLM predictor accuracy is poor | Report honestly — "the predictor agreed X% of the time" is itself publishable, in line with Sullivan et al. (2025). Pre-register predictor accuracy as exploratory. |
| Microphone VAD triggers on TV/music | Tune webrtcvad aggressiveness in week 2; gate on the human-voice frequency band if needed. |
| Three blocks × 6 interactions feels too long for participants (>65 min) | Drop to 5 interactions per block (15 total) if pilot participants report fatigue. Loses some fatigue-test power but preserves the policy comparison. |
| Watch button taps unreliable | 2-button taxonomy (Yes / No mapped to the two side buttons); large-font screen. Pilot in week 4. |
| Ethics approval slips past week 6 | Apply in *in-person, minimal-risk* category in week 1. Vignette-only fallback (n = 30 online survey of pre-recorded sessions) ready as Plan B. |
| Latin-square confounding (order effects) | 3 orderings counterbalanced across 16 participants (5–6 per ordering). Include order as a covariate in the mixed-effects model. |

## 9. Key References

Full literature review in [literature_review.md](literature_review.md). Core anchors:

- **Nissenbaum, H. (2010).** *Privacy in Context.* Stanford University Press. — Theoretical anchor.
- **Dietrich, M., Krüger, J., & Weisswange, T. H. (2023).** Graded disclosure in human-robot mediation. *Frontiers in Robotics and AI.*
- **Sullivan et al. (2025).** Benchmarking LLM privacy recognition for social-robot decision making. arXiv:2507.16124. — Motivates constrained on-device LLM use.
- **Apthorpe, N. et al. (2018).** Discovering smart home IoT privacy norms using contextual integrity. *PACM IMWUT.*
- **Lutz, C., & Tamò-Larrieux, A. (2021).** The robot privacy paradox. *Frontiers in Robotics and AI.* — Within-subjects design justification.
- **Granovetter, M. (1973).** The strength of weak ties. *American Journal of Sociology.*
- **Palen, L., & Dourish, P. (2003).** Unpacking "privacy" for a networked world. *CHI.*
- **Schroff, F., Kalenichenko, D., & Philbin, J. (2015).** FaceNet: A unified embedding for face recognition and clustering. *CVPR.*

**To add to the literature review in week 6:**

- Consent fatigue / "permission dialog overload" in mobile apps (Felt, Egelman, Wagner; Bonneau & Preibusch).
- Just-in-time vs. one-time consent design (Patil et al.).
- Local / on-device LLMs for privacy-sensitive applications.

---

*Companion documents: [survey_design.md](survey_design.md) (still vignette-flavoured; needs adapting to in-person rating instrument in week 2), [literature_review.md](literature_review.md).*
