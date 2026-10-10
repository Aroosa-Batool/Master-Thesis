# 20-minute midterm rehearsal sheet
Rehearse slides 1, 5, 10, 12 and 14 first. Then read the remaining cues.

## 1. Privacy-aware robot reminders (0.5 min)
My thesis explores how a social robot can deliver a useful reminder without revealing private information to people nearby. I use an Ohbot, a Bangle.js watch and local sensing. Today I will show the prototype, component measurements and the study I am preparing.

## 2. The privacy problem (1.5 min)
Use the appointment example throughout. Detection alone cannot determine whether sharing is socially acceptable. The watch lets the wearer respond discreetly and receive the reminder privately. Do not claim perfect privacy or visitor consent to recognition. Transition to the research questions.

## 3. Research questions (1.25 min)
RQ1 addresses the architecture. RQ2 is the main empirical question in the revised story survey. RQ3 currently addresses stated preferences, since the main study does not manipulate memory. These are proposed questions, not completed findings. Contribution at midterm: an end-to-end prototype and a clearly scoped evaluation design.

## 4. System components (2.25 min)
The laptop coordinates reminder scheduling, sensitivity classification and presence sensing. It sends a consent request to the watch and commands the robot. BLE connectivity is a coarse owner-presence proxy, not proof of wearing or room location. Core presence processing is local. The watch provides both consent input and private delivery.

## 5. Reminder delivery policy (2.25 min)
Walk through the four cases. Unanswered prompts never become remembered preferences. A refusal produces a neutral greeting and a watch note. The unified app withholds sensitive speech when sensing is inconclusive. Legacy fusion paths differ, so scope this safety behavior to the unified app. Recognition and sensitivity errors remain risks.

## 6. Sensing packages (1.5 min)
A silent visitor can evade microphone detection. A camera has a limited field of view. Fusion escalates after no non-owner voice is detected, including the owner-alone case. It does not guarantee less sensing in every situation. Current packages also differ in activation duration and head movement, so the study estimates perceptions of complete packages.

## 7. Consent memory (1.25 min)
Memory exists in camera, microphone and fusion apps. Re-ask stores no disclosure decisions but still retains recognition galleries. Apps use a broad reminder key, so an answer can transfer across topics. Current revocation requires clearing local state. The trade-off is convenience versus outdated preferences. Revised survey memory items measure preference, not a causal treatment effect.

## 8. Prototype progress (1.25 min)
This is the progress checkpoint. The repository contains integrated delivery paths, a local presentation workstation, evaluation capture tools and revised survey preparation materials. Code availability does not prove real-world recognition accuracy, trust or confirmed private receipt. No participant findings are claimed today. The next slide contains actual bundled component measurements.

## 9. Early technical measurements (1.5 min)
Explain input sizes and units. Component latency is not total response time and excludes acquisition windows and user interaction. Do not rank face and voice models by these unlike units. Bundled ArcFace is 81.01 ms per crop and ECAPA is 31.28 ms per six-second utterance. Faster computation does not prove better identification. Labeled capture and false-match evaluation remain necessary.

## 10. Main study design (1.75 min)
The revised design is dated October 4. Six stories cross health, financial and personal topics with two relationship/settings. Each participant sees a story once, while sensing versions rotate between participants. Three allocations, two response schedules and six balanced orders yield 36 cells. This is not the sample size. Main visitors are detected in every package, enabling matched outcomes.

## 11. Outcomes and analysis (1.5 min)
Plan two primary contrasts with Holm correction. Account for participant dependence, base story, response schedule, actual outcome and presentation position. Core questions are adaptations or new items, not a validated scale. Optional RoSAS or MDMT modules would add burden. Participant N is the sampling unit. Sample size and survey duration require simulation and pilot evidence.

## 12. Study interpretation (1.25 min)
Primary fallback stories do not test experiencing camera activation. Camera-only has a continuous session preview. Microphone has a scheduled five-minute window. The audit finds that fusion camera capture may fill the remaining interval, so do not describe every scan as brief. The no-sensor story is private-only and appears last. Hypothetical judgments cannot establish live behavior or visitor experience.

## 13. Remaining work (1.5 min)
Present a sequence rather than invented dates. Complete institutional, ethics, storage, retention and withdrawal details. Pilot active-sensor and consent comprehension. Technical tests need labeled data, silent visitors, off-camera visitors, false matches and failure paths. Freeze the analysis before collection. Ask whether the current package comparison is sufficient or a distinct live fallback evaluation should be prioritized.

## 14. Midterm takeaway (0.75 min)
Close: the system implements a concrete privacy-aware reminder workflow. Early measurements address feasibility. The next phase addresses acceptability and recognition robustness. Request feedback on the package-comparison scope and whether a separate live fallback test is needed. Pause for questions.

## 15. Discussion (0 min)
Outside the 20-minute speaking budget. Likely answers: BLE does not prove room presence. Re-ask does not delete recognition galleries. Consent expiry is proposed. The survey does not establish live behavior. Silent visitors can evade microphone detection and trigger camera fallback. No participant results are available in these materials.
