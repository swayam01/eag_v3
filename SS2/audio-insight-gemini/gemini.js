const GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models";
const MAX_INLINE_BYTES = 20 * 1024 * 1024;

async function callGemini(apiKey, model, parts, { responseMimeType, temperature } = {}) {
  if (!apiKey) throw new Error("Missing Gemini API key. Open Settings and paste your key.");
  const url = `${GEMINI_BASE}/${encodeURIComponent(model)}:generateContent?key=${encodeURIComponent(apiKey)}`;
  const body = {
    contents: [{ role: "user", parts }],
    generationConfig: {}
  };
  if (responseMimeType) body.generationConfig.responseMimeType = responseMimeType;
  if (typeof temperature === "number") body.generationConfig.temperature = temperature;

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const raw = await res.text();
  if (!res.ok) {
    let detail = raw;
    try { detail = JSON.parse(raw)?.error?.message || raw; } catch {}
    throw new Error(`Gemini ${res.status}: ${detail}`);
  }
  const data = JSON.parse(raw);
  const text = data?.candidates?.[0]?.content?.parts?.map((p) => p.text).filter(Boolean).join("\n");
  if (!text) throw new Error("Gemini returned no text. The response may have been blocked by safety filters.");
  return text;
}

function callGeminiText(apiKey, model, prompt, opts) {
  return callGemini(apiKey, model, [{ text: prompt }], opts);
}

async function fetchAudioAsBase64(audioUrl) {
  const res = await fetch(audioUrl);
  if (!res.ok) throw new Error(`Failed to fetch audio: HTTP ${res.status}`);
  const blob = await res.blob();
  if (blob.size > MAX_INLINE_BYTES) {
    throw new Error(`Audio too large (${(blob.size / 1024 / 1024).toFixed(1)} MB). Max is 20 MB.`);
  }
  const mimeType = blob.type || "audio/mpeg";
  const buffer = await blob.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  const base64 = btoa(binary);
  return { base64, mimeType };
}

const TRANSCRIBE_PROMPT = "Transcribe this audio verbatim. Output only the transcription text, no timestamps, no speaker labels, no commentary. If the audio is not in English, transcribe it and then provide the English translation after a blank line.";

async function transcribeAudio(apiKey, model, audioUrl) {
  const { base64, mimeType } = await fetchAudioAsBase64(audioUrl);
  const parts = [
    { inlineData: { mimeType, data: base64 } },
    { text: TRANSCRIBE_PROMPT }
  ];
  return callGemini(apiKey, model, parts, { temperature: 0.1 });
}

async function blobToBase64(blob) {
  if (blob.size > MAX_INLINE_BYTES) {
    throw new Error(`Recording too large (${(blob.size / 1024 / 1024).toFixed(1)} MB). Max is 20 MB.`);
  }
  const buffer = await blob.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

async function transcribeAudioBlob(apiKey, model, blob) {
  const mimeType = blob.type || "audio/webm";
  const base64 = await blobToBase64(blob);
  const parts = [
    { inlineData: { mimeType, data: base64 } },
    { text: TRANSCRIBE_PROMPT }
  ];
  return callGemini(apiKey, model, parts, { temperature: 0.1 });
}

async function summarizeTranscript(apiKey, model, transcript, pageTitle) {
  const prompt = `You are a research assistant. Analyze this audio transcript and return strict JSON:

{
  "summary": "2-4 sentence summary capturing the main topic and key points",
  "keyPoints": ["3-6 short bullet points of the most important facts/claims/ideas"],
  "topics": ["3-5 short lowercase topic tags"]
}

Context:
Title: ${pageTitle || "(untitled)"}

Transcript:
${transcript.slice(0, 30000)}

Respond with ONLY the JSON object. No markdown fencing, no preamble.`;

  const text = await callGeminiText(apiKey, model, prompt, {
    responseMimeType: "application/json",
    temperature: 0.3
  });
  const parsed = JSON.parse(text);
  return {
    summary: String(parsed.summary || "").trim(),
    keyPoints: Array.isArray(parsed.keyPoints) ? parsed.keyPoints.map((p) => String(p).trim()).filter(Boolean) : [],
    topics: Array.isArray(parsed.topics) ? parsed.topics.map((t) => String(t).toLowerCase().trim()).filter(Boolean) : []
  };
}

async function askTranscript(apiKey, model, record, question, history = []) {
  const historyBlock = history.length
    ? `\nPrevious turns:\n${history.map((h) => `${h.role === "user" ? "USER" : "ASSISTANT"}: ${h.text}`).join("\n")}\n`
    : "";

  const prompt = `You help the user understand an audio transcript.

Title: ${record.title || "(untitled)"}
Source: ${record.pageUrl || "(unknown)"}
Summary: ${record.summary || "(none)"}
Key points:
${(record.keyPoints || []).map((p) => `- ${p}`).join("\n") || "(none)"}

Full transcript:
${record.transcript.slice(0, 60000)}
${historyBlock}
Current question: ${question}

Instructions:
- Answer using ONLY information from the transcript above.
- Quote relevant passages when helpful. Use quotation marks for direct quotes.
- If the answer is not in the transcript, say so.
- Be concise.`;

  return callGeminiText(apiKey, model, prompt, { temperature: 0.4 });
}

async function askAllTranscripts(apiKey, model, records, question, history = []) {
  if (!records.length) throw new Error("No transcripts saved yet.");

  const corpus = records.map((r) => ({
    id: r.id,
    title: r.title,
    summary: r.summary || "",
    keyPoints: r.keyPoints || [],
    topics: r.topics || [],
    transcript: (r.transcript || "").slice(0, 4000)
  }));

  const historyBlock = history.length
    ? `\nPrevious turns:\n${history.map((h) => `${h.role === "user" ? "USER" : "ASSISTANT"}: ${h.text}`).join("\n")}\n`
    : "";

  const prompt = `You help the user search across their saved audio transcripts.

Here are the transcripts (JSON):
${JSON.stringify(corpus, null, 2)}
${historyBlock}
Question: ${question}

Instructions:
- Answer using ONLY the transcripts above.
- Cite transcript IDs inline as [id] when referencing a specific one.
- If no transcript is relevant, say so and suggest what to transcribe.
- Be concise.`;

  return callGeminiText(apiKey, model, prompt, { temperature: 0.4 });
}
