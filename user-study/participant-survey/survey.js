(function () {
  "use strict";
  const config = window.PARTICIPANT_SURVEY_CONFIG || {};
  const params = new URLSearchParams(window.location.search);
  const preview = params.get("preview") === "1" || window.SURVEY_PREVIEW_MODE === true;
  const materials = window.SURVEY_MATERIALS_MODE === true;
  const requiredConfig = ["institution", "researcher", "contact", "supervisor", "ethicsReference",
    "ethicsContact", "storageAndAccess", "retentionPeriod", "withdrawalProcedure", "compensation",
    "platformMetadata", "dataSharing", "returnInstructions"];
  const missing = requiredConfig.filter(key => !String(config[key] || "").trim());
  if (config.submissionEndpoint && !/^https:\/\//i.test(config.submissionEndpoint)) missing.push("valid HTTPS submission endpoint");
  const ready = missing.length === 0;
  const labels = ["Strongly disagree", "Disagree", "Somewhat disagree", "Neither agree nor disagree", "Somewhat agree", "Agree", "Strongly agree"];
  const modes = ["M", "C", "F"];
  const names = {M: "Microphone only", C: "Camera only", F: "Microphone first, camera fallback"};
  const sequences = {
    M: "The microphone listens during the five-minute window before the reminder. Sam’s voice is detected. The camera is not used.",
    C: "The camera is open during this session. At the reminder check, the robot turns its head and the camera detects Sam’s face. The microphone is not used for presence sensing.",
    F: "The microphone listens during the five-minute window before the reminder. Sam’s voice is detected, so the camera is not activated."
  };
  const topics = [["Appointment", "your mental-health appointment at 3 PM today"],
    ["Payment", "your overdue loan payment due today"], ["Personal appointment", "your confidential job interview at 4 PM today"]];
  const items = [
    "This situation could realistically happen in everyday life.",
    "The reminder contains sensitive information.",
    "The robot protected Alex’s privacy in this situation.",
    "The way the robot delivered the reminder was appropriate in this situation.",
    "I would trust this robot to handle my sensitive reminders.",
    "I would feel comfortable giving this robot sensitive information for reminders.",
    "I would feel comfortable being nearby while the sensors described in this story are active.",
    "I would feel in control of whether my reminder content was spoken aloud.",
    "I would feel in control of which sensors this system could use.",
    "This sensing and reminder-delivery approach would be acceptable to me.",
    "I would be willing to use this approach for my own reminders.",
    "I would be concerned about the system storing face or voice recognition representations."
  ];
  const base = ["M", "C", "F", "M", "C", "F"];
  function random(n) {
    const a = new Uint32Array(1);
    if (window.crypto && window.crypto.getRandomValues) {
      const limit = Math.floor(4294967296 / n) * n;
      do { window.crypto.getRandomValues(a); } while (a[0] >= limit);
      return a[0] % n;
    }
    return Math.floor(Math.random() * n);
  }
  function assignment(cell) {
    const match = /^L([123])-([AB])-W([1-6])$/.exec(cell || "");
    const allocation = match ? Number(match[1]) - 1 : random(3);
    const schedule = match ? match[2] : (random(2) ? "B" : "A");
    const order = match ? Number(match[3]) - 1 : random(6);
    const stories = [1, 2, 6, 3, 5, 4].map(s => (s - 1 + order) % 6 + 1).map((s, index) => {
      const mode = modes[(modes.indexOf(base[s - 1]) + allocation) % 3];
      const answer = ((s % 2 === 1) === (schedule === "A")) ? "NO" : "YES";
      return {story_id: `S${s}`, story: s, position: index + 1, condition: mode,
        active_sensors: mode === "C" ? "camera" : "microphone", watch_response: answer,
        delivery: answer === "NO" ? "private" : "aloud", topic: topics[Math.floor((s - 1) / 2)][0],
        relationship: s % 2 ? "friend" : "colleague", stimulus_id: `S${s}-${mode}-${answer}`};
    });
    return {cell_id: `L${allocation + 1}-${schedule}-W${order + 1}`, allocation: `L${allocation + 1}`,
      response_schedule: schedule, order_id: `W${order + 1}`, allocation_method: match ? "assigned_link" : "independent_random_cell", stories};
  }
  window.SURVEY_DESIGN = {assignment, items, labels};
  const esc = value => String(value == null ? "" : value).replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
  const field = key => esc(config[key] || "Not yet supplied by the researcher");
  function choices(name, title, options, type = "radio", required = false) {
    return `<fieldset><legend>${esc(title)}</legend><div class="choices">${options.map(option => {
      const pair = Array.isArray(option) ? option : [option, option];
      return `<label class="choice"><input type="${type}" name="${name}" value="${esc(pair[0])}" ${required ? "required" : ""}><span>${esc(pair[1])}</span></label>`;
    }).join("")}</div></fieldset>`;
  }
  function scale(name, title, anchors = labels) {
    return `<fieldset><legend>${esc(title)}</legend><div class="scale">${anchors.map((label, i) =>
      `<label class="choice"><input type="radio" name="${name}" value="${i + 1}"><strong>${i + 1}</strong>${esc(label)}</label>`).join("")}
      <label class="choice missing"><input type="radio" name="${name}" value="NA">Cannot judge / prefer not to answer</label></div></fieldset>`;
  }
  function text(name, title) {
    return `<label class="text-label" for="${name}">${esc(title)}</label><textarea id="${name}" name="${name}" rows="3" maxlength="1500" placeholder="Optional. Please avoid names and sensitive personal details."></textarea>`;
  }
  function select(name, title, options) {
    return `<label class="text-label" for="${name}">${esc(title)}</label><select id="${name}" name="${name}"><option value="">Select an answer (optional)</option>${options.concat(["Prefer not to answer"]).map(v => `<option>${esc(v)}</option>`).join("")}</select>`;
  }
  function image(home) {
    return `<img class="story-image" src="assets/${home ? "home" : "office"}-triptych-neutral-v2.png" width="2172" height="724" alt="Alex, with a gender-neutral appearance, sits on the left wearing a black Bangle.js watch. Sam sits on the right. Blue Ohbot turns toward Sam in all panels; Alex checks the watch in the middle panel, then looks up again."><p class="caption">Hypothetical AI-generated scene. Read the captions for sensing state, watch messages and delivery outcome.</p>`;
  }
  const sensorOptions = [["M", "Microphone only"], ["C", "Camera only"], ["F", "Microphone first, camera only if no bystander voice is detected"], ["N", "Neither"], ["unsure", "Not sure"]];
  const activeOptions = [["microphone", "Microphone only"], ["camera", "Camera only"], ["sequential", "Microphone then camera"], ["neither", "Neither"], ["unsure", "Not sure"]];
  let page = 0, session = null, answers = {}, started = null, prepared = null, completed = false;
  const pageNode = document.getElementById("page");
  const form = document.getElementById("survey");
  function info() {
    return `<h1 id="page-title">How should a reminder robot sense who is nearby?</h1>
      <p>A study about privacy, comfort and control with Ohbot and a Bangle.js smartwatch. Allow approximately ${field("estimatedMinutes")} minutes.</p>
      <h2>Before you decide</h2><p>You are invited to a master’s thesis study at <strong>${field("institution")}</strong>, conducted by ${field("researcher")} (${field("contact")}) and supervised by ${field("supervisor")}.</p>
      <p>You will read six illustrated fictional stories and a proposed comparison, then answer questions about the robot’s behavior and your preferences. You will not operate a robot or provide a face or voice recording. The survey does not activate your microphone or camera or connect to a watch.</p>
      <p>Stories include health, financial and personal reminders. Please do not disclose your own sensitive information or details identifying other people.</p>
      <p>Taking part is voluntary. You may skip any opinion or demographic question and stop before submission without a penalty. Eligibility: age ${Number(config.minimumAge || 18)} or older. Compensation: ${field("compensation")}.</p>
      <h2>Your answers and privacy</h2><p>We collect ratings, optional explanations, broad demographic and experience answers, a random response code, assigned stories, order and completion time. Your answers stay in this tab’s memory until you finish; reloading or closing the page clears them. ${config.submissionEndpoint ? "On submission, answers are sent to the configured research collection service." : "No answers are sent automatically. You will download a response file and return it through the researcher’s stated channel."}</p>
      <p>Storage and access: ${field("storageAndAccess")}. Retention: ${field("retentionPeriod")}.</p><p>Platform metadata: ${field("platformMetadata")}.</p><p>Reporting and data sharing: ${field("dataSharing")}.</p>
      <p>Before finishing, use “Withdraw and clear my answers” to stop. After returning or submitting answers: ${field("withdrawalProcedure")}.</p>
      <p>Study questions: ${field("contact")}. Participant-rights contact: ${field("ethicsContact")}. Ethics reference or approved wording: ${field("ethicsReference")}.</p>
      ${choices("C1", "Would you like to take part?", [["agree", "I have read this information, meet the age requirement, and voluntarily agree to participate."], ["decline", "I do not agree to participate."]], "radio", true)}`;
  }
  function intro() {
    return `<h1 id="page-title">Meet the robot and watch</h1>${image(true)}
      <p>Ohbot is a small desktop robot head connected to a computer. It delivers reminders scheduled beforehand, including sensitive appointments or payments. An external camera and a microphone can help the computer recognize whether another person is nearby. Ohbot’s eyes are not camera lenses.</p>
      <p>Bangle.js displays private permission questions and reminder messages. A wrist display reduces public exposure, although someone looking at it could still read it. The watch connection is an approximate sign that the wearer is nearby, not proof of the exact room or that the watch is being worn. This reminder app does not use unrelated health or GPS data from the watch.</p>
      <h2>Three different decisions</h2><ol class="summary-list"><li><strong>Sensor access:</strong> permitting the microphone, camera, both or neither. This does not permit aloud disclosure.</li><li><strong>Aloud disclosure:</strong> when another person is detected, the watch asks whether a sensitive reminder may be spoken. Yes permits speech; No withholds the content from speech and sends a private watch note.</li><li><strong>Remembering:</strong> permitting a previous Yes or No to be stored and reused. The main stories ask each time and do not reuse an earlier answer.</li></ol>
      <p>The current watch app handles disclosure questions and private notes. Sensor and memory settings are configured on the computer; putting these setup choices on the watch is a proposed extension. Assume the sensing setup in each story was explicitly allowed before the scene.</p>
      <h2>The sensing approaches</h2><div class="story"><h3>Microphone only</h3><p>The system listens for non-owner voices. With the unified app’s defaults it records continuously for five minutes, from seven to two minutes before a sensitive reminder. A silent visitor, or someone arriving after listening ends, may be missed. The camera is not used.</p></div>
      <div class="story"><h3>Camera only</h3><p>In the current camera-only application the camera stays open during the running session, with a head scan used for reminder checks. It may miss a face outside its view, hidden from it or incorrectly recognized. The microphone is not used for presence sensing.</p></div>
      <div class="story"><h3>Microphone first, camera fallback</h3><p>The microphone listens first. When a non-owner voice is detected, the camera is not activated. Otherwise, the microphone closes and the camera scans. With the unified app’s defaults this can continue for about two minutes until just before delivery. Both sensors are permitted but never active simultaneously.</p></div>
      <p>These approaches have different activation durations. Detection can be wrong. If no visitor is detected, the system can speak a sensitive reminder without a disclosure question. A No or no reply withholds sensitive speech and attempts watch delivery. If the watch is disconnected, that private delivery is not guaranteed. All stories assume a working watch connection.</p>
      <h2>What is stored?</h2><p>The presence pipeline processes audio and frames on the computer. Raw presence recordings and frames are temporary during ordinary reminder delivery. Numerical face and voice recognition representations are saved locally to recognize owners and visitors later. These are identifying data, even though they are not replayable recordings.</p>
      <p>Even the repeated-question mode can retain recognition representations. Reminder text and timing are saved. Remembering mode also saves explicit disclosure answers. Logs can include reminder content, person IDs and decisions. The code does not establish an automatic deletion period for all these files. A separate evaluation-data mode intentionally saves raw images or voice clips; it is outside these ordinary reminder stories.</p>
      <h2>Before the stories</h2><p>Imagine you are <strong>Alex</strong>, the watch wearer. Judge the described behavior. Opinion questions have no right or wrong answers, and may be skipped.</p>
      ${choices("I1", "Does permitting microphone access automatically permit sensitive reminders to be spoken around other people?", [["yes", "Yes"], ["no", "No"], ["unsure", "Not sure"]])}
      ${choices("I2", "Which statement is correct?", [["nothing", "No recordings means no identifying data are stored"], ["representations", "Numerical face or voice representations can still be stored"], ["health", "The robot reads unrelated health data from the watch"], ["unsure", "Not sure"]])}`;
  }
  function ratings(id, noSensor = false) {
    return `<h2>Your view of this situation</h2><p class="helper">Imagine being Alex. Choose one answer per statement, or leave it unanswered. All seven agreement labels are shown.</p>` + items.map((item, index) => scale(`${id}_Q${index + 1}`, noSensor && index === 6 ? "I would feel comfortable being nearby with neither sensor active." : item)).join("")
      + choices(`${id}_Q13`, "What did Alex’s decision in this scene permit?", [["aloud", "Speaking the reminder aloud"], ["private", "Delivering it privately without speaking its content"], ["memory", "Remembering the answer for future encounters"], ["none", "There was no disclosure decision in this scene"], ["unsure", "Not sure"]])
      + choices(`${id}_Q14`, "Which sensors actually operated for presence sensing?", activeOptions)
      + choices(`${id}_Q15`, "Which approach was allowed in the setup?", sensorOptions)
      + text(`${id}_Q16`, "What most influenced your answers? (optional)");
  }
  function story(s) {
    const home = s.story % 2 === 1, reminder = topics[Math.floor((s.story - 1) / 2)][1];
    const no = s.watch_response === "NO";
    return `<span class="tag">Story ${s.position} of 6 · ${esc(names[s.condition])}</span><h1 id="page-title">${esc(s.topic)}</h1>${image(home)}
      <div class="facts"><div class="fact"><strong>Location</strong>${home ? "Alex’s living room" : "Alex’s desk in a shared office"}</div><div class="fact"><strong>People</strong>Alex and Sam, ${home ? "a close friend visiting for tea" : "a colleague Alex knows through work"}</div></div>
      <p><strong>Context:</strong> Alex scheduled a sensitive reminder: <strong>“${esc(reminder)}”</strong>. Sam remains nearby throughout sensing and delivery.</p>
      <p><strong>Previously allowed sensing:</strong> ${s.condition === "F" ? "Microphone and camera" : esc(names[s.condition])}. <strong>Disclosure policy:</strong> ask each time a visitor is detected; do not remember disclosure answers.</p>
      <div class="story"><h2>1. Conversation and sensing</h2><p>During the pre-reminder interval, Sam says, “${home ? "Would you like some tea?" : "Shall we look at the task after this?"}” Alex replies, “${home ? "Yes, thanks." : "Yes, in a moment."}” Sam’s face is visible to the robot if the camera is used.</p><p>${esc(sequences[s.condition])}</p></div>
      <div class="watch"><h2>2. Private watch question</h2><p><strong>Robot asks:</strong> “I have noticed that someone is present with you. Do you want me to send private reminders in front of them?”</p><p>Watch buttons: <strong>Yes / No</strong>. Here, “send … in front of them” means speaking aloud.</p></div>
      <div class="story"><h2>3. Alex’s response and delivery</h2><p>Alex taps <strong>${no ? "No" : "Yes"}</strong>.</p>${no ? `<p>Ohbot says only <strong>“Hello there.”</strong> The connected watch displays <strong>“Reminder: ${esc(reminder)}”</strong> as a private note. Sam does not hear the reminder content.</p>` : `<p>Ohbot says <strong>“Here is your reminder for ${esc(reminder)}.”</strong> Sam hears the reminder content. A private note is not used for this delivery.</p>`}</div>${ratings(s.story_id)}`;
  }
  function noSensor() {
    return `<span class="tag">Proposed comparison · Neither sensor</span><h1 id="page-title">A private-only approach</h1>${image(true)}
      <p>This is a <strong>proposed design</strong>, not a mode implemented in the current reminder app.</p>
      <div class="facts"><div class="fact"><strong>Location</strong>Alex’s living room</div><div class="fact"><strong>People</strong>Alex and Sam, a close friend visiting for tea</div></div>
      <p>Alex scheduled the sensitive reminder <strong>“your mental-health appointment at 3 PM today”</strong>. Sam says, “Would you like some tea?” and stays nearby.</p>
      <div class="story"><h2>1. Neither sensor permitted</h2><p>Alex previously selected no microphone or camera access. Neither sensor operates. The system cannot tell whether Alex is alone.</p><h2>2. No disclosure question</h2><p>Every sensitive reminder goes privately to the connected watch. There is no Yes/No disclosure question. The watch gesture in the illustration represents viewing the note.</p><h2>3. Private delivery</h2><p>Ohbot says only <strong>“Hello there.”</strong> The watch displays <strong>“Reminder: your mental-health appointment at 3 PM today.”</strong> Sam does not hear the reminder content.</p></div>
      <p>This policy gives up automatic aloud delivery of sensitive reminders, even when the wearer is alone.</p>${ratings("S7", true)}`;
  }
  function preferences() {
    return `<h1 id="page-title">Your overall preferences</h1><p>Think about all the stories. These choices express your opinions; they do not activate sensors or set permissions on a real device.</p>
      ${choices("O1", "Which implemented sensing approach did you like most?", sensorOptions.slice(0, 3).concat([["equal", "No preference"], ["none", "I would use none of them"]]))}${text("O1_reason", "Why did you like that approach most?")}
      ${choices("O2", "Which approach did you like least?", sensorOptions.slice(0, 3).concat([["equal", "No preference"], ["all", "I found all unacceptable"]]))}${text("O2_reason", "Why did you like that approach least?")}
      ${choices("O3", "Which sensor access would you permit?", [["neither", "Neither"], ["microphone", "Microphone only"], ["camera", "Camera only"], ["both", "Both"], ["unsure", "Not sure"]])}
      ${scale("O4a", "I would feel comfortable allowing microphone access for the sensing behavior described.")}${scale("O4b", "I would feel comfortable allowing camera access for the sensing behavior described.")}
      ${choices("O5", "If you permitted both sensors, which activation policy would you prefer?", [["mic_first", "Microphone first, camera only if no bystander voice is detected"], ["camera_first", "Camera first, microphone only if needed (proposed alternative)"], ["simultaneous", "Both at the same time (proposed alternative)"], ["choose", "Let me choose before each reminder"], ["equal", "No preference"], ["neither", "I would not permit both"], ["unsure", "Not sure"]])}${text("O5_reason", "Why do you prefer that activation policy?")}
      <h2>If the visitor stays silent</h2><p>Suppose Sam stayed silent but was visible. The microphone-first approach would detect no bystander voice, close the microphone and scan with the camera. If the camera detected Sam, the watch would ask about aloud disclosure.</p>${scale("O6", "I would prefer this microphone-first/camera-fallback sequence to using the camera for every sensitive reminder.")}
      ${choices("O7", "Would you choose the proposed no-sensor policy, where all sensitive reminders go privately to the watch?", ["Yes", "No", "It depends", "Not sure"])}${text("O7_reason", "Why would you choose or reject the no-sensor policy?")}
      <h2>Should disclosure decisions be remembered?</h2><p>This is a separate preference. <strong>Ask each time</strong> means asking again when a visitor is detected for a sensitive reminder. <strong>Remember</strong> means reusing an explicit Yes or No when that visitor is recognized.</p><p>The current applications use a broad “reminder” key, so an answer can apply to later reminders with different topics. There is no automatic expiry. Face and voice identities are separate, so the same person may prompt again through a different sensor. Recognition can be wrong. These are the wearer’s disclosure decisions, not permission from the visitor.</p>
      ${choices("O8", "Which disclosure policy would you prefer?", [["reask", "Always ask again"], ["no_only", "Remember only No answers (proposed)"], ["remember", "Remember both Yes and No answers"], ["choose", "Let me choose for each answer (proposed)"], ["equal", "No preference"], ["unsure", "Not sure"]])}
      ${choices("O9", "Should a previous Yes ever allow a later sensitive reminder to be spoken without a new question?", ["Yes", "No", "It depends", "Not sure"])}${text("O9_reason", "Why?")}
      ${choices("O10", "If remembering is enabled, when should an answer expire?", ["After that reminder", "At the end of that day", "After one week", "After one month", "Only when I remove it", "A duration I choose", "Never remember answers", "Not sure"])}<p class="helper">Automatic expiry and choosing a duration are proposed controls.</p>
      ${choices("O11", "When should the robot ask again despite a saved answer? Choose all that apply.", ["Different reminder topic or sensitivity", "Different location", "Additional people present", "Uncertain identity match", "A different sensor recognizes the person", "A long time since the last encounter", "I changed or revoked a preference", "Every reminder", "Other", "Not sure"], "checkbox")}
      ${scale("O12", "How important would it be to view, change or delete saved disclosure decisions on the watch?", ["Not at all important", "Slightly important", "Somewhat important", "Moderately important", "Important", "Very important", "Extremely important"])}<p class="helper">Editing saved decisions on the watch is a proposed capability.</p>
      ${text("O13", "What one change would most improve your comfort or trust?")}`;
  }
  function demographics() {
    const frequency = ["Never", "Less than monthly", "Monthly", "Weekly", "Daily"];
    return `<h1 id="page-title">A little about your experience</h1><p>All questions are optional. We ask for broad categories, not identifying information.</p>
      ${select("D1", "Age band", ["18–24", "25–34", "35–44", "45–54", "55–64", "65+"])}
      ${select("D2", "Gender", ["Woman", "Man", "Nonbinary", "Self-describe"])}${text("D2_description", "If you selected self-describe (optional)")}
      ${select("D3", "Highest completed education", ["Secondary school or below", "Vocational qualification", "Bachelor’s degree", "Master’s degree", "Doctorate", "Other"])}
      ${select("D4", "Smartwatch use", ["Never", "Previously, but not currently", "Less than weekly", "Weekly", "Daily"])}
      ${select("D5", "Voice-assistant use", frequency)}${select("D6", "Camera-based identification use, such as face unlock", frequency)}
      ${select("D7", "Interaction with a social robot", ["Never", "Once", "A few times", "Regularly"])}
      ${select("D8", "Familiarity with Ohbot", ["Never heard of it", "Heard of it but not used it", "Used it"])}
      ${select("D9", "Familiarity with Bangle.js", ["Never heard of it", "Heard of it but not used it", "Used it"])}
      ${select("D10", "Technical experience", ["None", "Basic everyday use", "Some programming or electronics", "Extensive programming or electronics"])}`;
  }
  function review() {
    const rated = Object.entries(answers).filter(([k, v]) => /^S[1-7]_Q\d+$/.test(k) && v && !Array.isArray(v)).length;
    return `<h1 id="page-title">Review and finish</h1><p>You have reached the end. You may go Back to review your answers, leave skipped questions blank, or withdraw.</p><p>Your response code is <strong class="code">${esc(session.participant_code)}</strong>. Keep it if the withdrawal procedure uses a code.</p><p>You answered ${rated} story questions. Unanswered questions are recorded as missing, not neutral.</p><h2>Your story ratings</h2><table class="review-table"><thead><tr><th>Story</th><th>Approach</th><th>Acceptability (1–7)</th></tr></thead><tbody>${session.stories.map(s => `<tr><td>${esc(s.topic)}</td><td>${esc(names[s.condition])}</td><td>${esc(answers[`${s.story_id}_Q10`] || "Skipped")}</td></tr>`).join("")}</tbody></table>
      <h2>About these situations</h2><p>The stories are fictional and the pictures are AI-generated. The system descriptions are grounded in a research prototype. Watch-based setup, no-sensor private-only delivery and expiry controls are proposed extensions. These ratings are opinions, not permission to operate a sensor or store a real disclosure preference.</p>
      <h2>${config.submissionEndpoint && !preview ? "Submit your answers" : "Download and return your answers"}</h2><p>${field("returnInstructions")}</p><p>${config.submissionEndpoint && !preview ? "Finish submits your coded answers to the configured research service." : "Finish prepares a response file. Your answers are not sent automatically."}</p><p>After returning or submitting your answers: ${field("withdrawalProcedure")}</p>`;
  }
  function capture() {
    const fields = Array.from(pageNode.querySelectorAll("input[name],select[name],textarea[name]"));
    const keys = new Set(fields.map(f => f.name));
    for (const key of keys) {
      const group = fields.filter(f => f.name === key);
      if (group[0].type === "checkbox") answers[key] = group.filter(f => f.checked).map(f => f.value);
      else if (group[0].type === "radio") answers[key] = (group.find(f => f.checked) || {}).value || null;
      else answers[key] = group[0].value.trim() || null;
    }
  }
  function restore() {
    pageNode.querySelectorAll("input[name],select[name],textarea[name]").forEach(f => {
      const value = answers[f.name];
      if (f.type === "checkbox") f.checked = Array.isArray(value) && value.includes(f.value);
      else if (f.type === "radio") f.checked = value === f.value;
      else f.value = value || "";
    });
  }
  function render() {
    document.getElementById("error").hidden = true;
    const titles = ["Participant information", "Introduction", ...Array.from({length: 6}, (_, i) => `Story ${i + 1} of 6`), "Proposed comparison", "Overall preferences", "Your experience", "Review"];
    document.getElementById("step-label").textContent = titles[page] || "Thank you";
    document.getElementById("step-count").textContent = `Step ${page + 1} of 12`;
    const progress = document.getElementById("progress"); progress.max = 12; progress.value = page;
    pageNode.innerHTML = page === 0 ? info() : page === 1 ? intro() : page <= 7 ? story(session.stories[page - 2]) : page === 8 ? noSensor() : page === 9 ? preferences() : page === 10 ? demographics() : review();
    restore();
    document.getElementById("back").hidden = page === 0;
    const next = document.getElementById("next"); next.textContent = page === 11 ? "Finish" : page === 0 ? "Begin survey" : "Continue";
    next.disabled = page === 0 && !ready && !preview;
    document.getElementById("withdraw").hidden = !session;
    pageNode.focus(); window.scrollTo(0, 0);
  }
  function buildResponse() {
    const checks = {};
    for (const s of session.stories.concat([{story_id: "S7", condition: "N", active_sensors: "neither", watch_response: "NONE"}])) {
      const a = s.story_id;
      checks[a] = {};
      for (const [id, expected] of [["Q13", s.watch_response === "NONE" ? "none" : s.watch_response === "YES" ? "aloud" : "private"], ["Q14", s.active_sensors], ["Q15", s.condition]]) {
        const response = answers[`${a}_${id}`];
        checks[a][id] = {response: response || null, expected, pass: response ? response === expected : null};
      }
    }
    const normalized = {};
    Object.entries(answers).forEach(([k, v]) => { normalized[k] = /^S[1-7]_Q([1-9]|1[012])$/.test(k) || /^(O4[ab]|O6|O12)$/.test(k) ? (v && v !== "NA" ? Number(v) : null) : v; });
    return {schema_version: "2.0", study_id: config.studyId, survey_version: config.version,
      preview, participant_code: session.participant_code, cell_id: session.cell_id,
      allocation_method: session.allocation_method, allocation: session.allocation,
      response_schedule: session.response_schedule, order_id: session.order_id,
      story_order: session.stories.map(s => s.story_id), stories: session.stories,
      duration_seconds: Math.round((Date.now() - started) / 1000),
      completed_at: new Date().toISOString(), consent: answers.C1 === "agree",
      comprehension: checks, answers: normalized,
      missing_response_codes: Object.fromEntries(Object.entries(answers).filter(([, v]) => v === "NA"))};
  }
  function download(content, extension, type) {
    const url = URL.createObjectURL(new Blob([content], {type}));
    const link = document.createElement("a"); link.href = url;
    link.download = `${preview ? "PREVIEW-" : ""}ohbot-response-${session.participant_code}.${extension}`;
    document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function csv() {
    const flat = {};
    function flatten(value, path) {
      if (Array.isArray(value)) flat[path] = JSON.stringify(value);
      else if (value && typeof value === "object") Object.entries(value).forEach(([k, v]) => flatten(v, path ? `${path}.${k}` : k));
      else flat[path] = value;
    }
    flatten(prepared, "");
    function quote(v) { let s = v == null ? "" : String(v); if (/^[\s]*[=+@-]/.test(s)) s = "'" + s; return '"' + s.replace(/"/g, '""') + '"'; }
    return Object.keys(flat).map(quote).join(",") + "\r\n" + Object.values(flat).map(quote).join(",") + "\r\n";
  }
  function finishScreen(message, failed = false) {
    pageNode.innerHTML = `<h1 id="page-title">${failed ? "Submission did not succeed" : "Thank you"}</h1><p>${esc(message)}</p><p>Your code: <strong class="code">${esc(session.participant_code)}</strong></p><p>${field("returnInstructions")}</p><div class="downloads"><button type="button" id="json">Download response file</button><button type="button" id="csv" class="secondary">Download CSV copy</button>${failed ? '<button type="button" id="retry">Retry submission</button>' : ""}</div><p class="helper">The JSON response file preserves the full story assignments. ${preview ? "This is a preview response and must not be included in research data." : "Keep your response code for the stated withdrawal procedure."}</p><p>${field("withdrawalProcedure")}</p>`;
    document.getElementById("navigation").hidden = true;
    document.getElementById("step-label").textContent = "Response ready";
    document.getElementById("step-count").textContent = "";
    document.getElementById("progress").value = 12;
    document.getElementById("json").onclick = () => download(JSON.stringify(prepared, null, 2), "json", "application/json");
    document.getElementById("csv").onclick = () => download(csv(), "csv", "text/csv;charset=utf-8");
    if (failed) document.getElementById("retry").onclick = submit;
    pageNode.focus(); window.scrollTo(0, 0);
  }
  async function submit() {
    if (!prepared) prepared = buildResponse();
    if (!config.submissionEndpoint || preview) {
      completed = true; finishScreen("Your answers have not been sent. Download your response file and return it using the instructions below."); return;
    }
    const button = document.getElementById("retry") || document.getElementById("next");
    button.disabled = true; button.textContent = "Submitting…";
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(config.submissionEndpoint, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(prepared), signal: controller.signal});
      if (!response.ok) throw new Error("Submission failed");
      completed = true; finishScreen("The research collection service confirmed receipt of your coded response. You may download a copy.");
      document.getElementById("withdraw").textContent = "Clear my local copy";
    } catch (_) {
      finishScreen("We could not confirm receipt. Your answers remain in this tab. Retry using the same response code, or download the file and follow the researcher’s backup instructions.", true);
    } finally { clearTimeout(timer); }
  }
  function end(declined = false) {
    session = null; answers = {}; prepared = null; started = null; completed = true;
    pageNode.innerHTML = `<h1 id="page-title">${declined ? "Thank you for considering the study" : "Your local answers have been cleared"}</h1><p>${declined ? "You have not joined the study, and no response was prepared or sent." : "Your answers are no longer held in this tab. This does not delete a file you downloaded or answers already returned or submitted; use the researcher’s withdrawal procedure for those."}</p>`;
    document.getElementById("navigation").hidden = true; document.getElementById("withdraw").hidden = true; pageNode.focus();
  }
  form.addEventListener("submit", async event => {
    event.preventDefault(); capture();
    if (page === 0) {
      if (!answers.C1) { document.getElementById("error").textContent = "Please choose whether you agree to participate."; document.getElementById("error").hidden = false; return; }
      if (answers.C1 === "decline") { end(true); return; }
      if (!ready && !preview) return;
      const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
      session = {...assignment(params.get("cell")), participant_code: "P-" + Array.from({length: 12}, () => alphabet[random(alphabet.length)]).join("")};
      started = Date.now();
    }
    if (page === 11) { await submit(); return; }
    page += 1; render();
  });
  document.getElementById("back").onclick = () => { capture(); page -= 1; render(); };
  document.getElementById("withdraw").onclick = () => {
    if (window.confirm("Clear the answers held in this tab? Files already downloaded or responses already returned are not deleted.")) end();
  };
  pageNode.addEventListener("change", event => {
    if (event.target.name !== "O11") return;
    const fields = Array.from(pageNode.querySelectorAll('input[name="O11"]'));
    if (["Every reminder", "Not sure"].includes(event.target.value) && event.target.checked) fields.forEach(f => { if (f !== event.target) f.checked = false; });
    else if (event.target.checked) fields.forEach(f => { if (["Every reminder", "Not sure"].includes(f.value)) f.checked = false; });
  });
  window.addEventListener("beforeunload", event => { if (session && !completed) { event.preventDefault(); event.returnValue = ""; } });
  const setup = document.getElementById("setup");
  if (preview || !ready) {
    setup.hidden = false;
    setup.innerHTML = preview ? `<strong>Researcher preview.</strong> This is a functioning preview, not a recruitment link. Preview exports are labeled and no endpoint receives them. ${!ready ? "Institutional study information is still incomplete." : ""}` : `<strong>Participant enrollment is not open yet.</strong> The researcher must supply the study information before inviting participants. <a href="?preview=1">Open the researcher preview</a>.`;
  }
  if (materials) {
    session = assignment(params.get("cell") || "L1-A-W1");
    document.body.classList.add("materials");
    ["navigation", "withdraw", "setup", "progress"].forEach(id => document.getElementById(id).hidden = true);
    document.querySelector(".progress-row").hidden = true;
    const parts = [intro(), ...session.stories.map(story), noSensor(), preferences(), demographics(),
      '<h1>Thank you</h1><p>The stories are fictional and the pictures are AI-generated. Your answers express opinions about the described research prototype and proposed features.</p>'];
    pageNode.innerHTML = '<p class="helper">Please complete the participant information and consent supplied separately by the researcher before answering. Choose one option per question unless indicated otherwise. All opinion and experience questions are optional.</p>' + parts.map((html, i) => '<section class="material-section">' + html.replace(/id="page-title"/g, 'id="material-title-' + i + '"') + '</section>').join('');
  } else render();
}());
