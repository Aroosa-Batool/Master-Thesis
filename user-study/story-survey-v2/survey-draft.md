# How should a reminder robot sense who is nearby?

Researcher draft, version story-survey-v2, 4 October 2026. Text in square brackets is a researcher placeholder or rendering instruction, not text to distribute unchanged. Estimated duration: 15–20 minutes for the core survey, subject to pilot measurement; optional scale modules add time.

## 1. Participant information and research consent

You are invited to take part in a master's thesis study at [INSTITUTION], conducted by [RESEARCHER, UNIVERSITY EMAIL], supervised by [SUPERVISOR, CONTACT]. The study examines people's views of a reminder robot and the ways it could sense whether someone else is nearby.

You will read illustrated fictional situations and answer questions about privacy, control, comfort, trust and preferences. You will not operate a robot or provide a face or voice recording. The survey does not activate your microphone or camera or connect to your smartwatch. Some stories concern health, finances or personal appointments. Please do not enter your own sensitive information, names, or details identifying another person.

Participation is voluntary. You may skip a question, take a break, or stop before submission without giving a reason or suffering a penalty. [COMPENSATION OR NONE; EXPLAIN PARTIAL-COMPLETION POLICY]. Eligibility: [APPROVED AGE THRESHOLD AND OTHER CRITERIA].

We collect your ratings, optional written answers, broad demographic and technology-experience answers, a random response code, assigned stories and their order, and completion duration. [STATE WHETHER THE ACTUAL PLATFORM ALSO COLLECTS IP ADDRESSES, COOKIES OR DEVICE METADATA; DO NOT CLAIM ANONYMITY WITHOUT CHECKING]. Responses will be stored [LOCATION AND SYSTEM], accessible to [PEOPLE/ROLES], and retained for [PERIOD]. Results will be reported [AGGREGATE REPORTING AND APPROVED QUOTATION POLICY]. [STATE WHETHER DE-IDENTIFIED DATA WILL BE SHARED, WHERE, AND UNDER WHICH CONSENT].

Before submission you may withdraw by closing the survey. After submission, [EXACT WITHDRAWAL PROCEDURE USING RESPONSE CODE, DEADLINE, AND LIMITS AFTER ANONYMIZATION]. Contact [RESEARCHER] with questions or [INDEPENDENT ETHICS CONTACT] about participant rights. Ethics approval/reference: [APPROVED DETAILS].

**C1.** I have read the information above, meet the eligibility requirements, and voluntarily agree to participate. Options: **I agree to participate / I do not agree**. [Declining ends the survey; save no substantive answers without consent. Do not infer consent from continuing.]

## 2. Introduction: robot, watch and three separate decisions

[Show a verified device reference or neutral generated scene with Ohbot and Bangle.js. Name each device in a readable caption.]

Ohbot is a small desktop robot head connected to a computer. In this prototype it delivers reminders scheduled beforehand, such as an appointment or payment. Some reminders contain sensitive information. A Bangle.js smartwatch provides a quieter channel for permission questions and private reminder messages. A wrist display reduces public exposure but someone looking at the display could still read it.

The system can use a microphone, an external camera, or the microphone followed by the camera. The sensors connect to the computer; Ohbot's eyes are not camera lenses. The watch link is used as an approximate sign that the wearer is nearby. It cannot establish the exact room or confirm that the watch is being worn. The reminder and permission app does not use unrelated watch data such as heart rate or GPS location.

There are three different decisions:

1. **Sensor access:** whether the system may use the microphone, camera, both, or neither. Allowing sensing is not permission to speak a sensitive reminder aloud.
2. **Disclosure:** whether the robot may speak sensitive reminder content when it detects another person. The wearer answers privately on the watch using Yes or No.
3. **Remembering a disclosure decision:** whether an earlier Yes or No may be stored and reused when that person is recognized again. This is separate from sensor access and research participation.

**Prototype versus proposal.** The current watch app handles disclosure questions and private messages. Sensor choice and whether to remember answers are configured at startup on the computer; camera-only uses a separate application. Putting those setup choices on the watch is a proposed extension. In these stories, assume the displayed sensing setup was explicitly allowed before the scene. No new watch-based sensor-authorization interface is claimed to exist. The main stories use a fresh disclosure question each time another person is detected; previous disclosure answers are not reused.

### What each approach does

**Microphone only:** The computer listens for voices and compares voice representations with an enrolled owner representation. In the unified app's default schedule it records continuously for five minutes, starting seven minutes before a sensitive reminder, then analyzes that window. A silent visitor may be missed. Someone arriving after listening ends may also be missed. The camera is not used.

**Camera only:** The camera detects faces and compares face representations with an enrolled owner representation. In the current camera-only application the camera remains open during the running session, with a head scan used for reminder presence checks. It may miss a person outside its view, hidden from it, or not recognized correctly. The microphone is not used for presence sensing in this condition.

**Microphone first, camera fallback:** The microphone listens first. If it detects a non-owner voice, the camera is not activated. If no bystander voice is detected, the microphone closes and the camera checks the room. With the unified app's defaults this scan starts about two minutes before the reminder and can continue until just before it is due. Both sensors are permitted, but are not active simultaneously. No audible bystander does not prove that nobody else is present.

These descriptions compare complete sensing approaches, including their current timing; their activation duration is not identical. The system can make detection and identity errors. When a sensitive reminder is due, no detected bystander can lead to spoken delivery without a disclosure question. When a bystander is detected, a Yes answer permits speech; a No answer or no reply withholds the sensitive content from speech and attempts private watch delivery. If the watch is disconnected, private delivery cannot be guaranteed. The main stories assume a working connection. A neutral greeting such as “Hello there” may still be spoken when the sensitive content is withheld.

### Processing and stored information

The presence-recognition pipeline processes audio and camera frames on the computer. In normal reminder delivery, raw presence audio and camera frames are temporary and are not saved as an audio/video archive. The system does store numerical recognition representations of enrolled owners and recognized visitors in local files so that it can recognize them later. These face and voice representations are not photographs or replayable recordings, but they are identifying data, not anonymous information. Even the repeated-question mode can retain these recognition representations.

Reminder text and timing are saved. When remembering is enabled, explicit Yes/No disclosure decisions are also saved. Application logs can include reminder text, person IDs, events and decisions. The code does not establish an automatic deletion period for all of these files. A separate evaluation-data collection mode intentionally saves raw images or voice clips; it is outside the ordinary reminder-delivery behavior described here. This survey itself collects answers only, not those robot data. [Confirm final deployment configuration before use; do not generalize this description to all Ohbot vendor services.]

### Brief understanding check

**I1.** Does allowing the microphone automatically allow the robot to speak sensitive reminders around other people? **Yes / No / Not sure**. [Correct: No.]

**I2.** Which statement is correct? **No recordings means no identifying data are stored / Numerical face or voice representations can still be stored / The robot reads unrelated health data from the watch / Not sure**. [Correct: representations can still be stored.]

[Allow rereading and one retry with a neutral explanation. Record first and final responses.]

## 3. Illustrated stories

Please imagine that you are **Alex**, the watch wearer, in each story. Judge the described behavior; there are no right or wrong opinion answers. The pictures are hypothetical AI-generated illustrations, not photographs or sensor recordings. Device appearance is illustrative and will be checked against the study hardware. Dialogue and watch messages appear below the images so they remain readable.

[Show one assigned version of each of S1–S6 in the allocated order. Each has three equal panels: setting and sensing; private disclosure prompt; delivery. Reuse exactly the same base illustration across sensing versions. Keep titles neutral and do not label outcomes “privacy success” or “privacy failure.” All visitors speak during the microphone window and are visible during camera checks. This makes the primary stories matchable; the introduction already explains blind spots.]

### Shared rendering rules for every main story

**Setup caption:** “Previously allowed sensing: [Microphone only / Camera only / Microphone and camera]. Disclosure policy: ask each time a visitor is detected. Do not remember disclosure answers.” This is a description of a prior setup decision, not a claim that the existing watch app implements it.

Insert exactly one sensing sequence:

- **M:** “The microphone listens during the five-minute window before the reminder. Sam's voice is detected. The camera is not used.”
- **C:** “The camera is open during this session. At the reminder check, the robot turns its head and the camera detects Sam's face. The microphone is not used for presence sensing.”
- **F:** “The microphone listens during the five-minute window before the reminder. Sam's voice is detected, so the camera is not activated.”

The same existing disclosure message appears for all three: **Watch — Robot asks:** “I have noticed that someone is present with you. Do you want me to send private reminders in front of them?” **Buttons: Yes / No.** Here “send … in front of them” refers to speaking aloud, as explained above. This is the code's wording; clearer replacement wording would be a separate interface revision.

Two response schedules, A and B, are balanced across participants. In A, S1/S3/S5 use No and S2/S4/S6 use Yes. In B, reverse those responses. Every condition receives one Yes and one No within each participant. The person, topic, relationship, sensing result and illustration remain fixed. Only response and consequent delivery differ. No memory manipulation is introduced.

For **No**, print: “Alex taps **No**. Ohbot says only **‘Hello there.’** The connected watch displays **‘Reminder: [reminder text]’** as a private note. Sam does not hear the reminder content.”

For **Yes**, print: “Alex taps **Yes**. Ohbot says **‘Here is your reminder for [reminder text].’** Sam hears the reminder content. A private note is not used for this delivery.”

### S1 — Appointment, visiting friend

**Illustration:** home triptych; Alex wearing Bangle.js, Ohbot on the table, Sam seated opposite.

**Location:** Alex's living room. **People:** Alex and Sam, a close friend visiting for tea. **Context:** Alex previously scheduled a reminder marked sensitive. Sam stays for the entire sensing interval and the delivery.

**Action/dialogue:** During the microphone listening interval, Sam says, “Would you like some tea?” Alex replies, “Yes, thanks.” Sam's face is also visible during the camera check.

**Reminder text:** “your mental-health appointment at 3 PM today”.

[Insert assigned M/C/F sequence, identical disclosure watch prompt, assigned A/B response, and corresponding delivery wording.]

### S2 — Appointment, nearby colleague

**Illustration:** office triptych; same Alex and device designs, Sam in the opposite chair.

**Location:** Alex's desk in a shared office. **People:** Alex and Sam, a colleague Alex knows through work. **Context:** Sam is waiting to discuss a task and remains nearby through sensing and delivery. Alex's scheduled reminder is marked sensitive.

**Action/dialogue:** During the listening interval, Sam says, “Shall we look at the task after this?” Alex replies, “Yes, in a moment.” Sam's face is also visible during the camera check.

**Reminder text:** “your mental-health appointment at 3 PM today”.

[Insert assigned sequence, watch prompt, response and outcome.]

### S3 — Payment, visiting friend

**Illustration:** the same home triptych as S1, at the same display size.

**Location:** Alex's living room. **People:** Alex and Sam, a close friend visiting for tea. **Context:** Alex's scheduled financial reminder is marked sensitive. Sam remains nearby throughout sensing and delivery.

**Action/dialogue:** Sam says, “Would you like some tea?” during the listening interval. Alex replies, “Yes, thanks.” Sam's face is also visible during the camera check.

**Reminder text:** “your overdue loan payment due today”.

[Insert assigned sequence, watch prompt, response and outcome.]

### S4 — Payment, nearby colleague

**Illustration:** the same office triptych as S2.

**Location:** Alex's desk in a shared office. **People:** Alex and Sam, a colleague Alex knows through work. **Context:** Sam is waiting to discuss a task and remains nearby throughout sensing and delivery. Alex's financial reminder is marked sensitive.

**Action/dialogue:** Sam says, “Shall we look at the task after this?” during the listening interval. Alex replies, “Yes, in a moment.” Sam's face is also visible during the camera check.

**Reminder text:** “your overdue loan payment due today”.

[Insert assigned sequence, watch prompt, response and outcome.]

### S5 — Personal appointment, visiting friend

**Illustration:** the same home triptych as S1.

**Location:** Alex's living room. **People:** Alex and Sam, a close friend visiting for tea. **Context:** Alex's scheduled personal reminder is marked sensitive. Sam remains nearby throughout sensing and delivery.

**Action/dialogue:** Sam says, “Would you like some tea?” during the listening interval. Alex replies, “Yes, thanks.” Sam's face is also visible during the camera check.

**Reminder text:** “your confidential job interview at 4 PM today”.

[Insert assigned sequence, watch prompt, response and outcome.]

### S6 — Personal appointment, nearby colleague

**Illustration:** the same office triptych as S2.

**Location:** Alex's desk in a shared office. **People:** Alex and Sam, a colleague Alex knows through work. **Context:** Sam is waiting to discuss a task and remains nearby throughout sensing and delivery. Alex's scheduled personal reminder is marked sensitive.

**Action/dialogue:** Sam says, “Shall we look at the task after this?” during the listening interval. Alex replies, “Yes, in a moment.” Sam's face is also visible during the camera check.

**Reminder text:** “your confidential job interview at 4 PM today”.

[Insert assigned sequence, watch prompt, response and outcome.]

### S7 — Proposed comparison: neither sensor

**This is a proposed design, not a mode implemented in the current reminder app.**

**Illustration:** same home triptych and display size; caption the middle panel “Private delivery; no disclosure question”. **Location:** Alex's living room. **People:** Alex and Sam, a close friend visiting for tea. **Context:** the reminder is “your mental-health appointment at 3 PM today”. Sam says, “Would you like some tea?” and stays nearby.

**Setup:** Alex has selected neither microphone nor camera. **Policy:** without presence sensing, every sensitive reminder is sent privately to the connected watch. The robot does not infer that Alex is alone and does not speak sensitive content.

**Watch prompt and response:** no sensor request or disclosure question occurs during this scene; Alex previously selected no sensor access. **Robot action/outcome:** Ohbot says only “Hello there”. The watch displays “Reminder: your mental-health appointment at 3 PM today”. Sam does not hear the reminder content.

This policy gives up automatic aloud delivery of sensitive reminders, even when the wearer is alone. [Show after the six main stories. Treat as an exploratory policy comparison, not a fourth implemented sensing modality.]

## 4. Same questions after every story

Imagine being Alex. For Q1–Q12, select one option:

**1 Strongly disagree · 2 Disagree · 3 Somewhat disagree · 4 Neither agree nor disagree · 5 Somewhat agree · 6 Agree · 7 Strongly agree.**

[Show all seven labels for every item. Also provide a separate unscored “Cannot judge / prefer not to answer” option; it is missing data, not the midpoint. These are study-specific or adapted items, not a validated scale.]

| ID | Statement |
| --- | --- |
| Q1 | This situation could realistically happen in everyday life. |
| Q2 | The reminder contains sensitive information. |
| Q3 | The robot protected Alex's privacy in this situation. |
| Q4 | The way the robot delivered the reminder was appropriate in this situation. |
| Q5 | I would trust this robot to handle my sensitive reminders. |
| Q6 | I would feel comfortable giving this robot sensitive information for reminders. |
| Q7 | I would feel comfortable being nearby while the sensors described in this story are active. |
| Q8 | I would feel in control of whether my reminder content was spoken aloud. |
| Q9 | I would feel in control of which sensors this system could use. |
| Q10 | This sensing and reminder-delivery approach would be acceptable to me. |
| Q11 | I would be willing to use this approach for my own reminders. |
| Q12 | I would be concerned about the system storing face or voice recognition representations. |

For S7 only, render Q7 as “I would feel comfortable being nearby with neither sensor active.” This necessary adaptation is recorded; do not compare it as an identical active-sensor comfort item.

**Q13 — permission comprehension.** What did Alex's decision in this scene permit? **Speaking the reminder aloud / Delivering it privately without speaking its content / Remembering the answer for future encounters / There was no disclosure decision in this scene / Not sure**. [Yes → aloud; No → private; S7 → no disclosure decision.]

**Q14 — active-sensor comprehension.** Which sensors actually operated for presence sensing in this scene? **Microphone only / Camera only / Microphone then camera / Neither / Not sure**. [M → microphone; C → camera; F in main stories → microphone only, because a voice was detected; S7 → neither.]

**Q15 — configured approach comprehension.** Which approach was allowed in the setup? **Microphone only / Camera only / Microphone first, camera only if no bystander voice is detected / Neither / Not sure**. [Use condition assignment. Distinguish availability from actual activation.]

**Q16 — optional explanation.** What most influenced your answers? You may discuss the sensing, reminder content, relationship, watch question, delivery outcome or stored information. Please avoid personal or identifying details. [Free text.]

## 5. Overall preferences and permission choices

**O1.** Which implemented sensing approach did you like most? **Microphone only / Camera only / Microphone first with camera fallback / No preference / I would use none of them**. Why? [Optional free text.]

**O2.** Which did you like least? **Same three approaches / No preference / I found all unacceptable**. Why? [Optional free text; no forced distinct ranking.]

**O3.** If you could choose sensor access, what would you permit? **Neither / Microphone only / Camera only / Both / Not sure**. [This is access permission, not activation order or aloud-disclosure permission.]

**O4a.** I would feel comfortable allowing microphone access for the sensing behavior described. **O4b.** I would feel comfortable allowing camera access for the sensing behavior described. [Use fully labeled seven-point agreement choices above, plus cannot judge.]

**O5.** If you permitted both sensors, which activation policy would you prefer? **Microphone first, camera only if no bystander voice is detected / Camera first, microphone only if needed / Both at the same time / Let me choose before each reminder / No preference / I would not permit both / Not sure**. Camera-first and simultaneous operation are hypothetical alternatives. Why? [Optional.]

**O6 — fallback example.** Suppose Sam remained silent but was visible to the camera. With the microphone-first approach, no bystander voice would be detected, the microphone would close, and the camera would scan. If it detected Sam, the watch would then ask about aloud disclosure. “I would prefer this microphone-first/camera-fallback sequence to using the camera for every sensitive reminder.” [Fully labeled seven-point agreement, plus cannot judge. This measures a stated preference after explanation, not an observed branch experience.]

**O7.** Would you choose the proposed no-sensor policy, where all sensitive reminders go privately to the watch? **Yes / No / It depends / Not sure**. Why? [Optional.]

### Disclosure memory: a separate preference exercise

Both options below can use the same sensing approach. **Ask each time:** when a visitor is detected for a sensitive reminder, ask the wearer again. **Remember:** store an explicit Yes or No and reuse it when the same visitor is recognized. The current applications use one broad “reminder” key: an answer can apply to later reminders with different topics, not just an identical reminder. Current code has no automatic expiry in its decision cache. In the fused system, face and voice identities are separate, so the same person may prompt again when recognized through a different sensor. Recognition can be wrong. Memory refers to the wearer's permission to disclose around a visitor, not permission given by the visitor.

**O8.** Which disclosure policy would you prefer? **Always ask again / Remember only No answers / Remember both Yes and No answers / Let me choose for each answer / No preference / Not sure**. [Only always-ask and remember-both match existing policies; other options are proposals.]

**O9.** Should a previous Yes ever allow a later sensitive reminder to be spoken without a new question? **Yes / No / It depends / Not sure**. Why? [Optional.]

**O10.** If remembering is enabled, when should an answer expire? **After that reminder / At the end of that day / After one week / After one month / Only when I remove it / A duration I choose / Never remember answers / Not sure**. [Single choice; optional custom duration. All automatic expiry choices are proposed.]

**O11.** When should the robot ask again despite a saved answer? [Choose all that apply.] **Different reminder topic or sensitivity / Different location / Additional people present / Uncertain identity match / A different sensor recognizes the person / A long time since the last encounter / I changed or revoked a preference / Every reminder / Other / Not sure**. [Make Every reminder and Not sure exclusive.]

**O12.** How important would it be to view, change or delete saved disclosure decisions on the watch? **1 Not at all important / 2 Slightly important / 3 Somewhat important / 4 Moderately important / 5 Important / 6 Very important / 7 Extremely important / Cannot judge**. [A proposed interface capability, not an existing feature.]

**O13.** What one change would most improve your comfort or trust? [Optional free text.]

## 6. Demographics and experience

All questions are optional; include **Prefer not to answer** on each.

**D1 Age band:** 18–24 / 25–34 / 35–44 / 45–54 / 55–64 / 65+ [Adjust to approved eligibility]. **D2 Gender:** Woman / Man / Nonbinary / Self-describe [optional text]. **D3 Highest completed education:** Secondary school or below / Vocational qualification / Bachelor's degree / Master's degree / Doctorate / Other.

**D4 Smartwatch use:** Never / Previously, but not currently / Less than weekly / Weekly / Daily. **D5 Voice-assistant use:** Never / Less than monthly / Monthly / Weekly / Daily. **D6 Camera-based identification use, such as face unlock:** Never / Less than monthly / Monthly / Weekly / Daily. **D7 Interaction with a social robot:** Never / Once / A few times / Regularly. **D8 Familiarity with Ohbot:** Never heard of it / Heard of it but not used it / Used it. **D9 Familiarity with Bangle.js:** Same three options. **D10 Technical experience:** None / Basic everyday use / Some programming or electronics / Extensive programming or electronics. [Do not request diagnoses, income, exact birth date, employer or precise location.]

## 7. Debrief and submission

Thank you. This study concerns your views of fictional reminder situations. The pictures are AI-generated and do not show measured robot performance. The sensor and delivery behaviors are grounded in a research prototype; watch-based setup permissions, no-sensor delivery and expiry controls are proposed extensions. Your answers are opinions, not permission to activate a real sensor or to store a real disclosure preference.

[Show the response code, actual submission/return procedure, withdrawal contact and deadline. Offer Back to review / Submit / Withdraw without submitting. Provide an optional researcher contact link. Do not say responses were received until the actual collection system confirms that.]
