# Design, provenance and analysis

## Scope and estimand

The primary study compares **perceived acceptability of three implemented sensing packages under detected-bystander, fresh-consent stories**. It does not estimate sensor accuracy, live behavior, bystander consent, or the privacy advantage of the fallback branch. All primary visitors speak and are visible, so detection, watch response and outcome can be matched. Fallback is available in F but remains inactive in these six stories. The overall fallback example evaluates stated preference after explanation; report that distinction explicitly.

Camera-only currently has a continuously open preview; microphone-only listens for a scheduled five-minute window; unified fusion can scan for roughly the remaining two minutes. Thus modality is bundled with activation timing and visible head movement. Do not call the result a causal effect of sensor type alone. A future pure-modality experiment requires matched acquisition windows and implementation changes verified before freezing stimuli.

## Matched-story assignment

M = microphone only; C = camera only; F = microphone first/camera fallback. Each story has all three versions in the stimulus bank. Participants see each story once, with the following allocation:

| Base story | Topic | Relationship/setting | Allocation L1 | L2 | L3 | Response A | Response B |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | Health appointment | Friend/home | M | C | F | No/private | Yes/aloud |
| S2 | Health appointment | Colleague/office | C | F | M | Yes/aloud | No/private |
| S3 | Financial payment | Friend/home | F | M | C | No/private | Yes/aloud |
| S4 | Financial payment | Colleague/office | M | C | F | Yes/aloud | No/private |
| S5 | Personal appointment | Friend/home | C | F | M | No/private | Yes/aloud |
| S6 | Personal appointment | Colleague/office | F | M | C | Yes/aloud | No/private |

For every L/A-or-B combination, each sensing condition has two stories, one friend and one colleague, one Yes and one No. Each base story appears in every condition across L1–L3 and both response schedules. The response schedule prevents relationship from always predicting disclosure outcome across the sample. Topic is crossed with relationship in the stimulus bank. Relationship remains bundled with home/office, so do not estimate an independent relationship effect or claim location was controlled across relationships.

Allocate participants across **36 cells: 3 sensing allocations × 2 response schedules × 6 story orders**. Use balanced randomized blocks: shuffle all 36 cells, assign one cell to each eligible participant, then reshuffle for the next block. Use server-side allocation for balance across participants; browser shuffling alone is insufficient. Record cell, allocation, response schedule, actual sequence and survey version. Incomplete blocks can be imbalanced; report realized counts. Choose sample size from power simulation rather than rounding to 36 for its own sake.

Six balanced orders (Williams construction, fixed story identities):

| Order | Sequence |
| --- | --- |
| W1 | S1, S2, S6, S3, S5, S4 |
| W2 | S2, S3, S1, S4, S6, S5 |
| W3 | S3, S4, S2, S5, S1, S6 |
| W4 | S4, S5, S3, S6, S2, S1 |
| W5 | S5, S6, S4, S1, S3, S2 |
| W6 | S6, S1, S5, S2, S4, S3 |

These balance positions and immediate story predecessors across a complete block. They do not eliminate every learning or contrast effect. S7 is appended as a separate proposed-policy exercise; its fixed position and different private-only policy make it exploratory. If S7 becomes a confirmatory fourth arm, redesign assignment, outcome matching, timing, power and the analysis before recruitment.

Main stimuli deliberately avoid sensor-specific privacy failures. Do not silently add silent visitors only to microphone stories. A separate robustness study could cross M/C/F with (speaking and visible / silent and visible / speaking and out of view), rotate each social context across all cells, and state actual detection and resulting outcomes. When outcomes differ because of sensor limitations, estimate total policy effects rather than outcome-controlled sensor effects. Memory should remain separate, or become an explicitly powered 3×2 sensing-by-memory factorial with repeat encounters.

## Question-source table

OSF screenshot filenames refer to the supplied archive. These are conceptual adaptations; no evidence establishes the OSF items as a validated scale.

| Draft IDs | Construct | Source and change | Status/scoring |
| --- | --- | --- | --- |
| C1 | Research participation consent | Newly written; institutional details unresolved | Administrative; decline terminates |
| I1–I2 | Permission and data comprehension | Newly written from code audit | Categorical; first/final answers recorded |
| Q1 | Realism | Study 1 Disclosure 3, Control 2, Withhold 2: conversation realism adapted to everyday reminder situation | Adaptation; individual ordinal item |
| Q2 | Sensitivity | Same Study 1 screenshots: sensitive-content judgment adapted to reminder content | Adaptation; individual ordinal item |
| Q3 | Privacy protection | Study 2 Questions 2: privacy protection/violation judgments consolidated into a positive protection item | Adaptation; do not treat as reversed validated scale |
| Q4 | Disclosure/withholding appropriateness | Study 1 Disclosure 3/Withhold 3 and Study 2 Questions 3/5: generalized to either delivery outcome | Adaptation; identical wording for Yes/No |
| Q5 | Trust with sensitive reminders | Study 1 Disclosure 5/Withhold 4 and Study 2 Questions 3: contextualized trust | Adaptation; not a validated trust score |
| Q6 | Comfort entrusting sensitive information | Study 1 Disclosure 4/Withhold 4; Study 2 Questions 4 | Adaptation; individual item |
| Q7 | Comfort around active sensing | Study 2 Questions 4: conversation comfort narrowed to sensing | Adaptation; S7 wording exception |
| Q8 | Disclosure control | Newly written for watch decision | New item |
| Q9 | Sensor-access control | Newly written; separates access from disclosure | New item |
| Q10–Q11 | Acceptability and willingness | Newly written; informed by earlier user-study constructs | New items, separate outcomes |
| Q12 | Recognition-data privacy concern | Newly written from retention audit | New item; higher = more concern |
| Q13–Q15 | Disclosure, activation and setup comprehension | Newly written from implemented branches | Categorical manipulation checks |
| Q16 | Influences on judgment | Study 1 Disclosure 5/Withhold 5/Control 4: factor prompts changed to an optional explanation | Adapted qualitative prompt |
| O1–O7 | Sensing/access/order and no-sensor preferences | Newly written for study purpose | Categorical, ordinal and qualitative |
| O8–O13 | Memory, expiry, re-request and design preferences | Newly written; distinguishes existing and proposed controls | Preference only, not memory treatment effect |
| D1–D10 | Demographics and experience | Newly written broad categories | Optional, descriptive |
| R module | Warmth/competence/discomfort | RoSAS original 2017 items and response range | Validated source instrument; vignette use still needs evaluation |
| T module | Performance trust and ethical trust | MDMT v2 author-authorized selection of complete subscales | Source-preserved subscales, not full MDMT or full Moral Trust |

## Robot-perception and trust measures

The [HRI Scale Database](https://hriscaledatabase.psychology.gmu.edu/Database/) was used to locate candidate instruments, then primary publications and author instructions were checked. Its checklist ratings summarize reporting criteria, not a guarantee of fit to this study. Its RoSAS page lacks item downloads; its MDMT v2 page says instructions are not readily available, but the authors' Brown-hosted instructions are accessible. Use the author version as the administration authority. Do not mix MDMT v1 and v2 names or item sets.

### Optional R module: original RoSAS

Recommend RoSAS when warmth, competence and discomfort are substantive secondary questions. Source: Carpinella, Wyman, Perez & Stroessner (2017), [original author-uploaded paper](https://www.researchgate.net/publication/314159812_The_Robotic_Social_Attributes_Scale_RoSAS_Development_and_Validation), DOI [10.1145/2909824.3020208](https://doi.org/10.1145/2909824.3020208). Item membership and anchors were verified in Study 2, and six-item means in Study 4. The original study also used image-based evaluations, supporting consideration for a vignette study without proving validity for privacy judgments.

Ask participants how strongly each adjective is associated with the robot in the described situation. This contextual stem is an adaptation of the referent; retain the actual adjectives and response range. Randomize the 18 adjectives, recording their order. Use numeric positions **1–9** with endpoint labels **1 “definitely not associated”** and **9 “definitely associated”**; do not convert these to seven-point agreement responses or add invented intermediate labels.

| Subscale | Verified adjectives |
| --- | --- |
| Warmth | feeling, happy, organic, compassionate, social, emotional |
| Competence | knowledgeable, interactive, responsive, capable, competent, reliable |
| Discomfort | aggressive, awful, scary, awkward, dangerous, strange |

Average the six items separately within each dimension; higher scores indicate more of that dimension. Do not reverse discomfort into warmth or collapse all 18 items. The study-specific Q7 is not a substitute for RoSAS discomfort. Original reports do not supply a universal missing-item rule: preregister the conservative complete-six rule for each subscale and show missingness; any relaxed rule is a researcher addition. Optional skip remains missing, outside the instrument range.

A [2025 original RoSAS-SF publication](https://link.springer.com/article/10.1007/s12369-025-01251-4) also exists. Do not invent a short form by choosing favorite original items. This draft specifies the original 18-item form; a deliberate switch requires checking the short form's exact items, anchors and scoring and freezing a new version.

### Optional T module: selected MDMT v2 subscales

Recommend MDMT v2 because reliable task performance and ethically handling sensitive content both matter. Read [Malle & Ullman (2023), original workshop paper](https://arxiv.org/pdf/2311.14887) and [author administration/scoring instructions, version 2023-09-30](https://research.clps.brown.edu/SocCogSci/Measures/MDMT_v2_(2023)_Full_scale.pdf). The authors permit selecting whole dimensions. For this survey, a 12-item selection of Reliable, Competent and Ethical avoids asking 20 trust items after every story while preserving complete subscales.

Rate each descriptor for the robot in this situation, with numeric choices **0–7**, endpoint labels **0 “Not at all”**, **7 “Very”**, and separate **“Does Not Fit”**. Do not use the study's seven-point agreement scale. Present four blocks of three, each with one item from each selected dimension:

| Block | Reliable | Competent | Ethical |
| --- | --- | --- | --- |
| 1 | reliable | competent | ethical |
| 2 | predictable | skilled | principled |
| 3 | dependable | capable | moral |
| 4 | consistent | meticulous | has integrity |

Average four responses for each dimension; the eight performance items form Performance Trust. Ethical alone is **not** the full Moral Trust factor, which in v2 also requires Transparent and Benevolent. Treat non-fit as missing, never zero. Authors do not set a universal minimum response count: preregister a complete-four rule per selected dimension and require both complete performance dimensions for the factor; report non-fit frequencies separately. A relaxed rule is an added analysis decision, not author scoring.

For full Moral Trust, use the complete author form through the linked source, preserving all 20 items and its five-dimension block balance. Do not reconstruct a hybrid from the older 16-item form. Author instructions say research use is free and request notification for community validation; no email was sent on the researcher's behalf.

### Where to administer optional scales

For a short core survey, omit R/T and report Q5 as a study-specific trust item. For a robot-perception study, administer the chosen full module(s) after each of the six main stories so the condition comparisons have the same exposure basis. This substantially increases burden: R adds 108 ratings and T adds 72. Pilot timing and fatigue before committing; do not retain the 15–20-minute estimate without measurement. A single global module at the end can describe the overall robot impression but cannot identify condition-specific scale differences. Do not administer scales only for whichever story a participant liked most.

## Implementation audit and boundaries

| Claim or discrepancy | Evidence in repository | Survey treatment |
| --- | --- | --- |
| Due reminders, sensitivity, connected-watch gate | `robot/core/reminders.py`, `voice_reminder.py`, `fusion_reminder.py` | Scheduled reminders; no heart-rate trigger |
| Five-minute continuous audio, T−7 to T−2 defaults | `robot/apps/reminder_app.py`, `voice_reminder.record_until` | Duration disclosed, not portrayed as a brief sample |
| Fallback only after no non-owner voice | `fusion_reminder.sense_bystander`, `check_mic` | Separate allowed sensors from sensors actually used |
| Camera can open immediately and fill remaining time | `fusion_reminder.py` lines around 610–650 | Avoid README claim of a late, brief scan |
| Camera-only opens before main loop; releases on exit | `robot/apps/camera_reask.py` | Continuous session-camera behavior disclosed |
| Sensor and memory setup are terminal configuration | `reminder_app.build_config`, `_launch` | Watch setup permissions explicitly proposed |
| Watch has disclosure and private-note functions | `bangle/consent_app.js`, `policy.BangleClient` | Exact existing prompt and Yes/No; no sensor setting UI invented |
| Timeout is not a cached No | `voice_reminder.py`, `fusion_reminder.py`, watch timeout | No-reply withholds; unanswered prompts not remembered |
| Connected BLE approximates presence | `policy.BangleClient.is_connected` | No exact room/wearing guarantee |
| Face/voice galleries persist in repeated-consent mode | `robot/perception/face_db.py`, `robot/core/owner.py` | Do not equate reask with deletion of recognition data |
| Consent store keys include content type, but apps use broad `reminder` key | `policy.ConsentKey`, `ConsentStore`, `robot_io.REMINDER_CONTENT_TYPE`, `camera_remember.py` | A choice can transfer across reminder topics; topic-specific consent is proposed |
| Fusion prefixes voice/face identity keys | `fusion_reminder.py` | No cross-modal identity guarantee |
| No TTL/deletion UI in consent store/watch app | `policy.ConsentStore`, `bangle/consent_app.js` | Expiry and watch editing are proposals |
| Logs can retain reminder text and decisions | `robot/core/logsetup.py`, camera delivery and voice/fusion logging | No broad “nothing is stored” claim |
| Unified fail-safe differs from legacy fusion | `reminder_app._launch`, `fusion_reminder.decide_and_deliver` | No general guarantee across apps; main stimuli successful operation only |
| Watch notification is one-way, not proof of reading | `policy.BangleClient.notify`, `bangle.notify` | Working-connection assumption; outcome stipulated, not measured |

The introduction's local-processing claim applies to the presence pipeline, not to all vendor Ohbot apps, TTS configurations, third-party services or future deployment. Raw-media claims exclude intentional evaluation capture. Verify enrollment capture, voice-reminder creation/transcription, TTS intermediate files and logging settings if a later live study includes them. Permissions from the wearer do not establish informed permission from visitors to biometric processing; this survey does not resolve that live-study requirement.

## What was retained and changed

Retained: an illustration followed by location, people/relationships, context, dialogue/action, repeated fully labeled seven-point judgments, an imagined participant perspective, and an optional explanation of influences. Study 1 provides realism, sensitivity and disclosure/withholding judgments; Study 2 provides robot privacy, trust, information-sharing comfort and appropriateness themes.

Changed: human-to-human information sharing becomes a scheduled Ohbot reminder with watch-mediated disclosure. Added actual sensing timing, recognition-data retention, sensor/access comprehension, separate control items, structured overall access/order preferences, memory and expiry choices, and a transparent proposed no-sensor policy. Removed video-dependent speech-quality judgments, duplicated negative formulations, social-norm claims without a verified scale, and the reference's attention-check commands. Those commands were participant-facing source examples and were never governing instructions. The new main design uses three matched sensing versions and a reproducible cross-participant allocation rather than assuming the archive demonstrates randomization or validated scoring.

## Concise preregistration-oriented analysis plan

1. **Primary outcome:** Q10 acceptability. Primary contrasts: F−M and F−C, two-sided, Holm family correction at .05. State the estimand as perceptions of described packages in detected-bystander contexts. Directional benefits are hypotheses, not conclusions. M−C is secondary.
2. **Model:** cumulative-link mixed model for ordinal Q10 with condition, base-story fixed effects, response schedule, actual Yes/No outcome and presentation position; participant random intercept and condition slopes if supported. Do not simultaneously include perfectly redundant outcome/relationship terms without checking the design matrix. Use story fixed effects to avoid pretending six fixed stories are a broad random sample of situations. If the random structure fails, simplify according to a preregistered rule and report it. A linear mixed-model sensitivity analysis may help interpretation, with clustered uncertainty; do not substitute six rows per participant for six independent people.
3. **Secondary outcomes:** Q3 privacy protection, Q5 trust, Q7 active-sensor comfort, Q8/Q9 control, Q11 willingness, Q12 recognition-data concern. Report distributions, effect estimates and 95% intervals; preregister a secondary multiplicity family. Q1/Q2 describe perceived realism/sensitivity, not automatic exclusions or post-treatment covariates in the primary model. Analyze optional source-preserved scale subscales/factors separately and report reliability in this sample; reliability does not establish validity.
4. **Missingness and eligibility:** exclude no-consent/ineligible entries and demonstrable duplicate submissions using an approved rule. Keep skipped/cannot-judge/non-fit responses missing. Report incomplete survey counts; mixed models use observed eligible ratings under their assumptions. Do not impute neutral answers. Preregister any speed threshold from pilot evidence, not a guessed cutoff. Keep a main analysis of all otherwise eligible respondents and a sensitivity analysis omitting participants failing at least two final setup/active-sensor checks; state the threshold before collection. Do not remove an opinion because it appears inconsistent with a comprehension key.
5. **Balance and power:** tabulate realized counts across 36 cells, stimulus positions and outcomes. Simulate the ordinal mixed design for a smallest meaningful condition difference and plausible participant heterogeneity, response probabilities, dropout and missingness. Choose N before recruitment; participant N is the sampling unit. No sample-size or power claim is inferred from the OSF CSV.
6. **Preferences:** report O1–O8 response frequencies with denominators and intervals, handling none/ties/not-sure explicitly. Show microphone/camera access comfort separately. O8–O12 measure memory preferences only; no causal memory-policy effect is estimated. S7 receives descriptive item distributions and clearly labeled exploratory comparisons; it confounds sensing with private-only delivery and appears last.
7. **Qualitative answers:** code Q16 and overall reasons for sensing intrusiveness, stored recognition data, relationship/topic, disclosure outcome, watch control and convenience. Allow new codes. Use a second coder on a prespecified subset if feasible, reconcile disagreements and retain an audit trail. Do not claim theme prevalence in the population or quote identifying text. Link themes to ratings cautiously.
8. **Limits:** hypothetical stated preferences, AI illustration realism, convenience recruitment, bundled timing/location effects, repeated-exposure demand characteristics, unknown hardware match, and a detected-bystander stimulus set. Robot-performance, speech-quality and visitor-experience conclusions require separate observed data.
