# Participant survey materials

Open **questionnaire.html** for the complete illustrated participant questionnaire. It is a self-contained file with both images embedded, works without JavaScript, and can be printed or saved as PDF from your browser. Its radio controls are for viewing or printing; it does not save responses. This booklet uses assignment L1-A-W1.

Open **preview.html** to try the step-by-step fillable survey. Preview exports are marked PREVIEW and are never sent to a collection endpoint. Answers exist only in the tab until exported; reloading clears them.

**participant-questions.txt** contains the same participant wording and options for copying into your survey platform. **assets/** contains the two generated story illustrations. The same image is deliberately reused for all sensor and delivery conditions in each location, so the visual treatment does not cue a preferred condition.

## Contents

Introduction and two comprehension questions; six counterbalanced main stories, each with 12 fully labeled agreement ratings, three comprehension questions and one optional explanation; one separately labeled proposed no-sensor comparison; overall sensing and disclosure-memory preferences; optional demographics and experience questions; closing explanation. Main stories combine health, finance and personal reminders with friend and colleague settings and Yes/No disclosure outcomes.

## Your administration and collection setup

As requested, institutional consent, ethics, contacts, retention and recruitment are yours to complete. The questionnaire booklet assumes these are supplied separately. For the optional web collection version, edit config.js and use index.html after completing those fields. The web template prevents enrollment until they are supplied. No server or public deployment is included.

Without submissionEndpoint, Finish creates downloadable JSON and CSV response files for manual return. A configured HTTPS endpoint must implement storage, cross-origin access where needed, and duplicate protection using participant_code. A successful HTTP response must mean the response was durably accepted. Test collection before inviting participants.

Use assigned links such as index.html?cell=L1-A-W1. There are 36 cells: L1–L3 × A–B × W1–W6. Recruit evenly across cells using the existing ../story-survey-v2/story-assignments.csv schedule. Independent random browser assignment cannot guarantee balance across a small sample. participant-materials.html?cell=L2-B-W3 displays a printable booklet for another cell, using JavaScript.

These are adapted research questions, not a newly validated psychometric scale. Keep the no-sensor comparison separate from primary condition comparisons. All main fallback stories detect a speaking visitor using the microphone, so their camera stays inactive; the overall-preference section explicitly describes a silent-visitor fallback. See ../story-survey-v2/research-design.md for provenance and analysis limits. The estimated duration is provisional and needs a pilot.

## Verification

JavaScript syntax passed. check-survey.cjs checks all 36 cells for unique stories, two presentations per mode, balanced relationships and Yes/No outcomes, and navigation through the optional-answer flow to local finish. The illustrated materials were opened and visually inspected in Safari. The collection endpoint and participant recruitment workflow require your setup and pilot.
