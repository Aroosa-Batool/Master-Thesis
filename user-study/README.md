# Microphone and camera comfort study

This folder is a distribution-ready **study draft**, not an ethics-approved instrument. It compares three sensing conditions while holding the reminder, watch-consent behavior, local processing, and retention explanation constant:

1. microphone only;
2. camera only; and
3. microphone first, then camera only if needed.

The page randomizes condition order per browser session and records that order with the response. Each condition uses the same nine 7-point items, a comprehension/manipulation check, and an optional free-text prompt. The overall section asks for preference, consent-memory policy, expiry, and design changes.

## Files

| File | Purpose |
| --- | --- |
| `index.html` | Fillable participant questionnaire |
| `study-config.js` | Researcher, ethics, and optional submission settings |
| `study.js` | Randomization, validation, coded export, and optional JSON submission |
| `study.css` | Responsive and print styling |
| `assets/condition-*.png` | Three matched AI-generated visual vignettes |
| `assets/image-prompts.md` | Reproducibility record for the generated images |
| `analysis-plan.md` | Draft design, hypotheses, exclusions, and statistical plan |
| `codebook.csv` | Variable names, response ranges, and scoring notes |
| `recruitment-copy.md` | Short and long invitation text with mandatory placeholders |
| `aggregate_responses.py` | Combines downloaded JSON responses into one CSV |

## Preview locally

From the repository root:

```bash
python3 -m http.server 8000 --directory user-study
```

Then visit `http://localhost:8000`. Opening `index.html` directly also works in modern browsers, but testing through HTTP better matches deployment.

## Mandatory steps before distribution

1. Obtain supervisor and institutional ethics approval for the final wording, images, recruitment route, age threshold, storage, retention period, and withdrawal process.
2. Replace every `[REPLACE: ...]` field in `study-config.js`. The page deliberately displays a warning while any remain.
3. Decide how responses will be collected. The default is **local download only**: nothing leaves the participant's browser automatically. Give participants an approved return channel. If the institution provides an approved HTTPS JSON endpoint, add it as `submissionEndpoint` and update the participant-information wording to match the real controller, storage location, retention, access, and withdrawal procedure.
4. Run cognitive interviews with 3–5 people to check that “sensitive reminder,” “local biometric representation,” the sequence condition, and the response anchors mean what you intend. Do not mix pilot and main-study responses unless the instrument remains unchanged and the protocol permits it.
5. Run an a priori power analysis using the planned primary comparison and a defensible expected effect. Do not present a convenience sample as adequately powered without that analysis.
6. Freeze a tagged/versioned copy before recruitment. Record the study version, dates, recruitment channels, eligibility criteria, exclusions, and deviations.
7. Test the deployed form on phone and desktop, including all three orderings, required fields, endpoint failure, JSON/CSV download, keyboard navigation, and screen-reader labels.

## Why this design is defensible

- **Controlled visual manipulation:** the robot, room, viewpoint, lighting, hand, watch, palette, and illustration style are matched. The main visible change is sensor state. The sequential image is necessarily a two-stage panel and should be acknowledged as a possible visual-complexity confound.
- **Within-subject comparison:** every participant evaluates every sensing approach, reducing between-person noise in baseline privacy attitudes.
- **Order control:** the three conditions are randomized, and `condition_order` is exported for balance checks and sensitivity analysis.
- **Same items in every condition:** comfort, privacy concern, control, transparency, trust, acceptability, willingness, perceived bystander comfort, and benefit-versus-sensing cost are measured identically.
- **Manipulation checks:** each condition asks which sensors were used. The analysis plan treats exclusions and sensitivity analysis explicitly rather than silently removing inconvenient responses.
- **Data minimization:** the form requests broad experience bands and no direct identifiers. Free-text prompts warn participants not to disclose sensitive details.
- **Transparent stimuli:** the form states that its illustrations are AI-generated hypothetical vignettes, not real sensor captures or a literal rendering of Ohbot.

The nine rating statements are **study-specific items**, not a validated psychometric scale. It is fine to analyze each construct separately. Do not call their average a validated “trust” or “privacy” score. If a composite is proposed, justify its construct, report internal consistency, and show the item-level results.

## Collection formats

The response contains:

- a random, non-identifying participant code;
- condition order and completion duration;
- pass/fail flags for the three manipulation checks; and
- all form answers.

JSON preserves the nested structure and is the preferred archival format. CSV is convenient for immediate inspection. To combine a folder of JSON files:

```bash
python3 user-study/aggregate_responses.py path/to/responses combined-responses.csv
```

The script refuses duplicate participant codes by default and never edits the source files.

## Deployment note

The questionnaire is plain static HTML/CSS/JavaScript and can be hosted by an institution-approved web server or static-site service. Static hosting alone does not collect responses. An endpoint must be configured and documented, or participants must return the downloaded response through an approved method.

## Academic positioning

This is a scalable **vignette study of stated perceptions**, not proof of behavior in a live robot interaction. A strong thesis presentation should pair it with a small hands-on or video-based pilot if feasible, and explicitly discuss ecological validity, hypothetical bias, self-selection, and the fact that visitors' comfort is estimated by the primary user rather than measured from bystanders directly.

The vignette method aligns with the contextual-integrity approach already identified in `docs/literature_review.md`, especially Apthorpe et al. (2018). The general HRI reporting rationale can be tied to Riek (2012). Check the final bibliography against the primary publications before submission.
