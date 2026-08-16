"use strict";

/* Presentation Stage — keyboard-first, audience-facing view.
   All state comes from the same server as the console; the stage never owns
   demo logic, it only renders snapshots and posts the same control endpoints. */

const byId = (id) => document.getElementById(id);

const ACCENTS = {
  coral: "#ff7a6e",
  blue: "#5aa2ff",
  violet: "#a78bfa",
  green: "#34d399",
  gold: "#fbbf24",
  red: "#f87171",
};

// Live runs from the stage always use the console's "research" timing preset;
// anything custom is configured in the console beforehand.
const LIVE_PRESET = { sensors: "both", monitor_lead: 420, listen_duration: 300, laptop_voice: true };

let currentState = null;
let scenarioData = {};
let scenarioIds = [];
let selectedScenario = null;
let lastFrameVersion = -1;
let railBuilt = false;
let toastTimer = null;
let idleTimer = null;

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

function showToast(message, isError = true) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.remove("hidden", "info");
  if (!isError) toast.classList.add("info");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.add("hidden"), isError ? 7000 : 4000);
}

async function post(path, body = {}) {
  const payload = await request(path, { method: "POST", body });
  const state = payload?.state || (payload?.steps ? payload : null);
  if (state) renderState(state);
  return payload;
}

function act(path, body = {}) {
  return post(path, body).catch((error) => showToast(error.message));
}

/* ============ title view ============ */

function setAccent(name) {
  document.documentElement.style.setProperty("--accent", ACCENTS[name] || ACCENTS.blue);
}

function selectScenario(id) {
  const scenario = scenarioData[id];
  if (!scenario) return;
  selectedScenario = id;
  document.querySelectorAll(".scenario-card").forEach((card) => {
    card.classList.toggle("selected", card.dataset.id === id);
    card.setAttribute("aria-selected", String(card.dataset.id === id));
  });
  setAccent(scenario.accent);
  byId("scenario-description").textContent = scenario.description;
  const sensors = scenario.recommended_sensors === "both" ? "mic → camera fallback" : "microphone only";
  byId("guided-caption").textContent = `${scenario.recommended_policy} policy · ${sensors}`;
  renderTitleReadiness(currentState);
}

function buildScenarioCards() {
  const grid = byId("scenario-grid");
  grid.replaceChildren();
  scenarioIds.forEach((id, index) => {
    const scenario = scenarioData[id];
    const card = document.createElement("button");
    card.type = "button";
    card.className = "scenario-card";
    card.dataset.id = id;
    card.setAttribute("role", "option");
    card.style.setProperty("--card-accent", ACCENTS[scenario.accent] || ACCENTS.blue);
    const number = document.createElement("span");
    number.className = "card-number";
    number.textContent = String(index + 1);
    const title = document.createElement("h3");
    title.textContent = scenario.title;
    const short = document.createElement("p");
    short.textContent = scenario.short;
    card.append(number, title, short);
    card.addEventListener("click", () => selectScenario(id));
    card.addEventListener("dblclick", () => startGuided());
    grid.append(card);
  });
}

function startGuided() {
  const scenario = scenarioData[selectedScenario];
  if (!scenario || byId("start-guided").disabled) return;
  act("/api/demo/start", {
    scenario: selectedScenario,
    policy: scenario.recommended_policy,
    sensors: scenario.recommended_sensors,
  });
}

function startLive() {
  const scenario = scenarioData[selectedScenario];
  act("/api/live/start", { policy: scenario?.recommended_policy || "remember", ...LIVE_PRESET });
}

function renderTitleReadiness(state) {
  if (!state) return;
  const readiness = state.readiness || {};
  const busy = state.mode === "job";
  byId("busy-note").classList.toggle("hidden", !busy);
  byId("start-guided").disabled = busy;

  const reminder = readiness.next_reminder;
  const reasons = [];
  if (!reminder) reasons.push("no pending reminder — add one in the console");
  if (readiness.voice?.ready === false) reasons.push("voice enrollment missing");
  if (readiness.face?.ready === false) reasons.push("face enrollment missing");
  byId("start-live").disabled = busy || reasons.length > 0;
  byId("live-caption").textContent = reasons.length
    ? reasons.join(" · ")
    : `next: “${reminder.text}” · due ${String(reminder.remind_at).slice(11, 16)} · research timing · ready ✓`;
}

/* ============ stage view ============ */

function buildRail(steps) {
  const rail = byId("rail");
  rail.replaceChildren();
  steps.forEach((step, index) => {
    const node = document.createElement("div");
    node.className = "rail-node pending";
    node.dataset.step = step.id;
    const dot = document.createElement("div");
    dot.className = "dot";
    dot.dataset.number = String(index + 1);
    const label = document.createElement("span");
    label.className = "node-label";
    label.textContent = step.eyebrow;
    node.append(dot, label);
    rail.append(node);
  });
  railBuilt = true;
}

function renderRail(state) {
  (state.steps || []).forEach((step) => {
    const node = document.querySelector(`.rail-node[data-step="${step.id}"]`);
    if (!node) return;
    const next = `rail-node ${step.status}`;
    if (node.className !== next) node.className = next; // keep the pulse animation running
  });
}

function renderStageHeader(state) {
  const scenario = scenarioData[state.scenario];
  if (scenario) setAccent(scenario.accent);
  byId("stage-scenario").textContent = scenario?.title || (state.mode === "live" ? "Live hardware run" : "Walkthrough");
  const badge = byId("stage-mode-badge");
  badge.textContent = state.mode === "live" ? "LIVE" : "GUIDED";
  badge.classList.toggle("live", state.mode === "live");
  const sensors = state.config?.sensors === "both" ? "mic → camera" : "mic only";
  byId("stage-config").textContent = state.config?.policy ? `${state.config.policy} · ${sensors}` : "";
  byId("stage-status").className = `status-dot ${state.status || "idle"}`;
}

function renderHeadline(state) {
  const active = (state.steps || []).find((step) => step.id === state.current_step);
  byId("stage-eyebrow").textContent = active?.eyebrow || "";
  byId("stage-headline").textContent = state.headline || active?.title || "";
  byId("stage-detail").textContent = active?.detail || "";
}

function renderOutcome(state) {
  const banner = byId("outcome-banner");
  const outcome = state.outcome ? String(state.outcome) : "";
  banner.classList.toggle("hidden", !outcome);
  if (!outcome) return;
  const lower = outcome.toLowerCase();
  byId("outcome-icon").textContent =
    lower.includes("privat") || lower.includes("wrist") || lower.includes("held") ? "🔒"
      : lower.includes("spoke") || lower.includes("aloud") ? "🔊"
        : "✓";
  byId("outcome-text").textContent = outcome;
}

function renderSensors(state) {
  const micOn = Boolean(state.sensors?.microphone);
  byId("tile-mic").classList.toggle("on", micOn);
  byId("mic-state").textContent = micOn ? "listening" : "closed";
  const remaining = Number(state.metrics?.microphone_level_remaining_s || 0);
  byId("mic-remaining").textContent = micOn
    ? (remaining > 0 ? `temporary window · ${Math.max(0, remaining).toFixed(0)}s remaining` : "temporary window · raw audio discarded")
    : "no audio is being captured";
  const level = Math.min(100, Math.max(0, Number(state.metrics?.microphone_level || 0) / 0.05 * 100));
  byId("mic-meter").style.width = `${level}%`;

  const cameraOn = Boolean(state.sensors?.camera);
  byId("tile-camera").classList.toggle("on", cameraOn);
  byId("camera-state").textContent = cameraOn ? "robot point of view" : "lens closed";
  const hasFrame = cameraOn && state.frame_available;
  byId("camera-frame").classList.toggle("hidden", !hasFrame);
  byId("camera-shutter").classList.toggle("hidden", hasFrame);
  if (hasFrame && state.frame_version !== lastFrameVersion) {
    lastFrameVersion = state.frame_version;
    byId("camera-frame").src = `/api/frame?v=${state.frame_version}`;
  }

  const ownerStep = (state.steps || []).find((step) => step.id === "owner");
  byId("tile-watch").classList.toggle("on", ownerStep?.status === "complete");
  byId("watch-state").textContent = ownerStep?.status === "complete" ? "owner present"
    : ownerStep?.status === "warning" ? "watch offline" : "checked during run";
  const identity = state.identity;
  byId("identity-state").textContent = identity
    ? `${identity.modality === "face" ? "Seen" : "Heard"}: ${identity.id}${identity.similarity != null ? ` · cosine ${Number(identity.similarity).toFixed(2)}` : ""}`
    : "no bystander identified";
}

function renderTicker(state) {
  const event = (state.events || []).slice(-1)[0];
  const ticker = byId("ticker");
  if (!event) {
    ticker.classList.add("hidden");
    return;
  }
  ticker.className = `ticker ${event.tone || "info"}`;
  byId("ticker-time").textContent = String(event.at).slice(11, 19);
  byId("ticker-message").textContent = event.message;
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
  const pad = (value) => String(value).padStart(2, "0");
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  return hours ? `${hours}:${pad(minutes)}:${pad(whole % 60)}` : `${minutes}:${pad(whole % 60)}`;
}

function renderControls(state) {
  const isDemo = state.mode === "demo";
  byId("guided-controls").classList.toggle("hidden", !isDemo);
  byId("live-controls").classList.toggle("hidden", state.mode !== "live");
  if (isDemo) {
    byId("control-next").disabled = !state.demo?.has_next;
    byId("control-previous").disabled = Number(state.demo?.cursor || 0) <= 0;
    byId("step-counter").textContent = `${state.demo?.cursor ?? 0} / ${state.demo?.total ?? 0}`;
  } else if (state.mode === "live") {
    const reminder = state.config?.reminder;
    byId("live-countdown").textContent = reminder
      ? `“${reminder.text}” · ${formatCountdown(secondsUntil(reminder))}`
      : "";
    byId("control-stop").disabled = !state.process_running;
  }
}

/* ============ state pump ============ */

function renderState(state) {
  currentState = state;
  const onStage = state.mode === "demo" || state.mode === "live";
  document.body.classList.toggle("view-stage", onStage);
  document.body.classList.toggle("view-title", !onStage);
  if (!railBuilt && Array.isArray(state.steps) && state.steps.length) buildRail(state.steps);
  if (onStage) {
    renderStageHeader(state);
    renderHeadline(state);
    renderRail(state);
    renderOutcome(state);
    renderSensors(state);
    renderTicker(state);
    renderControls(state);
  } else {
    renderTitleReadiness(state);
  }
}

async function pollState() {
  try {
    const state = await request("/api/state");
    renderState(state);
  } catch (error) {
    byId("stage-status").className = "status-dot error";
  }
}

/* ============ input ============ */

function toggleFullscreen() {
  if (!document.fullscreenElement) document.documentElement.requestFullscreen().catch(() => {});
  else document.exitFullscreen().catch(() => {});
}

function wakeControls() {
  document.body.classList.remove("controls-idle");
  clearTimeout(idleTimer);
  idleTimer = setTimeout(() => document.body.classList.add("controls-idle"), 3000);
}

function leaveStage() {
  const mode = currentState?.mode;
  if (mode === "demo") {
    act("/api/reset");
  } else if (mode === "live") {
    if (currentState?.process_running) byId("stop-confirm").classList.remove("hidden");
    else act("/api/reset");
  }
}

async function confirmStopLive() {
  byId("stop-confirm").classList.add("hidden");
  try {
    await post("/api/live/stop");
  } catch (error) {
    showToast(error.message);
    return;
  }
  // The child needs a moment to release sensors; reset once it has exited.
  setTimeout(() => {
    if (currentState && !currentState.process_running) act("/api/reset");
  }, 1500);
}

function handleKeydown(event) {
  if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName)) return;
  wakeControls();
  const mode = currentState?.mode || "idle";

  if (event.key === "?") {
    byId("keys-overlay").classList.toggle("hidden");
    return;
  }
  if (event.key === "f" || event.key === "F") {
    toggleFullscreen();
    return;
  }
  if (event.key === "Escape") {
    if (!byId("keys-overlay").classList.contains("hidden")) return byId("keys-overlay").classList.add("hidden");
    if (!byId("stop-confirm").classList.contains("hidden")) return byId("stop-confirm").classList.add("hidden");
    if (document.fullscreenElement) return; // the browser handles fullscreen exit itself
    leaveStage();
    return;
  }

  if (mode === "idle" || mode === "job") {
    if (/^[1-6]$/.test(event.key)) {
      const id = scenarioIds[Number(event.key) - 1];
      if (id) selectScenario(id);
    } else if (event.key === "Enter" && document.activeElement === document.body) {
      startGuided();
    }
    return;
  }

  if (mode === "demo") {
    if (["ArrowRight", "PageDown", " "].includes(event.key)) {
      event.preventDefault();
      if (currentState?.demo?.has_next) act("/api/demo/next");
    } else if (["ArrowLeft", "PageUp"].includes(event.key)) {
      event.preventDefault();
      if (Number(currentState?.demo?.cursor || 0) > 0) act("/api/demo/previous");
    } else if (event.key === "r" || event.key === "R") {
      startGuided();
    }
  }
}

function bindEvents() {
  byId("start-guided").addEventListener("click", startGuided);
  byId("start-live").addEventListener("click", startLive);
  byId("control-next").addEventListener("click", () => act("/api/demo/next"));
  byId("control-previous").addEventListener("click", () => act("/api/demo/previous"));
  byId("control-restart").addEventListener("click", startGuided);
  byId("control-stop").addEventListener("click", () => byId("stop-confirm").classList.remove("hidden"));
  byId("confirm-stop").addEventListener("click", confirmStopLive);
  byId("confirm-cancel").addEventListener("click", () => byId("stop-confirm").classList.add("hidden"));
  document.addEventListener("keydown", handleKeydown);
  document.addEventListener("pointermove", wakeControls);
  // Keep Space/Enter for the keyboard flow instead of re-triggering the last clicked button.
  document.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (button) button.blur();
  });
}

async function init() {
  bindEvents();
  try {
    const payload = await request("/api/scenarios");
    scenarioData = payload.scenarios || {};
    scenarioIds = Object.keys(scenarioData);
    buildScenarioCards();
    if (scenarioIds.length) selectScenario(scenarioIds[0]);
    await pollState();
  } catch (error) {
    showToast(error.message);
  }
  setInterval(pollState, 500);
  wakeControls();
}

init();
