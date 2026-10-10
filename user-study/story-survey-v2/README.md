# Ohbot and Bangle.js story survey — researcher review draft

Prepared 4 October 2026. Start with [survey-draft.md](survey-draft.md). The draft includes participant-facing wording, six matched story families, repeated questions, overall preferences, demographics, and debriefing. [stimulus-bank.md](stimulus-bank.md) expands all 36 main-story variants into complete illustrated text. [research-design.md](research-design.md) contains the assignment scheme, question provenance, scale recommendations, implementation audit, and analysis plan. [illustration-storyboard.md](illustration-storyboard.md) contains the storyboard, verified device references, image prompts, and visual QA requirements. [story-assignments.csv](story-assignments.csv) contains every main-study stimulus assignment; [order-schedule.csv](order-schedule.csv) gives the balanced presentation orders.

This is a separate revision package. The existing `user-study/index.html` and its images remain the earlier draft; they do not implement this design. No participant responses are collected by this package. Review the institutional placeholders before transferring the draft to your approved survey platform. Generated images are draft stimuli requiring hardware-owner review, not evidence of a real interaction.

## Recommended study

Each participant reads six stories: two microphone-only, two camera-only, and two microphone-first/camera-fallback. Each base story appears in only one sensing condition for that participant, but rotates across all three conditions across participants. Three topics are crossed with two relationships. A separate counterbalanced script schedule changes Yes/No responses without changing the sensing assignment. Every participant therefore encounters one consented aloud delivery and one private delivery per sensing condition.

The proposed no-sensor comparison follows as a clearly separate exploratory story. It uses neither microphone nor camera and delivers sensitive reminders privately to the watch. It changes the delivery policy as well as sensing, so its ratings are not evidence of a pure sensor effect. Consent-memory preferences are assessed afterward, outside the main sensing manipulation.

The primary F stories detect a voice and therefore do not activate the camera. The silent-visitor example in the overall section explains the actual fallback branch. This choice keeps primary outcomes matched; it does not test the experienced effect of a camera fallback. The research design describes a separate factorial extension if observing that branch is essential.

Rebuild the expanded stimuli and assignment tables with `python3 user-study/story-survey-v2/build_stimuli.py` from the repository root. The generator verifies per-condition response/relationship balance, all story positions and immediate predecessors, and image availability. It is a review-artifact generator, not a participant survey runner.

## Reference review

The supplied archive was used because the OSF web file listing was inaccessible through the research browser. All 21 questionnaire screenshots were inspected. The 58 scenario metadata files and 368 numbered script lines were parsed as data, never executed; their text is indexed in `osf-reference-inventory.json`. The archive also contains WAV dialogue assets and a 456-row `phase2_out.csv`. The CSV has participant/scenario fields and columns named Privacy, Trust, Social Norms and Privacy Inclination; those labels do not establish item validity or scoring provenance. Audio assets were inventoried, not used as stimuli or assumed to be videos. No original study title, authors, ethics wording, license, allocation method, or sample-size rationale is inferred from the archive.

## Known review decisions

- Verify the actual Ohbot version, camera accessory and watch generation. Public reference images show Ohbot v2.2 and Bangle.js 2; the repository alone does not establish those exact hardware versions.
- Decide whether to evaluate current sensor packages, including camera duration differences, or implement matched sensing windows first. This draft describes current packages honestly.
- Watch-based sensor and memory setup controls are proposed; existing watch code implements disclosure Yes/No and private notifications.
- Choose the optional validated-measure module before piloting; the core survey is complete without it and makes no validated-scale claim.
- Supply institution, investigator, ethics, survey storage, retention, compensation and withdrawal details. Re-estimate duration in a cognitive pilot; the earlier 8–10-minute estimate does not apply to this larger draft.
