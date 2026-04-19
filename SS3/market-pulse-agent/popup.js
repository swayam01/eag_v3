// Popup UI — orchestrates the Run tab live trace via chrome.runtime messaging with the service worker.

const STORAGE_KEYS = {
  settings: "marketPulseSettings",
  reports: "marketPulseReports",
  theme: "marketPulseTheme",
  priceHistory: "marketPulsePriceHistory"
};

import { loadEnv } from "./env.js";

const DEFAULT_MODEL = "gemini-2.5-flash";

const el = {
  tabs: document.querySelectorAll(".tab"),
  panels: document.querySelectorAll(".panel"),
  themeToggle: document.getElementById("themeToggle"),
  toast: document.getElementById("toast"),

  // Run
  runBtn: document.getElementById("runBtn"),
  promptInput: document.getElementById("promptInput"),
  runStatus: document.getElementById("runStatus"),
  traceContainer: document.getElementById("traceContainer"),
  finalReport: document.getElementById("finalReport"),

  // History
  historyList: document.getElementById("historyList"),
  emptyHistory: document.getElementById("emptyHistory"),
  historyBadge: document.getElementById("historyBadge"),
  clearHistoryBtn: document.getElementById("clearHistoryBtn"),

  // Schedule
  scheduleEnabled: document.getElementById("scheduleEnabled"),
  scheduleTime: document.getElementById("scheduleTime"),
  saveScheduleBtn: document.getElementById("saveScheduleBtn"),
  scheduleStatus: document.getElementById("scheduleStatus"),
  nextFire: document.getElementById("nextFire"),

  // Settings
  apiKeyInput: document.getElementById("apiKeyInput"),
  modelInput: document.getElementById("modelInput"),
  tgTokenInput: document.getElementById("tgTokenInput"),
  tgChatIdInput: document.getElementById("tgChatIdInput"),
  saveSettingsBtn: document.getElementById("saveSettingsBtn"),
  testTelegramBtn: document.getElementById("testTelegramBtn"),
  settingsStatus: document.getElementById("settingsStatus"),
  exportBtn: document.getElementById("exportBtn"),
  wipeHistoryBtn: document.getElementById("wipeHistoryBtn")
};

let settings = {};
let reports = [];
let running = false;

/* ---------- utils ---------- */
function showToast(msg, ms = 1800) {
  el.toast.textContent = msg;
  el.toast.classList.remove("hidden");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => el.toast.classList.add("hidden"), ms);
}

function setStatus(node, text, kind) {
  node.textContent = text;
  node.classList.remove("hidden", "success", "error", "working");
  if (kind) node.classList.add(kind);
  if (!text) node.classList.add("hidden");
}

function formatDate(iso) {
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

/* ---------- tabs ---------- */
el.tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    el.tabs.forEach((t) => t.classList.toggle("active", t === tab));
    el.panels.forEach((p) => p.classList.toggle("active", p.dataset.panel === tab.dataset.tab));
    if (tab.dataset.tab === "history") renderHistory();
    if (tab.dataset.tab === "schedule") updateNextFireDisplay();
  });
});

/* ---------- storage ---------- */
async function loadAll() {
  const data = await chrome.storage.local.get([
    STORAGE_KEYS.settings, STORAGE_KEYS.reports, STORAGE_KEYS.theme
  ]);
  settings = data[STORAGE_KEYS.settings] || {};
  reports = data[STORAGE_KEYS.reports] || [];

  const theme = data[STORAGE_KEYS.theme] || "light";
  document.body.classList.toggle("dark", theme === "dark");
  el.themeToggle.checked = theme === "dark";

  if (!settings.geminiApiKey) {
    const env = await loadEnv();
    if (env.GEMINI_API_KEY) {
      settings.geminiApiKey = env.GEMINI_API_KEY;
      await chrome.storage.local.set({ [STORAGE_KEYS.settings]: settings });
    }
  }
  el.apiKeyInput.value = settings.geminiApiKey || "";
  el.modelInput.value = settings.geminiModel || DEFAULT_MODEL;
  el.tgTokenInput.value = settings.telegramBotToken || "";
  el.tgChatIdInput.value = settings.telegramChatId || "";
  el.scheduleEnabled.checked = !!settings.scheduleEnabled;
  el.scheduleTime.value = settings.scheduleTime || "09:00";

  el.historyBadge.textContent = String(reports.length);
}

async function saveSettings(patch) {
  settings = { ...settings, ...patch };
  await chrome.storage.local.set({ [STORAGE_KEYS.settings]: settings });
}

/* ---------- theme ---------- */
el.themeToggle.addEventListener("change", async () => {
  const theme = el.themeToggle.checked ? "dark" : "light";
  document.body.classList.toggle("dark", theme === "dark");
  await chrome.storage.local.set({ [STORAGE_KEYS.theme]: theme });
});

/* ---------- run tab ---------- */
function resetTrace() {
  el.traceContainer.innerHTML = "";
  el.finalReport.textContent = "—";
  el.finalReport.classList.add("empty-state");
}

function renderTraceStep(step) {
  const div = document.createElement("div");
  div.className = `trace-step ${step.type}`;

  const icon = document.createElement("div");
  icon.className = "icon";
  icon.textContent = iconFor(step.type);

  const body = document.createElement("div");
  body.className = "body";

  const title = document.createElement("div");
  title.className = "step-title";
  title.textContent = titleFor(step);

  const text = document.createElement("div");
  text.className = "step-text";
  text.textContent = textFor(step);

  body.appendChild(title);
  body.appendChild(text);

  const detail = detailFor(step);
  if (detail) {
    const pre = document.createElement("pre");
    pre.textContent = detail;
    body.appendChild(pre);
  }

  div.appendChild(icon);
  div.appendChild(body);
  el.traceContainer.appendChild(div);
  el.traceContainer.scrollTop = el.traceContainer.scrollHeight;
}

function iconFor(type) {
  return ({
    user: "🙋",
    thought: "🧠",
    tool_call: "🔧",
    tool_result: "✅",
    tool_error: "⚠️",
    final: "🎯",
    error: "❌"
  })[type] || "•";
}

function titleFor(step) {
  switch (step.type) {
    case "user": return "User prompt";
    case "thought": return "Agent thinking";
    case "tool_call": return `Tool call: ${step.name}`;
    case "tool_result": return `Tool result: ${step.name}`;
    case "tool_error": return `Tool error: ${step.name}`;
    case "final": return "Final answer";
    case "error": return "Error";
    default: return step.type;
  }
}

function textFor(step) {
  if (step.text) return step.text;
  if (step.type === "tool_call") return "";
  if (step.type === "tool_result") return "";
  if (step.type === "tool_error") return step.error || "";
  return "";
}

function detailFor(step) {
  if (step.type === "tool_call") return JSON.stringify(step.args || {}, null, 2);
  if (step.type === "tool_result") return JSON.stringify(step.result, null, 2);
  return "";
}

async function runAgent() {
  if (running) return;
  if (!settings.geminiApiKey) {
    showToast("Set a Gemini API key in Settings first.");
    return;
  }
  running = true;
  el.runBtn.disabled = true;
  resetTrace();
  setStatus(el.runStatus, "🚀 Agent running…", "working");

  const userPrompt = el.promptInput.value.trim();

  const result = await chrome.runtime.sendMessage({
    type: "RUN_AGENT",
    userPrompt: userPrompt || undefined
  });

  running = false;
  el.runBtn.disabled = false;

  if (result?.ok) {
    setStatus(el.runStatus, "✅ Agent finished. Report sent to Telegram.", "success");
    el.finalReport.textContent = result.final || "(no final text)";
    el.finalReport.classList.remove("empty-state");
  } else {
    setStatus(el.runStatus, `❌ Failed: ${result?.error || "unknown"}`, "error");
  }

  await loadAll();
  renderHistory();
}

el.runBtn.addEventListener("click", runAgent);

// Live trace streaming from the service worker while an agent run is in progress.
chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "AGENT_STEP" && running) {
    renderTraceStep(message.step);
  }
});

/* ---------- history tab ---------- */
function renderHistory() {
  el.historyList.innerHTML = "";
  el.historyBadge.textContent = String(reports.length);
  if (!reports.length) {
    el.emptyHistory.classList.remove("hidden");
    return;
  }
  el.emptyHistory.classList.add("hidden");

  reports.forEach((r) => {
    const div = document.createElement("div");
    div.className = "history-item";

    const head = document.createElement("div");
    head.className = "history-head";
    const title = document.createElement("div");
    title.className = "title";
    title.textContent = `${r.source === "schedule" ? "⏰" : "🚀"} ${r.source}`;
    const badge = document.createElement("span");
    badge.className = `badge ${r.ok ? "ok" : "err"}`;
    badge.textContent = r.ok ? "ok" : "failed";
    head.appendChild(title);
    head.appendChild(badge);
    div.appendChild(head);

    const ts = document.createElement("div");
    ts.className = "timestamp";
    ts.textContent = formatDate(r.timestamp);
    div.appendChild(ts);

    if (r.final) {
      const finalDetails = document.createElement("details");
      const sum = document.createElement("summary");
      sum.textContent = "📄 Final report";
      finalDetails.appendChild(sum);
      const pre = document.createElement("pre");
      pre.textContent = r.final;
      finalDetails.appendChild(pre);
      div.appendChild(finalDetails);
    }

    if (r.error) {
      const errDiv = document.createElement("div");
      errDiv.style.color = "var(--danger)";
      errDiv.style.fontSize = "11px";
      errDiv.style.marginTop = "4px";
      errDiv.textContent = `Error: ${r.error}`;
      div.appendChild(errDiv);
    }

    const traceDetails = document.createElement("details");
    const traceSum = document.createElement("summary");
    traceSum.textContent = `🔧 Trace (${(r.trace || []).length} steps)`;
    traceDetails.appendChild(traceSum);
    const tracePre = document.createElement("pre");
    tracePre.textContent = JSON.stringify(r.trace, null, 2);
    traceDetails.appendChild(tracePre);
    div.appendChild(traceDetails);

    el.historyList.appendChild(div);
  });
}

el.clearHistoryBtn.addEventListener("click", async () => {
  if (!confirm("Clear all past runs?")) return;
  reports = [];
  await chrome.storage.local.set({ [STORAGE_KEYS.reports]: [] });
  renderHistory();
  showToast("🗑️ History cleared.");
});

/* ---------- schedule tab ---------- */
el.saveScheduleBtn.addEventListener("click", async () => {
  await saveSettings({
    scheduleEnabled: el.scheduleEnabled.checked,
    scheduleTime: el.scheduleTime.value || "09:00"
  });
  await chrome.runtime.sendMessage({ type: "RECONCILE_ALARM" });
  setStatus(el.scheduleStatus, "✅ Schedule saved.", "success");
  updateNextFireDisplay();
});

async function updateNextFireDisplay() {
  const alarm = await chrome.alarms.get("market-pulse-daily");
  if (alarm?.scheduledTime) {
    el.nextFire.textContent = new Date(alarm.scheduledTime).toLocaleString();
  } else {
    el.nextFire.textContent = "Not scheduled.";
  }
}

/* ---------- settings tab ---------- */
el.saveSettingsBtn.addEventListener("click", async () => {
  await saveSettings({
    geminiApiKey: el.apiKeyInput.value.trim(),
    geminiModel: el.modelInput.value.trim() || DEFAULT_MODEL,
    telegramBotToken: el.tgTokenInput.value.trim(),
    telegramChatId: el.tgChatIdInput.value.trim()
  });
  setStatus(el.settingsStatus, "✅ Settings saved.", "success");
});

el.testTelegramBtn.addEventListener("click", async () => {
  const token = el.tgTokenInput.value.trim();
  const chatId = el.tgChatIdInput.value.trim();
  if (!token || !chatId) {
    setStatus(el.settingsStatus, "Enter both bot token and chat ID first.", "error");
    return;
  }
  setStatus(el.settingsStatus, "🧪 Sending test message…", "working");
  try {
    const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text: "✅ Market Pulse test message" })
    });
    const body = await res.text();
    if (!res.ok) throw new Error(`${res.status}: ${body}`);
    setStatus(el.settingsStatus, "✅ Test message sent to Telegram!", "success");
  } catch (err) {
    setStatus(el.settingsStatus, `❌ ${err.message}`, "error");
  }
});

el.exportBtn.addEventListener("click", async () => {
  const data = await chrome.storage.local.get([STORAGE_KEYS.reports, STORAGE_KEYS.priceHistory]);
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `market-pulse-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
});

el.wipeHistoryBtn.addEventListener("click", async () => {
  if (!confirm("Wipe stored price history? Past runs will still be visible; only the price samples used by calc_change will be deleted.")) return;
  await chrome.storage.local.remove(STORAGE_KEYS.priceHistory);
  showToast("🗑️ Price history wiped.");
});

/* ---------- auto-refresh history on storage changes ---------- */
chrome.storage.onChanged.addListener((changes) => {
  if (changes[STORAGE_KEYS.reports]) {
    reports = changes[STORAGE_KEYS.reports].newValue || [];
    renderHistory();
  }
});

/* ---------- init ---------- */
(async function init() {
  await loadAll();
  renderHistory();
  updateNextFireDisplay();
})();
