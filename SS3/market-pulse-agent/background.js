// Service worker. Owns chrome.alarms scheduling and runs the agent on schedule.
// Also runs the agent on-demand when the popup sends RUN_AGENT (popup needs this route
// because the popup window closes and would abort long-running fetch chains).

import { runAgent } from "./agent.js";
import { loadEnv } from "./env.js";

const SETTINGS_KEY = "marketPulseSettings";
const REPORTS_KEY = "marketPulseReports";
const ALARM_NAME = "market-pulse-daily";

const DEFAULT_PROMPT = "Run today's market pulse briefing and send it to Telegram.";

// ---------- Install / startup ----------

chrome.runtime.onInstalled.addListener(async () => {
  await reconcileAlarm();
});

chrome.runtime.onStartup.addListener(async () => {
  await reconcileAlarm();
});

// ---------- Alarm handler ----------

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== ALARM_NAME) return;
  await executeRun({ source: "schedule" });
});

// ---------- Message router ----------

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "RUN_AGENT") {
    executeRun({ source: "manual", userPrompt: message.userPrompt || DEFAULT_PROMPT })
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true;
  }
  if (message?.type === "RECONCILE_ALARM") {
    reconcileAlarm().then(() => sendResponse({ ok: true })).catch((err) => sendResponse({ ok: false, error: err.message }));
    return true;
  }
  return false;
});

// ---------- Core run ----------

async function executeRun({ source, userPrompt }) {
  const { [SETTINGS_KEY]: settings = {} } = await chrome.storage.local.get(SETTINGS_KEY);
  let apiKey = settings.geminiApiKey;
  if (!apiKey) {
    const env = await loadEnv();
    apiKey = env.GEMINI_API_KEY;
  }
  const model = settings.geminiModel || "gemini-2.5-flash";

  if (!apiKey) {
    const err = "Gemini API key missing. Open Settings.";
    await saveReport({ source, trace: [], final: null, error: err, ok: false });
    notify("Market Pulse", err);
    return { ok: false, error: err, trace: [] };
  }

  const trace = [];
  const result = await runAgent({
    apiKey,
    model,
    userPrompt: userPrompt || DEFAULT_PROMPT,
    onStep: (step) => {
      trace.push(step);
      chrome.runtime.sendMessage({ type: "AGENT_STEP", step }).catch(() => {});
    }
  });

  await saveReport({
    source,
    trace: result.trace,
    final: result.final || null,
    error: result.error || null,
    ok: result.ok
  });

  if (source === "schedule") {
    if (result.ok) {
      notify("Market Pulse", "Daily briefing sent to Telegram ✅");
    } else {
      notify("Market Pulse", `Run failed: ${result.error || "unknown"}`);
    }
  }

  return result;
}

async function saveReport(report) {
  const full = { ...report, timestamp: new Date().toISOString(), id: `${Date.now()}-${Math.random().toString(16).slice(2, 8)}` };
  const { [REPORTS_KEY]: existing = [] } = await chrome.storage.local.get(REPORTS_KEY);
  const next = [full, ...existing].slice(0, 50);
  await chrome.storage.local.set({ [REPORTS_KEY]: next });
}

function notify(title, message) {
  try {
    chrome.notifications?.create({
      type: "basic",
      iconUrl: chrome.runtime.getURL("icon128.png"),
      title,
      message
    });
  } catch {}
}

// ---------- Alarm reconciliation ----------

async function reconcileAlarm() {
  const { [SETTINGS_KEY]: settings = {} } = await chrome.storage.local.get(SETTINGS_KEY);
  await chrome.alarms.clear(ALARM_NAME);

  if (!settings.scheduleEnabled) return;

  const time = settings.scheduleTime || "09:00";
  const [hours, minutes] = time.split(":").map(Number);
  if (isNaN(hours) || isNaN(minutes)) return;

  const now = new Date();
  const next = new Date();
  next.setHours(hours, minutes, 0, 0);
  if (next <= now) next.setDate(next.getDate() + 1);

  chrome.alarms.create(ALARM_NAME, {
    when: next.getTime(),
    periodInMinutes: 24 * 60
  });
}
