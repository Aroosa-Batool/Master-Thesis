# Draft analysis plan — sensor comfort vignette study

Freeze and time-stamp this plan **before** examining main-study outcomes. Items marked “proposed” require supervisor and ethics approval.

## Research question

How does the presence-sensing approach—microphone only, camera only, or microphone followed by camera only when needed—affect perceived acceptability, comfort, privacy concern, trust, control, transparency, bystander comfort, and willingness to use a privacy-aware reminder robot?

## Design

- Design: one-factor, three-level, within-subject vignette study.
- Unit of analysis: eligible participant.
- Perspective: the participant imagines being the robot owner/watch wearer.
- Fixed across conditions: reminder sensitivity, watch-mediated disclosure choice, local processing, non-retention of raw audio/video, local storage of a compact biometric representation and earlier disclosure choice, and visible sensor status.
- Manipulated factor: `sensor_condition` with levels `microphone`, `camera`, and `sequential`.
- Order: independently randomized per browser session; exported as `condition_order`.

Camera-only remains a valid comparison because the repository contains standalone camera applications even though the main unified flow prioritizes microphone-first fusion.

## Outcomes

### Primary outcome

`ACC1`: “This approach is acceptable for detecting whether another person is present,” scored 1–7. This single, direct item avoids creating an unjustified composite after seeing results.

### Secondary outcomes

- `COM1`: participant comfort, 1–7.
- `PRV1`: privacy concern, 1–7; higher means more concern.
- `CTL1`: perceived control, 1–7.
- `TRN1`: perceived transparency of active sensing, 1–7.
- `TRU1`: trust in sensitive-reminder handling, 1–7.
- `INT1`: willingness to use, 1–7.
- `BYS1`: expected bystander comfort, 1–7.
- `BEN1`: perceived privacy-benefit/sensing-cost balance, 1–7.
- Forced-choice most and least preferred conditions.
- Preference for re-asking versus remembered/expiring/context-dependent disclosure choices.
- Desired decision-expiry interval.
- Free-text reasons, concerns/reassurances, and desired changes.

The repeated items are study-specific. Analyze them individually. A proposed exploratory acceptance composite may average `COM1`, reverse-coded `PRV1`, `TRU1`, `ACC1`, `INT1`, and `BEN1` only if the construct was specified before outcome inspection and its internal consistency and dimensionality are acceptable. Report item-level results even if a composite is used.

## Proposed hypotheses

- **H1 (primary, non-directional):** acceptability ratings differ across the three sensor conditions.
- **H2 (proposed directional):** camera-only produces greater privacy concern than microphone-only.
- **H3 (proposed directional):** the sequential condition is more acceptable than camera-only because the camera is conditionally activated.
- **H4 (proposed directional):** expected bystander comfort is higher for microphone-only than camera-only.

If these hypotheses were written after any main-study outcomes were observed, label them exploratory rather than confirmatory.

## Eligibility and exclusions

Pre-specify the final policy in the ethics protocol. Recommended draft:

- Include participants aged 18 or older who consented and completed all required outcome items.
- Exclude test records and exact duplicate participant codes. Resolve duplicates using a predeclared rule; do not choose the more favorable response.
- Do not exclude responses solely because ratings appear unfavorable or have low variance.
- Treat failed manipulation checks transparently. Primary analysis can include all otherwise eligible responses; repeat it as a sensitivity analysis excluding participants who fail two or more of the three checks. Report both and the number excluded.
- Flag implausibly short durations using a threshold set from piloting, not after inspecting group differences. Report results with and without flagged responses.
- Do not impute missing primary outcomes. State the missing-data pattern and use available paired cases for each comparison.

## Sample size

Determine sample size with an a priori power analysis for the primary three-condition within-subject comparison. Document:

- assumed effect and its source (closest study or pilot);
- alpha and desired power;
- expected exclusions/incompletes;
- the test used in the calculation; and
- the final recruitment stop rule.

Avoid claiming that a conventional number such as 20–30 is sufficient without a calculation. If recruitment is constrained, describe the study as exploratory/pilot and emphasize effect estimates and uncertainty.

## Quantitative analysis

1. Lock the valid-response set and exclusions before comparing conditions.
2. Report counts, missingness, manipulation-check performance, condition orders, and completion duration.
3. Plot all ordinal distributions and paired participant trajectories; report median and interquartile range for each condition.
4. Primary omnibus test: Friedman test of `ACC1` across the three conditions.
5. If the omnibus test is significant—or if pairwise contrasts were explicitly planned—run paired Wilcoxon signed-rank tests for microphone vs camera, microphone vs sequential, and camera vs sequential. Apply Holm correction across the three primary pairwise comparisons.
6. Report Kendall's W for the omnibus test and a matched rank-biserial effect size with confidence interval for each paired contrast. State how zero differences/ties are handled by the software.
7. Analyze secondary items using the same descriptive approach. Correct for the declared family of inferential secondary tests or label them exploratory; do not present many uncorrected p-values as confirmatory.
8. Summarize forced-choice preferences with counts and percentages. A chi-square goodness-of-fit or exact multinomial test may be exploratory; show the raw counts.
9. Inspect order effects by plotting and, if adequately powered, modeling rating as a function of condition, presentation position, and their interaction. Treat this as a sensitivity analysis rather than changing the main test post hoc.
10. Report exact software versions, packages, analysis code, alpha, confidence level, exclusions, deviations, and all tested outcomes.

Do not interpret a non-significant result as proof that conditions are equivalent. Equivalence requires predeclared smallest effect sizes of interest and an equivalence design/test.

## Qualitative analysis

- Export comments without participant contact information.
- Develop a short codebook from a subset covering perceived surveillance, recording/retention, controllability, transparency/indicators, detection reliability, social acceptability, conditional activation, and desired controls.
- Have two researchers independently code a subset if resources allow, discuss disagreements, then apply the refined codebook consistently.
- Report theme frequencies only as descriptive context; include concise de-identified excerpts under the approved consent wording.
- Preserve negative cases and suggestions that contradict the preferred design.

## Planned figures for the thesis

- Paired dot/line plot of `ACC1` across all three conditions.
- Diverging stacked Likert chart for the nine items, faceted by condition.
- Forced-choice preference bar chart with count labels.
- Theme table linking qualitative concerns to concrete design implications.

Avoid bar charts of means without the underlying ordinal distributions.

## Interpretation limits

- Ratings concern illustrated hypothetical use, not observed long-term behavior.
- The sequential condition uses a two-panel image, creating greater visual complexity than the single-panel conditions.
- AI-generated visuals do not exactly depict Ohbot hardware.
- Primary users estimate bystander comfort; this is not direct bystander evidence.
- Recruitment channel and self-selection may overrepresent technically interested or privacy-aware participants.
- The scenario discloses local processing and raw-data deletion, so findings may not generalize to cloud processing or recording systems.
