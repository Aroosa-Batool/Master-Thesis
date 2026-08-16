"use strict";

const byId = (id) => document.getElementById(id);
let currentState = null;
let scenarioData = {};
let algorithmData = { catalog: [], datasets: [] };
let evaluationData = null;
let presentationMode = "guided";
let lastFrameVersion = -1;
let lastDraftKey = "";
let lastJobSignature = "";
let noticeTimer = null;

async function request(path, options = {}) {
  const config = { ...options };
  if (config.body && typeof config.body !== "string") {
    config.body = JSON.stringify(config.body);
    config.headers = { "Content-Type": "application/json", ...(config.headers || {}) };
  }
  const response = await fetch(path, config);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) throw new Error(payload?.error || `${response.status} ${response.statusText}`);
  return payload;
}

function showNotice(message, isError = false) {
  const notice = byId("notice");
  notice.textContent = message;
  notice.classList.remove("hidden", "error");
  if (isError) notice.classList.add("error");
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => notice.classList.add("hidden"), isError ? 9000 : 4500);
}

async function post(path, body = {}) {
  try {
    const payload = await request(path, { method: "POST", body });
    const state = payload?.state || (payload?.steps ? payload : null);
    if (state) renderState(state);
    return payload;
  } catch (error) {
    showNotice(error.message, true);
    throw error;
  }
}

function setPresentationMode(mode) {
  presentationMode = mode;
  byId("mode-guided").classList.toggle("active", mode === "guided");
  byId("mode-live").classList.toggle("active", mode === "live");
  byId("guided-controls").classList.toggle("hidden", mode !== "guided");
  byId("live-controls").classList.toggle("hidden", mode !== "live");
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === name));
  document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.id === `tab-${name}`));
  if (name === "algorithms") loadAlgorithms();
  if (name === "evaluation") loadEvaluation();
}

function renderWorkflow(steps) {
  const root = byId("workflow");
  root.replaceChildren();
  let completed = 0;
  steps.forEach((step, index) => {
    if (!["pending", "active"].includes(step.status)) completed += 1;
    const card = document.createElement("article");
    card.className = `workflow-step ${step.status}`;
    card.dataset.number = String(index + 1);
    const eyebrow = document.createElement("p");
    eyebrow.className = "eyebrow";
    eyebrow.textContent = step.eyebrow;
    const title = document.createElement("h3");
    title.textContent = step.title;
    const detail = document.createElement("p");
    detail.textContent = step.detail;
    card.append(eyebrow, title, detail);
    root.append(card);
  });
  byId("step-counter").textContent = `${completed} / ${steps.length}`;
}

function renderEvents(events) {
  const root = byId("event-log");
  root.replaceChildren();
  if (!events.length) {
    root.textContent = "No events yet.";
    return;
  }
  events.slice(-120).forEach((event) => {
    const row = document.createElement("div");
    row.className = `event ${event.tone || "info"}`;
    const at = document.createElement("span"); at.className = "time"; at.textContent = event.at;
    const source = document.createElement("span"); source.className = "source"; source.textContent = event.source;
    const message = document.createElement("span"); message.textContent = event.message;
    row.append(at, source, message);
    root.append(row);
  });
  root.scrollTop = root.scrollHeight;
}

function renderSensors(state) {
  const micOn = Boolean(state.sensors?.microphone);
  const cameraOn = Boolean(state.sensors?.camera);
  byId("microphone-card").classList.toggle("on", micOn);
  byId("microphone-card").classList.toggle("off", !micOn);
  byId("microphone-state").textContent = micOn ? "Active · listening" : "Closed";
  byId("microphone-detail").textContent = micOn
    ? `Temporary window · ${Math.max(0, Number(state.metrics?.microphone_level_remaining_s || 0)).toFixed(0)}s remaining`
    : "No audio is being captured.";
  const level = Math.min(100, Math.max(0, Number(state.metrics?.microphone_level || 0) / 0.05 * 100));
  byId("microphone-meter").style.width = `${level}%`;

  byId("camera-card").classList.toggle("on", cameraOn);
  byId("camera-card").classList.toggle("off", !cameraOn);
  byId("camera-state").textContent = cameraOn ? "Active · robot point of view" : "Closed";
  const hasFrame = cameraOn && state.frame_available;
  byId("camera-frame").classList.toggle("hidden", !hasFrame);
  byId("camera-shutter").classList.toggle("hidden", hasFrame);
  if (hasFrame && state.frame_version !== lastFrameVersion) {
    lastFrameVersion = state.frame_version;
    byId("camera-frame").src = `/api/frame?v=${state.frame_version}`;
  }
  byId("head-position").textContent = `Head: ${state.metrics?.head_position || "centred · 5/10"}`;

  const ownerStep = state.steps?.find((step) => step.id === "owner");
  byId("watch-state").textContent = ownerStep?.status === "complete"
    ? "Watch connected · owner present"
    : ownerStep?.status === "warning" ? "Watch offline · reminder held" : "Watch checked during live run";
  const identity = state.identity;
  byId("identity-state").textContent = identity
    ? `${identity.modality === "face" ? "Seen" : "Heard"}: ${identity.id}${identity.similarity != null ? ` · cosine ${Number(identity.similarity).toFixed(2)}` : ""}`
    : "No bystander identity resolved.";
}

function renderReadiness(readiness) {
  const root = byId("readiness-grid");
  root.replaceChildren();
  const order = ["python", "microphone", "camera", "watch", "ohbot", "voice", "face", "models", "reminders"];
  order.forEach((key) => {
    const item = readiness?.[key];
    if (!item) return;
    const card = document.createElement("article");
    card.className = `readiness-item ${item.ready === true ? "ready" : item.ready === false ? "missing" : "unknown"}`;
    const title = document.createElement("strong"); title.textContent = `${item.ready === true ? "✓" : item.ready === false ? "!" : "?"} ${item.label}`;
    const detail = document.createElement("p"); detail.textContent = item.detail;
    card.append(title, detail); root.append(card);
  });

}

function secondsUntil(reminder) {
  const parsed = Date.parse(reminder?.remind_at || "");
  if (Number.isFinite(parsed)) return (parsed - Date.now()) / 1000;
  const reported = Number(reminder?.seconds_until);
  return Number.isFinite(reported) ? reported : null;
}

function formatCountdown(seconds) {
  if (seconds === null) return "—";
  if (seconds <= 0) return "due now";
  const whole = Math.floor(seconds);
  const parts = [Math.floor(whole / 3600), Math.floor((whole % 3600) / 60), whole % 60];
  const pad = (value) => String(value).padStart(2, "0");
  return parts[0] ? `${parts[0]}:${pad(parts[1])}:${pad(parts[2])}` : `${parts[1]}:${pad(parts[2])}`;
}

// The operator never picks a reminder: the console shows the next approaching
// pending one (undelivered leftovers stepped over) and counts down to it. During
// a live run the pinned target from the server wins, so the panel cannot drift
// to a different reminder halfway through.
function renderNextReminder(state) {
  const running = state.mode === "live" && state.process_running;
  const pinned = running ? state.config?.reminder : null;
  const reminder = pinned || state.readiness?.next_reminder || null;
  const remaining = reminder ? secondsUntil(reminder) : null;
  const panel = byId("next-reminder");
  panel.classList.toggle("empty", !reminder);
  panel.classList.toggle("imminent", Boolean(reminder) && remaining !== null && remaining <= 120);
  byId("next-reminder-text").textContent = reminder ? reminder.text : "No pending reminder";
  byId("next-reminder-countdown").textContent = reminder ? formatCountdown(remaining) : "—";
  if (!reminder) {
    byId("next-reminder-meta").textContent = "Add one in the Reminders tab; the console follows the queue automatically.";
  } else {
    const flag = reminder.sensitive === true ? "sensitive · presence gated"
      : reminder.sensitive === false ? "everyday · spoken normally" : "unclassified";
    const upcoming = Number(state.readiness?.upcoming_count || 0);
    const overdue = Number(state.readiness?.overdue_count || 0);
    const queue = pinned ? "running" : [
      upcoming > 1 ? `${upcoming - 1} more queued` : null,
      overdue ? `${overdue} overdue ignored` : null,
    ].filter(Boolean).join(" · ");
    byId("next-reminder-meta").textContent =
      `${reminder.id} · due ${String(reminder.remind_at).slice(11, 19)} · ${flag}`
      + (queue ? ` · ${queue}` : "");
  }
  byId("live-start").disabled = !reminder || running;
}

function renderJob(job) {
  const kind = job?.kind;
  byId("job-title").textContent = kind ? kind.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "No setup task running";
  byId("job-meter").style.width = `${Math.max(0, Math.min(1, Number(job?.progress || 0))) * 100}%`;
  byId("job-result").textContent = typeof job?.result === "string" ? job.result : (job?.status === "running" ? "Task is running…" : "Choose a test, enrollment, capture, or benchmark.");
  const running = ["running", "starting", "stopping"].includes(job?.status);
  byId("job-stop").disabled = !running;
  byId("eval-face-capture").disabled = !(running && kind === "eval_face");
}

function applyDraft(draft) {
  if (!draft?.text || !draft?.remind_at) return;
  const key = JSON.stringify(draft);
  if (key === lastDraftKey) return;
  lastDraftKey = key;
  byId("reminder-text").value = draft.text;
  byId("reminder-time").value = draft.remind_at.slice(0, 19);
  byId("reminder-sensitive").value = String(Boolean(draft.sensitive));
  byId("classifier-reason").textContent = `${draft.backend || "Classifier"}: ${draft.reason || "No explanation available"}`;
  showNotice("Voice reminder draft is ready. Review it, then press Save reminder.");
}

function renderState(state) {
  const previousJob = currentState?.job;
  currentState = state;
  byId("global-status").textContent = state.status === "running" ? "Running" : state.status === "error" ? "Needs attention" : state.status === "complete" ? "Complete" : "Ready";
  byId("global-status").className = `status-pill ${state.status}`;
  byId("headline").textContent = state.headline;
  byId("outcome").textContent = state.outcome || "No delivery outcome yet.";
  renderWorkflow(state.steps || []);
  renderSensors(state);
  renderEvents(state.events || []);
  renderReadiness(state.readiness || {});
  renderNextReminder(state);
  renderJob(state.job || {});
  applyDraft(state.reminder_draft);
  byId("guided-next").disabled = state.mode === "demo" && !state.demo?.has_next;
  byId("guided-previous").disabled = state.mode !== "demo" || Number(state.demo?.cursor || 0) <= 0;

  const signature = `${state.job?.kind}:${state.job?.status}`;
  if (signature !== lastJobSignature && state.job?.status === "complete") {
    if (String(state.job.kind).startsWith("benchmark")) loadAlgorithms();
    if (String(state.job.kind).startsWith("eval")) loadEvaluation();
  }
  lastJobSignature = signature;
  if (previousJob?.status === "running" && state.job?.status === "error") showNotice("The active task failed. Open the evidence log for details.", true);
}

async function pollState() {
  try {
    const state = await request("/api/state");
    renderState(state);
  } catch (error) {
    byId("global-status").textContent = "Server unavailable";
    byId("global-status").className = "status-pill error";
  }
}

async function loadScenarios() {
  const payload = await request("/api/scenarios");
  scenarioData = payload.scenarios;
  const select = byId("scenario-select");
  select.replaceChildren();
  Object.entries(scenarioData).forEach(([id, scenario]) => select.add(new Option(`${scenario.title} — ${scenario.short}`, id)));
  select.dispatchEvent(new Event("change"));
}

function renderAlgorithmCatalog(catalog) {
  const root = byId("algorithm-catalog"); root.replaceChildren();
  catalog.forEach((item) => {
    const card = document.createElement("article"); card.className = "algorithm-card";
    const label = document.createElement("p"); label.className = "eyebrow"; label.textContent = `${item.modality} · ${item.stage}`;
    const title = document.createElement("h3"); title.textContent = item.name;
    const role = document.createElement("p"); role.textContent = item.role;
    const meta = document.createElement("p"); meta.className = "meta";
    meta.textContent = item.threshold || `${item.embedding_dim}-D embedding`;
    card.append(label, title, role, meta); root.append(card);
  });
}

function renderBenchmarkResults() {
  const select = byId("result-dataset");
  const previous = select.value;
  select.replaceChildren();
  algorithmData.datasets.forEach((dataset) => select.add(new Option(`${dataset.source} · ${dataset.modality}`, dataset.id)));
  if ([...select.options].some((option) => option.value === previous)) select.value = previous;
  const dataset = algorithmData.datasets.find((item) => item.id === select.value) || algorithmData.datasets[0];
  const rows = dataset?.rows || [];
  const metric = byId("result-metric").value;
  const metricNumber = (value) => value == null || value === "" ? null : Number(value);
  const values = rows.map((row) => metricNumber(row[metric])).filter((value) => value !== null && Number.isFinite(value));
  const max = Math.max(...values, 1);
  const chart = byId("benchmark-chart"); chart.replaceChildren();
  if (!rows.length) chart.textContent = "No benchmark results are available yet.";
  rows.forEach((row) => {
    const value = metricNumber(row[metric]);
    if (value === null || !Number.isFinite(value)) return;
    const line = document.createElement("div"); line.className = "chart-row";
    const name = document.createElement("strong"); name.textContent = row.name;
    const track = document.createElement("div"); track.className = "bar-track";
    const bar = document.createElement("div"); bar.className = "bar"; bar.style.width = `${Math.max(1, value / max * 100)}%`; track.append(bar);
    const number = document.createElement("span"); number.textContent = value.toFixed(value < 1 ? 3 : 1);
    line.append(name, track, number); chart.append(line);
  });
  const table = byId("benchmark-table"); table.replaceChildren();
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    const cells = [row.name, row.stage, row.lat_median_ms, row.lat_p95_ms, row.fps, row.peak_rss_mb, row.model_size_mb, row.embedding_dim, row.accuracy_label || row.accuracy || "—", row.ok ? "OK" : row.error || "Failed"];
    cells.forEach((value) => { const td = document.createElement("td"); td.textContent = value == null || value === "" ? "—" : (typeof value === "number" ? value.toFixed(2) : String(value)); tr.append(td); });
    table.append(tr);
  });
}

async function loadAlgorithms() {
  try {
    algorithmData = await request("/api/algorithms");
    renderAlgorithmCatalog(algorithmData.catalog || []);
    renderBenchmarkResults();
  } catch (error) { showNotice(error.message, true); }
}

function renderEvaluation(data) {
  evaluationData = data;
  const coverage = data.coverage || {};
  byId("coverage-summary").textContent = `${coverage.people || 0} participant label(s) · ${coverage.conditions || 0} condition(s)${coverage.minimum_samples_met ? " · sample minimum met" : ""}`;
  const root = byId("coverage-grid"); root.replaceChildren();
  [["Face", data.faces || {}], ["Voice", data.voices || {}]].forEach(([modality, people]) => {
    Object.entries(people).forEach(([name, info]) => {
      const item = document.createElement("div"); item.className = "coverage-item";
      const title = document.createElement("strong"); title.textContent = `${modality} · ${name}`;
      const samples = document.createElement("p"); samples.textContent = `${info.samples} sample(s)`;
      const conditions = document.createElement("p"); conditions.textContent = `Conditions: ${info.conditions.join(", ") || "none"}`;
      item.append(title, samples, conditions); root.append(item);
    });
  });
  if (!root.children.length) root.textContent = "No labelled evaluation samples have been captured yet.";
}

async function loadEvaluation() {
  try { renderEvaluation(await request("/api/evaluation")); }
  catch (error) { showNotice(error.message, true); }
}

function localDateTime(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

// No reminder is chosen here: the server pins the run to the same next-pending
// reminder the countdown is showing.
async function startLive() {
  if (!currentState) return;
  const target = currentState.readiness?.next_reminder;
  if (!target) { showNotice("Add a pending reminder before starting a live run.", true); return; }
  const preset = byId("timing-preset").value;
  const lead = preset === "research" ? 420 : preset === "quick" ? 90 : Number(byId("custom-lead").value);
  const listen = preset === "research" ? 300 : preset === "quick" ? 45 : Number(byId("custom-listen").value);
  await post("/api/live/start", {
    policy: byId("live-policy").value,
    sensors: byId("live-sensors").value,
    monitor_lead: lead,
    listen_duration: listen,
    laptop_voice: byId("laptop-voice").checked,
  });
  showNotice(`Live run following ${target.id} (${target.text}).`);
}

async function startJob(kind, options = {}) {
  await post("/api/jobs/start", { kind, ...options });
  showNotice(`${kind.replaceAll("_", " ")} started.`);
}

function bindEvents() {
  document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => switchTab(button.dataset.tab)));
  byId("mode-guided").addEventListener("click", () => setPresentationMode("guided"));
  byId("mode-live").addEventListener("click", () => setPresentationMode("live"));
  byId("scenario-select").addEventListener("change", () => {
    const scenario = scenarioData[byId("scenario-select").value];
    if (!scenario) return;
    byId("guided-policy").value = scenario.recommended_policy;
    byId("guided-sensors").value = scenario.recommended_sensors;
  });
  byId("guided-start").addEventListener("click", () => post("/api/demo/start", { scenario: byId("scenario-select").value, policy: byId("guided-policy").value, sensors: byId("guided-sensors").value }));
  byId("guided-next").addEventListener("click", () => post("/api/demo/next"));
  byId("guided-previous").addEventListener("click", () => post("/api/demo/previous"));
  byId("guided-restart").addEventListener("click", () => post("/api/demo/start", { scenario: byId("scenario-select").value, policy: byId("guided-policy").value, sensors: byId("guided-sensors").value }));
  byId("timing-preset").addEventListener("change", () => byId("custom-timing").classList.toggle("hidden", byId("timing-preset").value !== "custom"));
  byId("live-start").addEventListener("click", () => startLive().catch(() => {}));
  byId("live-stop").addEventListener("click", () => post("/api/live/stop"));
  byId("fullscreen-button").addEventListener("click", async () => { if (!document.fullscreenElement) await document.documentElement.requestFullscreen(); else await document.exitFullscreen(); });
  document.addEventListener("keydown", (event) => {
    if (presentationMode !== "guided" || !byId("tab-presentation").classList.contains("active") || ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
    if (event.key === "ArrowRight") post("/api/demo/next");
    if (event.key === "ArrowLeft") post("/api/demo/previous");
  });

  byId("refresh-readiness").addEventListener("click", pollState);
  document.querySelectorAll(".job-button").forEach((button) => button.addEventListener("click", () => startJob(button.dataset.kind).catch(() => {})));
  byId("enroll-voice").addEventListener("click", () => startJob("voice_enrollment", { overwrite: byId("overwrite-enrollment").checked }).catch(() => {}));
  byId("enroll-face").addEventListener("click", () => startJob("face_enrollment", { overwrite: byId("overwrite-enrollment").checked }).catch(() => {}));
  byId("job-stop").addEventListener("click", () => post("/api/jobs/stop"));
  byId("record-reminder").addEventListener("click", () => startJob("voice_reminder", { seconds: Number(byId("voice-seconds").value), model: byId("whisper-model").value }).catch(() => {}));
  byId("reminder-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = await post("/api/reminders/save", { text: byId("reminder-text").value, remind_at: byId("reminder-time").value, sensitive: byId("reminder-sensitive").value === "true" });
    showNotice(`Reminder ${payload.reminder.id} saved.`);
    byId("reminder-text").value = "";
  });

  byId("refresh-algorithms").addEventListener("click", loadAlgorithms);
  byId("result-dataset").addEventListener("change", renderBenchmarkResults);
  byId("result-metric").addEventListener("change", renderBenchmarkResults);
  byId("benchmark-modality").addEventListener("change", () => {
    const camera = byId("benchmark-modality").value === "camera";
    byId("resolution-field").classList.toggle("hidden", !camera);
    byId("benchmark-candidates").value = camera ? "yunet,sface" : "silero,resemblyzer";
    byId("benchmark-repeats").value = camera ? "50" : "200";
    byId("benchmark-timeout").value = camera ? "900" : "600";
  });
  byId("benchmark-start").addEventListener("click", () => {
    const modality = byId("benchmark-modality").value;
    startJob(`benchmark_${modality}`, { candidates: byId("benchmark-candidates").value, repeats: Number(byId("benchmark-repeats").value), timeout: Number(byId("benchmark-timeout").value), resolution: byId("benchmark-resolution").value, use_eval_data: byId("benchmark-eval").checked }).catch(() => {});
  });

  byId("refresh-evaluation").addEventListener("click", loadEvaluation);
  byId("eval-face-negative").addEventListener("change", () => { byId("eval-face-label").disabled = byId("eval-face-negative").checked; });
  byId("eval-face-start").addEventListener("click", () => startJob("eval_face", { label: byId("eval-face-label").value, condition: byId("eval-face-condition").value, shots: Number(byId("eval-face-count").value), negative: byId("eval-face-negative").checked }).catch(() => {}));
  byId("eval-face-capture").addEventListener("click", () => post("/api/jobs/action", { action: "capture" }));
  byId("eval-voice-start").addEventListener("click", () => startJob("eval_voice", { label: byId("eval-voice-label").value, condition: byId("eval-voice-condition").value, clips: Number(byId("eval-voice-count").value), seconds: Number(byId("eval-voice-seconds").value) }).catch(() => {}));
}

async function init() {
  bindEvents();
  byId("reminder-time").value = localDateTime(new Date(Date.now() + 10 * 60000));
  byId("eval-face-capture").disabled = true;
  try {
    await Promise.all([loadScenarios(), loadAlgorithms(), loadEvaluation(), pollState()]);
  } catch (error) { showNotice(error.message, true); }
  setInterval(pollState, 500);
}

init();
