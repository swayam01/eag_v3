const STORAGE_KEYS = {
  records: "audioInsightRecords",
  apiKey: "audioInsightApiKey",
  model: "audioInsightModel"
};
const DEFAULT_MODEL = "gemini-2.5-flash-lite";

const ui = {
  recordBtn: document.getElementById("recordBtn"),
  timer: document.getElementById("timer"),
  dot: document.getElementById("dot"),
  previewSection: document.getElementById("previewSection"),
  preview: document.getElementById("preview"),
  labelInput: document.getElementById("labelInput"),
  transcribeBtn: document.getElementById("transcribeBtn"),
  discardBtn: document.getElementById("discardBtn"),
  status: document.getElementById("status")
};

let mediaRecorder = null;
let chunks = [];
let recordedBlob = null;
let startTime = null;
let timerInterval = null;

function setStatus(text, kind) {
  ui.status.textContent = text;
  ui.status.classList.remove("hidden", "success", "error", "working");
  if (kind) ui.status.classList.add(kind);
  if (!text) ui.status.classList.add("hidden");
}

function updateTimer() {
  if (!startTime) return;
  const s = Math.floor((Date.now() - startTime) / 1000);
  ui.timer.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunks = [];
    recordedBlob = null;

    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus" : "audio/webm";
    mediaRecorder = new MediaRecorder(stream, { mimeType });

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data);
    };

    mediaRecorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      clearInterval(timerInterval);
      recordedBlob = new Blob(chunks, { type: mimeType });
      ui.preview.src = URL.createObjectURL(recordedBlob);
      ui.previewSection.classList.remove("hidden");
      ui.recordBtn.textContent = "Start Recording";
      ui.recordBtn.classList.remove("recording");
      ui.timer.classList.add("hidden");
      ui.dot.classList.add("hidden");
    };

    mediaRecorder.start(1000);
    startTime = Date.now();
    timerInterval = setInterval(updateTimer, 500);

    ui.timer.classList.remove("hidden");
    ui.dot.classList.remove("hidden");
    ui.previewSection.classList.add("hidden");
    ui.recordBtn.textContent = "Stop Recording";
    ui.recordBtn.classList.add("recording");
    setStatus("");
  } catch (err) {
    setStatus(`Mic error: ${err.message}`, "error");
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }
  startTime = null;
}

function discard() {
  recordedBlob = null;
  chunks = [];
  ui.previewSection.classList.add("hidden");
  if (ui.preview.src) {
    URL.revokeObjectURL(ui.preview.src);
    ui.preview.removeAttribute("src");
  }
  setStatus("");
}

function generateId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

async function transcribeAndSave() {
  if (!recordedBlob) return;

  const data = await chrome.storage.local.get([STORAGE_KEYS.apiKey, STORAGE_KEYS.model]);
  let apiKey = data[STORAGE_KEYS.apiKey];
  if (!apiKey) {
    const env = await loadEnv();
    apiKey = env.GEMINI_API_KEY || "";
  }
  const model = data[STORAGE_KEYS.model] || DEFAULT_MODEL;

  if (!apiKey) {
    setStatus("No API key set. Open the extension popup → Settings and add your Gemini key.", "error");
    return;
  }

  ui.transcribeBtn.disabled = true;
  ui.discardBtn.disabled = true;
  setStatus("🎧 Transcribing audio…", "working");

  try {
    const transcript = await transcribeAudioBlob(apiKey, model, recordedBlob);

    setStatus("✨ Generating summary…", "working");
    let summary = "", keyPoints = [], topics = [];
    try {
      const label = ui.labelInput.value.trim() || "Mic recording";
      const result = await summarizeTranscript(apiKey, model, transcript, label);
      summary = result.summary;
      keyPoints = result.keyPoints;
      topics = result.topics;
    } catch (e) {
      console.warn("Summary failed:", e);
    }

    const now = new Date().toISOString();
    const record = {
      id: generateId(),
      title: ui.labelInput.value.trim() || `Mic recording ${new Date().toLocaleString()}`,
      pageUrl: "",
      audioUrl: "(mic recording)",
      transcript,
      summary,
      keyPoints,
      topics,
      createdAt: now,
      updatedAt: now
    };

    const existing = await chrome.storage.local.get(STORAGE_KEYS.records);
    const records = Array.isArray(existing[STORAGE_KEYS.records]) ? existing[STORAGE_KEYS.records] : [];
    records.unshift(record);
    await chrome.storage.local.set({ [STORAGE_KEYS.records]: records });

    setStatus(`✅ Saved: "${record.title}". You can close this window.`, "success");
    discard();
  } catch (err) {
    setStatus(`Error: ${err.message}`, "error");
  } finally {
    ui.transcribeBtn.disabled = false;
    ui.discardBtn.disabled = false;
  }
}

ui.recordBtn.addEventListener("click", () => {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    stopRecording();
  } else {
    startRecording();
  }
});

ui.transcribeBtn.addEventListener("click", transcribeAndSave);
ui.discardBtn.addEventListener("click", discard);
