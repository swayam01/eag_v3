const STORAGE_KEYS = {
  records: "audioInsightRecords",
  theme: "audioInsightTheme",
  apiKey: "audioInsightApiKey",
  model: "audioInsightModel"
};

const DEFAULT_MODEL = "gemini-2.5-flash-lite";
const DEFAULT_API_KEY = "AIzaSyAGEwQCmAj-6PFIcNJNObEHCNof91WBLYk";

const el = {
  themeToggle: document.getElementById("themeToggle"),
  toast: document.getElementById("toast"),
  tabs: document.querySelectorAll(".tab"),
  panels: document.querySelectorAll(".panel"),

  openRecorderBtn: document.getElementById("openRecorderBtn"),

  rescanBtn: document.getElementById("rescanBtn"),
  mediaList: document.getElementById("mediaList"),
  noMedia: document.getElementById("noMedia"),
  manualAudioUrl: document.getElementById("manualAudioUrl"),
  manualLabel: document.getElementById("manualLabel"),
  transcribeUrlBtn: document.getElementById("transcribeUrlBtn"),
  detectStatus: document.getElementById("detectStatus"),

  searchInput: document.getElementById("searchInput"),
  libraryList: document.getElementById("libraryList"),
  emptyLib: document.getElementById("emptyLib"),
  libCount: document.getElementById("libCount"),
  libCountBadge: document.getElementById("libCountBadge"),
  libraryItemTpl: document.getElementById("libraryItemTpl"),

  chatMessages: document.getElementById("chatMessages"),
  chatInput: document.getElementById("chatInput"),
  askBtn: document.getElementById("askBtn"),
  clearChatBtn: document.getElementById("clearChatBtn"),
  transcriptSelect: document.getElementById("transcriptSelect"),
  selectedSummary: document.getElementById("selectedSummary"),

  apiKeyInput: document.getElementById("apiKeyInput"),
  modelInput: document.getElementById("modelInput"),
  saveSettingsBtn: document.getElementById("saveSettingsBtn"),
  testKeyBtn: document.getElementById("testKeyBtn"),
  settingsStatus: document.getElementById("settingsStatus"),
  exportBtn: document.getElementById("exportBtn"),
  wipeBtn: document.getElementById("wipeBtn")
};

let records = [];
let settings = { apiKey: "", model: DEFAULT_MODEL };
let chatHistory = [];
let currentPage = { title: "", url: "" };

/* ---------- utils ---------- */
function generateId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function formatDate(iso) {
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

function fmtDuration(sec) {
  if (!sec) return "";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

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

/* ---------- storage ---------- */
async function loadAll() {
  const data = await chrome.storage.local.get([
    STORAGE_KEYS.records, STORAGE_KEYS.apiKey,
    STORAGE_KEYS.model, STORAGE_KEYS.theme
  ]);
  records = Array.isArray(data[STORAGE_KEYS.records]) ? data[STORAGE_KEYS.records] : [];
  settings.apiKey = data[STORAGE_KEYS.apiKey] || DEFAULT_API_KEY;
  settings.model = data[STORAGE_KEYS.model] || DEFAULT_MODEL;

  if (!data[STORAGE_KEYS.apiKey]) {
    await chrome.storage.local.set({ [STORAGE_KEYS.apiKey]: DEFAULT_API_KEY });
  }

  const theme = data[STORAGE_KEYS.theme] || "light";
  document.body.classList.toggle("dark", theme === "dark");
  el.themeToggle.checked = theme === "dark";

  el.apiKeyInput.value = settings.apiKey;
  el.modelInput.value = settings.model;
}

async function saveRecords() {
  await chrome.storage.local.set({ [STORAGE_KEYS.records]: records });
}

/* ---------- tabs ---------- */
function switchTab(name) {
  el.tabs.forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  el.panels.forEach((p) => p.classList.toggle("active", p.dataset.panel === name));
  if (name === "ask") populateTranscriptSelect();
}

el.tabs.forEach((tab) => {
  tab.addEventListener("click", () => switchTab(tab.dataset.tab));
});

/* ---------- detect ---------- */
async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
}

async function scanPage() {
  el.mediaList.innerHTML = "";
  el.noMedia.classList.add("hidden");
  try {
    const tab = await getActiveTab();
    if (!tab?.id) { el.noMedia.classList.remove("hidden"); return; }
    const res = await chrome.tabs.sendMessage(tab.id, { type: "SCAN_MEDIA" });
    currentPage = { title: res?.pageTitle || tab.title || "Untitled", url: res?.pageUrl || tab.url || "" };
    const media = res?.media || [];
    if (!media.length) { el.noMedia.classList.remove("hidden"); return; }
    media.forEach((m) => renderMediaItem(m));
  } catch (_e) {
    const tab = await getActiveTab();
    currentPage = { title: tab?.title || "", url: tab?.url || "" };
    el.noMedia.classList.remove("hidden");
  }
}

function renderMediaItem(m) {
  const div = document.createElement("div");
  div.className = "media-item";

  const info = document.createElement("div");
  info.className = "media-info";

  const label = document.createElement("div");
  label.className = "media-label";
  label.textContent = m.label || "Audio";
  label.title = m.src;

  const meta = document.createElement("div");
  meta.className = "media-meta";
  const parts = [m.isVideo ? "video" : "audio"];
  if (m.duration) parts.push(fmtDuration(m.duration));
  if (m.mimeType) parts.push(m.mimeType.split("/").pop());
  meta.textContent = parts.join(" · ");

  info.appendChild(label);
  info.appendChild(meta);

  const btn = document.createElement("button");
  btn.className = "primary small-btn";
  btn.textContent = "Transcribe";
  btn.addEventListener("click", () => handleTranscribe(m.src, m.label));

  div.appendChild(info);
  div.appendChild(btn);
  el.mediaList.appendChild(div);
}

/* ---------- transcription flow ---------- */
async function handleTranscribe(audioUrl, label) {
  if (!settings.apiKey) {
    showToast("Set a Gemini API key in Settings first.");
    switchTab("settings");
    return;
  }
  if (!audioUrl) {
    showToast("No audio URL.");
    return;
  }

  setStatus(el.detectStatus, "🎧 Fetching and transcribing audio… (this may take a while for long audio)", "working");

  try {
    const transcript = await transcribeAudio(settings.apiKey, settings.model, audioUrl);

    setStatus(el.detectStatus, "✨ Generating summary…", "working");
    let summary = "", keyPoints = [], topics = [];
    try {
      const result = await summarizeTranscript(settings.apiKey, settings.model, transcript, label || currentPage.title);
      summary = result.summary;
      keyPoints = result.keyPoints;
      topics = result.topics;
    } catch (sumErr) {
      console.warn("Summary failed:", sumErr);
    }

    const now = new Date().toISOString();
    const record = {
      id: generateId(),
      title: label || currentPage.title || "Untitled audio",
      pageUrl: currentPage.url,
      audioUrl,
      transcript,
      summary,
      keyPoints,
      topics,
      createdAt: now,
      updatedAt: now
    };

    records.unshift(record);
    await saveRecords();
    renderLibrary();

    setStatus(el.detectStatus, `✅ Transcribed and saved: "${record.title}"`, "success");
  } catch (err) {
    setStatus(el.detectStatus, `Error: ${err.message}`, "error");
  }
}

el.transcribeUrlBtn.addEventListener("click", () => {
  const url = el.manualAudioUrl.value.trim();
  const label = el.manualLabel.value.trim();
  handleTranscribe(url, label);
});

/* ---------- mic recording (opens dedicated window) ---------- */
el.openRecorderBtn.addEventListener("click", async () => {
  const res = await chrome.runtime.sendMessage({ type: "OPEN_RECORDER" });
  if (!res?.ok) {
    showToast(`Could not open recorder: ${res?.error || "unknown error"}`, 3000);
  }
});

/* ---------- library ---------- */
function renderLibrary() {
  const query = el.searchInput.value.trim().toLowerCase();
  const filtered = records.filter((r) => {
    if (!query) return true;
    return [r.title, r.summary, r.transcript, ...(r.topics || []), ...(r.keyPoints || [])]
      .filter(Boolean).join(" ").toLowerCase().includes(query);
  });

  el.libraryList.innerHTML = "";
  el.libCount.textContent = String(filtered.length);
  el.libCountBadge.textContent = String(records.length);
  el.emptyLib.classList.toggle("hidden", filtered.length !== 0);

  filtered
    .sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))
    .forEach((r) => renderLibItem(r));
}

function renderLibItem(r) {
  const node = el.libraryItemTpl.content.firstElementChild.cloneNode(true);
  node.dataset.id = r.id;

  node.querySelector(".lib-title").textContent = r.title || "Untitled";

  const urlEl = node.querySelector(".lib-url");
  urlEl.href = r.pageUrl || "#";
  urlEl.textContent = r.pageUrl || "";

  const topicsBox = node.querySelector(".lib-topics");
  (r.topics || []).forEach((t) => {
    const span = document.createElement("span");
    span.className = "topic-tag";
    span.textContent = t;
    topicsBox.appendChild(span);
  });

  const summaryEl = node.querySelector(".lib-summary");
  summaryEl.textContent = r.summary || "No summary.";

  const kpBox = node.querySelector(".lib-keypoints");
  if (r.keyPoints?.length) {
    r.keyPoints.forEach((kp) => {
      const div = document.createElement("div");
      div.className = "keypoint";
      div.textContent = kp;
      kpBox.appendChild(div);
    });
  } else {
    kpBox.remove();
  }

  node.querySelector(".lib-transcript").textContent = r.transcript || "";
  node.querySelector(".lib-footer").textContent = `Saved: ${formatDate(r.createdAt)}`;

  node.querySelector(".ask-single-btn").addEventListener("click", () => {
    switchTab("ask");
    document.querySelector('input[name="askMode"][value="single"]').checked = true;
    handleAskModeChange();
    el.transcriptSelect.value = r.id;
    updateSummaryPreview();
  });

  node.querySelector(".copy-btn").addEventListener("click", async () => {
    const payload = [
      `Title: ${r.title}`,
      r.summary ? `Summary:\n${r.summary}` : "",
      r.keyPoints?.length ? `Key points:\n- ${r.keyPoints.join("\n- ")}` : "",
      `Transcript:\n${r.transcript}`
    ].filter(Boolean).join("\n\n");
    await navigator.clipboard.writeText(payload);
    showToast("📋 Copied!");
  });

  node.querySelector(".delete-btn").addEventListener("click", async () => {
    records = records.filter((x) => x.id !== r.id);
    await saveRecords();
    renderLibrary();
    populateTranscriptSelect();
  });

  el.libraryList.appendChild(node);
}

function highlightLibItem(id) {
  switchTab("library");
  requestAnimationFrame(() => {
    const node = el.libraryList.querySelector(`[data-id="${id}"]`);
    if (!node) return;
    node.scrollIntoView({ block: "nearest", behavior: "smooth" });
    node.classList.add("highlight");
    setTimeout(() => node.classList.remove("highlight"), 1500);
  });
}

/* ---------- ask ---------- */
function populateTranscriptSelect() {
  const current = el.transcriptSelect.value;
  el.transcriptSelect.innerHTML = '<option value="">— Pick a transcript —</option>';
  records.forEach((r) => {
    const opt = document.createElement("option");
    opt.value = r.id;
    opt.textContent = (r.title || "Untitled").slice(0, 50);
    el.transcriptSelect.appendChild(opt);
  });
  if (current && records.some((r) => r.id === current)) {
    el.transcriptSelect.value = current;
  }
  updateSummaryPreview();
}

function updateSummaryPreview() {
  const mode = document.querySelector('input[name="askMode"]:checked')?.value;
  if (mode === "all") {
    el.transcriptSelect.classList.add("hidden");
    if (records.length) {
      el.selectedSummary.classList.remove("hidden");
      el.selectedSummary.innerHTML = `<strong>${records.length} transcript${records.length > 1 ? "s" : ""}</strong> in your library. Ask anything across all of them.`;
    } else {
      el.selectedSummary.classList.add("hidden");
    }
    return;
  }

  el.transcriptSelect.classList.remove("hidden");
  const id = el.transcriptSelect.value;
  const r = records.find((x) => x.id === id);
  if (!r) {
    el.selectedSummary.classList.add("hidden");
    return;
  }
  el.selectedSummary.classList.remove("hidden");
  const parts = [`<strong>${r.title}</strong>`];
  if (r.summary) parts.push(r.summary);
  if (r.keyPoints?.length) parts.push(`Key: ${r.keyPoints.slice(0, 3).join(" · ")}`);
  el.selectedSummary.innerHTML = parts.join("<br/>");
}

function handleAskModeChange() {
  updateSummaryPreview();
  chatHistory = [];
  renderChat();
}

document.querySelectorAll('input[name="askMode"]').forEach((radio) => {
  radio.addEventListener("change", handleAskModeChange);
});
el.transcriptSelect.addEventListener("change", () => {
  updateSummaryPreview();
  chatHistory = [];
  renderChat();
});

function renderChatEmpty() {
  const mode = document.querySelector('input[name="askMode"]:checked')?.value;
  const label = mode === "all" ? "all saved transcripts" : "the selected transcript";
  el.chatMessages.innerHTML = `<div class="chat-empty">💡 Ask a question about ${label}.</div>`;
}

function renderAssistantAnswer(text) {
  const div = document.createElement("div");
  div.className = "msg assistant";

  const ids = new Set(records.map((r) => r.id));
  const parts = String(text).split(/(\[[^\]]+\])/g);
  parts.forEach((part) => {
    const m = part.match(/^\[([^\]]+)\]$/);
    if (m && ids.has(m[1])) {
      const chip = document.createElement("span");
      chip.className = "cite";
      const rec = records.find((r) => r.id === m[1]);
      chip.textContent = rec ? (rec.title || "source").slice(0, 24) : m[1];
      chip.title = rec?.pageUrl || "";
      chip.addEventListener("click", () => highlightLibItem(m[1]));
      div.appendChild(chip);
    } else {
      div.appendChild(document.createTextNode(part));
    }
  });
  return div;
}

function renderChat() {
  if (!chatHistory.length) { renderChatEmpty(); return; }
  el.chatMessages.innerHTML = "";
  chatHistory.forEach((m) => {
    if (m.role === "user") {
      const div = document.createElement("div");
      div.className = "msg user";
      div.textContent = m.text;
      el.chatMessages.appendChild(div);
    } else if (m.role === "working") {
      const div = document.createElement("div");
      div.className = "msg assistant working";
      div.textContent = "Thinking...";
      el.chatMessages.appendChild(div);
    } else if (m.role === "error") {
      const div = document.createElement("div");
      div.className = "msg assistant error";
      div.textContent = m.text;
      el.chatMessages.appendChild(div);
    } else {
      el.chatMessages.appendChild(renderAssistantAnswer(m.text));
    }
  });
  el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
}

async function handleAsk() {
  const q = el.chatInput.value.trim();
  if (!q) return;
  if (!settings.apiKey) { showToast("Set API key in Settings."); return; }
  if (!records.length) { showToast("No transcripts saved yet."); return; }

  const mode = document.querySelector('input[name="askMode"]:checked')?.value;
  const selectedId = el.transcriptSelect.value;

  if (mode === "single" && !selectedId) {
    showToast("Pick a transcript first.");
    return;
  }

  el.chatInput.value = "";
  el.askBtn.disabled = true;
  chatHistory.push({ role: "user", text: q });
  chatHistory.push({ role: "working" });
  renderChat();

  const priorTurns = chatHistory
    .filter((m) => m.role === "user" || m.role === "assistant")
    .slice(-8, -1);

  try {
    let answer;
    if (mode === "single") {
      const rec = records.find((r) => r.id === selectedId);
      if (!rec) throw new Error("Transcript not found.");
      answer = await askTranscript(settings.apiKey, settings.model, rec, q, priorTurns);
    } else {
      answer = await askAllTranscripts(settings.apiKey, settings.model, records, q, priorTurns);
    }
    chatHistory = chatHistory.filter((m) => m.role !== "working");
    chatHistory.push({ role: "assistant", text: answer });
  } catch (err) {
    chatHistory = chatHistory.filter((m) => m.role !== "working");
    chatHistory.push({ role: "error", text: err.message });
  }

  renderChat();
  el.askBtn.disabled = false;
}

/* ---------- settings ---------- */
async function saveSettings() {
  settings.apiKey = el.apiKeyInput.value.trim();
  settings.model = el.modelInput.value.trim() || DEFAULT_MODEL;
  await chrome.storage.local.set({
    [STORAGE_KEYS.apiKey]: settings.apiKey,
    [STORAGE_KEYS.model]: settings.model
  });
  setStatus(el.settingsStatus, "✅ Settings saved.", "success");
}

async function testKey() {
  const key = el.apiKeyInput.value.trim();
  const model = el.modelInput.value.trim() || DEFAULT_MODEL;
  if (!key) { setStatus(el.settingsStatus, "Enter an API key first.", "error"); return; }
  setStatus(el.settingsStatus, "Testing...", "working");
  try {
    const text = await callGeminiText(key, model, "Respond with only the word: pong", { temperature: 0 });
    setStatus(el.settingsStatus, `OK — model responded: "${text.trim().slice(0, 40)}"`, "success");
  } catch (err) {
    setStatus(el.settingsStatus, err.message, "error");
  }
}

async function exportRecords() {
  const blob = new Blob([JSON.stringify(records, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `audio-transcripts-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

async function wipeRecords() {
  if (!window.confirm(`Delete all ${records.length} transcripts? This cannot be undone.`)) return;
  records = [];
  await saveRecords();
  renderLibrary();
  populateTranscriptSelect();
  showToast("🗑️ All transcripts deleted.");
}

/* ---------- theme ---------- */
async function toggleTheme() {
  const next = el.themeToggle.checked ? "dark" : "light";
  document.body.classList.toggle("dark", next === "dark");
  await chrome.storage.local.set({ [STORAGE_KEYS.theme]: next });
}

/* ---------- init ---------- */
async function init() {
  await loadAll();
  await scanPage();
  renderLibrary();
  populateTranscriptSelect();
  renderChatEmpty();

  el.rescanBtn.addEventListener("click", scanPage);

  chrome.storage.onChanged.addListener((changes) => {
    if (changes[STORAGE_KEYS.records]) {
      records = changes[STORAGE_KEYS.records].newValue || [];
      renderLibrary();
      populateTranscriptSelect();
    }
  });
  el.themeToggle.addEventListener("change", toggleTheme);
  el.searchInput.addEventListener("input", renderLibrary);

  el.askBtn.addEventListener("click", handleAsk);
  el.chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); handleAsk(); }
  });
  el.clearChatBtn.addEventListener("click", () => { chatHistory = []; renderChat(); });

  el.saveSettingsBtn.addEventListener("click", saveSettings);
  el.testKeyBtn.addEventListener("click", testKey);
  el.exportBtn.addEventListener("click", exportRecords);
  el.wipeBtn.addEventListener("click", wipeRecords);
}

init();
