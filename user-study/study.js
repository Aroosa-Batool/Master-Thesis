(function () {
  "use strict";

  const CONFIG = window.STUDY_CONFIG || {};
  const STORAGE_KEY = "sensor-comfort-study-session-v1";
  const startTime = Date.now();
  let preparedResponse = null;

  const CONDITIONS = {
    microphone: {
      title: "Microphone only",
      image: "assets/condition-microphone-only.png",
      alt: "Illustration of a desktop robot with its microphone light on and camera shutter closed",
      summary: "The microphone listens during the reminder lead window for a non-owner voice. The camera remains physically closed.",
      facts: ["Microphone active", "Camera closed", "Raw audio not retained"],
      manipulation: "microphone"
    },
    camera: {
      title: "Camera only",
      image: "assets/condition-camera-only.png",
      alt: "Illustration of a desktop robot with its camera open and microphone light off",
      summary: "The camera briefly scans for nearby faces around the reminder time. The microphone remains closed.",
      facts: ["Camera active", "Microphone closed", "Raw video not retained"],
      manipulation: "camera"
    },
    sequential: {
      title: "Microphone, then camera if needed",
      image: "assets/condition-mic-then-camera.png",
      alt: "Two-stage illustration showing a robot using its microphone first and camera second",
      summary: "The microphone listens first. Only if it hears no non-owner voice does the camera briefly check for a silent bystander. The sensors are never open at the same time.",
      facts: ["Microphone first", "Camera only if needed", "Never simultaneous"],
      manipulation: "sequential"
    }
  };

  const ITEMS = [
    ["COM1", "I would feel comfortable with this sensing approach in my home or workspace."],
    ["PRV1", "I would be concerned about my privacy when this approach is used."],
    ["CTL1", "I would feel in control of when sensing occurs."],
    ["TRN1", "It would be clear to me which sensor is active."],
    ["TRU1", "I would trust the robot to handle sensitive reminders appropriately."],
    ["ACC1", "This approach is acceptable for detecting whether another person is present."],
    ["INT1", "I would be willing to use this sensing approach."],
    ["BYS1", "I think visitors or bystanders would feel comfortable with this approach."],
    ["BEN1", "The privacy benefit of this approach would justify its use of sensors."]
  ];

  function escapeHtml(value) {
    return String(value).replace(/[&<>'"]/g, function (character) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;" }[character];
    });
  }

  function randomIndex(max) {
    if (window.crypto && window.crypto.getRandomValues) {
      const value = new Uint32Array(1);
      window.crypto.getRandomValues(value);
      return value[0] % max;
    }
    return Math.floor(Math.random() * max);
  }

  function shuffled(values) {
    const result = values.slice();
    for (let index = result.length - 1; index > 0; index -= 1) {
      const swapIndex = randomIndex(index + 1);
      [result[index], result[swapIndex]] = [result[swapIndex], result[index]];
    }
    return result;
  }

  function createParticipantCode() {
    const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    let code = "P-";
    for (let index = 0; index < 8; index += 1) code += alphabet[randomIndex(alphabet.length)];
    return code;
  }

  function getSession() {
    try {
      const existing = JSON.parse(sessionStorage.getItem(STORAGE_KEY));
      if (existing && existing.participantCode && Array.isArray(existing.order)) return existing;
    } catch (error) {
      // A blocked storage API should not prevent participation.
    }
    const session = {
      participantCode: createParticipantCode(),
      order: shuffled(Object.keys(CONDITIONS))
    };
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session)); } catch (error) { /* no-op */ }
    return session;
  }

  function likertCells(conditionId, itemCode) {
    return Array.from({ length: 7 }, function (_, index) {
      const value = index + 1;
      const anchor = value === 1 ? "Strongly disagree" : value === 7 ? "Strongly agree" : String(value);
      return `<td><label title="${anchor}"><span class="sr-only">${escapeHtml(anchor)}</span><input type="radio" name="${conditionId}_${itemCode}" value="${value}" required aria-label="${value}: ${escapeHtml(anchor)}"></label></td>`;
    }).join("");
  }

  function conditionHtml(conditionId, position) {
    const condition = CONDITIONS[conditionId];
    const rows = ITEMS.map(function (item) {
      return `<tr><th scope="row">${escapeHtml(item[1])}</th>${likertCells(conditionId, item[0])}</tr>`;
    }).join("");
    const facts = condition.facts.map(function (fact) { return `<span class="fact">${escapeHtml(fact)}</span>`; }).join("");

    return `
      <article class="card condition-card" data-condition="${conditionId}">
        <figure class="condition-image">
          <img src="${condition.image}" alt="${escapeHtml(condition.alt)}" width="1448" height="1086" ${position === 1 ? "" : "loading=\"lazy\""}>
          <figcaption>Illustrated scenario</figcaption>
        </figure>
        <div class="condition-content">
          <p class="condition-index">Condition ${position} of 3</p>
          <h3>${escapeHtml(condition.title)}</h3>
          <p class="condition-summary">${escapeHtml(condition.summary)}</p>
          <div class="facts">${facts}</div>

          <p class="question-label">For each statement, select one answer from 1 (strongly disagree) to 7 (strongly agree).</p>
          <div class="matrix-wrap">
            <table class="matrix">
              <thead><tr><th scope="col">Statement</th><th scope="col">1<br>Strongly<br>disagree</th><th scope="col">2</th><th scope="col">3</th><th scope="col">4<br>Neither</th><th scope="col">5</th><th scope="col">6</th><th scope="col">7<br>Strongly<br>agree</th></tr></thead>
              <tbody>${rows}</tbody>
            </table>
          </div>

          <div class="question-block">
            <label for="${conditionId}-check"><span class="question-label">Which sensing sequence did this condition describe? <span aria-hidden="true">*</span></span></label>
            <select id="${conditionId}-check" name="${conditionId}_manipulation_check" required>
              <option value="">Select one</option>
              <option value="microphone">Microphone only</option>
              <option value="camera">Camera only</option>
              <option value="sequential">Microphone first, then camera only if needed</option>
              <option value="simultaneous">Microphone and camera at the same time</option>
              <option value="unsure">Unsure</option>
            </select>
          </div>

          <div class="question-block">
            <label for="${conditionId}-comment"><span class="question-label">What, if anything, felt reassuring or concerning about this approach?</span></label>
            <textarea id="${conditionId}-comment" name="${conditionId}_comment" maxlength="1000" rows="3" placeholder="Optional. Please do not include names or sensitive personal details."></textarea>
          </div>
        </div>
      </article>`;
  }

  function renderScale(groupName) {
    const target = document.querySelector(`[data-radio-group="${groupName}"]`);
    if (!target) return;
    target.innerHTML = Array.from({ length: 7 }, function (_, index) {
      const value = index + 1;
      return `<label><span>${value}</span><input type="radio" name="${groupName}" value="${value}" required aria-label="${value}"></label>`;
    }).join("");
  }

  function populateConfig() {
    document.querySelectorAll("[data-config]").forEach(function (element) {
      const key = element.dataset.config;
      if (CONFIG[key] !== undefined) element.textContent = CONFIG[key];
    });
    if (CONFIG.title) document.title = `${CONFIG.title} · User Study`;

    const requiredFields = ["institution", "researcher", "contact", "supervisor", "ethicsReference"];
    const unresolved = requiredFields.some(function (key) {
      return !CONFIG[key] || /^\[REPLACE:/i.test(String(CONFIG[key]));
    });
    document.getElementById("setup-warning").hidden = !unresolved;

    const endpoint = String(CONFIG.submissionEndpoint || "").trim();
    if (endpoint) {
      document.getElementById("collection-description").textContent = "After you select submit, the coded answers are sent to the researcher-configured collection endpoint. The researcher must accurately disclose any technical logs or identifiers collected by that service.";
      document.getElementById("submit-explanation").textContent = "Selecting the button below validates the required answers and submits the coded response to the configured research endpoint.";
      document.getElementById("submit-button").textContent = "Submit coded response";
    }
  }

  function requiredCompletion() {
    const required = Array.from(document.querySelectorAll("#study-form [required]"));
    const groups = new Map();
    required.forEach(function (field) {
      const key = field.type === "radio" ? `radio:${field.name}` : `field:${field.name || field.id}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(field);
    });
    let completed = 0;
    groups.forEach(function (fields) {
      const first = fields[0];
      if (first.type === "radio") {
        if (fields.some(function (field) { return field.checked; })) completed += 1;
      } else if (first.type === "checkbox") {
        if (first.checked) completed += 1;
      } else if (String(first.value).trim()) completed += 1;
    });
    return { completed: completed, total: groups.size };
  }

  function updateProgress() {
    const completion = requiredCompletion();
    const percentage = completion.total ? Math.round((completion.completed / completion.total) * 100) : 0;
    const progress = document.getElementById("progress");
    progress.value = percentage;
    progress.textContent = `${percentage}%`;
    document.getElementById("progress-label").textContent = `${percentage}% complete`;
  }

  function formAnswers(form) {
    const answers = {};
    new FormData(form).forEach(function (value, key) {
      answers[key] = value;
    });
    form.querySelectorAll('input[type="checkbox"][name]').forEach(function (checkbox) {
      answers[checkbox.name] = checkbox.checked;
    });
    return answers;
  }

  function buildResponse(form, session) {
    const answers = formAnswers(form);
    const manipulationChecks = {};
    Object.keys(CONDITIONS).forEach(function (conditionId) {
      manipulationChecks[conditionId] = answers[`${conditionId}_manipulation_check`] === CONDITIONS[conditionId].manipulation;
    });

    return {
      schema_version: "1.0",
      study_id: CONFIG.studyId || "sensor-comfort-v1",
      participant_code: session.participantCode,
      condition_order: session.order,
      duration_seconds: Math.max(1, Math.round((Date.now() - startTime) / 1000)),
      illustration_disclosure: "AI-generated standardized vignettes; not actual sensor recordings",
      manipulation_check_pass: manipulationChecks,
      answers: answers
    };
  }

  function flatten(value, prefix, output) {
    if (Array.isArray(value)) {
      output[prefix] = value.join("|");
    } else if (value && typeof value === "object") {
      Object.keys(value).forEach(function (key) {
        flatten(value[key], prefix ? `${prefix}.${key}` : key, output);
      });
    } else {
      output[prefix] = value;
    }
    return output;
  }

  function csvValue(value) {
    const text = value === undefined || value === null ? "" : String(value);
    return `"${text.replace(/"/g, '""')}"`;
  }

  function download(contents, mimeType, extension, participantCode) {
    const prefix = CONFIG.responseFilePrefix || "sensor-study-response";
    const blob = new Blob([contents], { type: mimeType });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${prefix}-${participantCode}.${extension}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
  }

  async function handleSubmit(event, session) {
    event.preventDefault();
    const form = event.currentTarget;
    const error = document.getElementById("form-error");
    if (!form.reportValidity()) {
      error.hidden = false;
      const firstInvalid = form.querySelector(":invalid");
      if (firstInvalid) firstInvalid.focus();
      return;
    }
    error.hidden = true;
    preparedResponse = buildResponse(form, session);

    const endpoint = String(CONFIG.submissionEndpoint || "").trim();
    const completionMessage = document.getElementById("completion-message");
    if (endpoint) {
      const submitButton = document.getElementById("submit-button");
      submitButton.disabled = true;
      submitButton.textContent = "Submitting…";
      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(preparedResponse)
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        completionMessage.textContent = "Your coded response was submitted. You may also download a copy for your records.";
      } catch (submissionError) {
        completionMessage.textContent = "Automatic submission did not succeed. Your answers remain in this browser; download a response file and return it using the researcher's approved backup method.";
      } finally {
        submitButton.disabled = false;
        submitButton.textContent = "Submit coded response";
      }
    }

    const completion = document.getElementById("completion");
    completion.hidden = false;
    completion.focus();
    completion.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function initialize() {
    populateConfig();
    const session = getSession();
    document.getElementById("participant-code").textContent = session.participantCode;
    document.getElementById("condition-list").innerHTML = session.order.map(function (conditionId, index) {
      return conditionHtml(conditionId, index + 1);
    }).join("");
    renderScale("status_light_helpful");

    const form = document.getElementById("study-form");
    form.addEventListener("input", updateProgress);
    form.addEventListener("change", updateProgress);
    form.addEventListener("submit", function (event) { handleSubmit(event, session); });

    document.getElementById("download-json").addEventListener("click", function () {
      if (!preparedResponse) return;
      download(JSON.stringify(preparedResponse, null, 2), "application/json", "json", preparedResponse.participant_code);
    });
    document.getElementById("download-csv").addEventListener("click", function () {
      if (!preparedResponse) return;
      const row = flatten(preparedResponse, "", {});
      const headers = Object.keys(row);
      const csv = `${headers.map(csvValue).join(",")}\n${headers.map(function (key) { return csvValue(row[key]); }).join(",")}\n`;
      download(csv, "text/csv;charset=utf-8", "csv", preparedResponse.participant_code);
    });
    document.getElementById("print-response").addEventListener("click", function () { window.print(); });
    document.getElementById("reset-button").addEventListener("click", function () {
      if (!window.confirm("Clear every answer in this form and create a new participant session?")) return;
      try { sessionStorage.removeItem(STORAGE_KEY); } catch (error) { /* no-op */ }
      window.location.reload();
    });
    updateProgress();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize);
  } else {
    initialize();
  }
}());
