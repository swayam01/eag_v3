// Gemini REST wrapper with function-calling support.
// Used by both the popup (via dynamic import) and the service worker.

const GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models";

export async function generate({ apiKey, model, contents, tools, systemInstruction, temperature }) {
  if (!apiKey) throw new Error("Missing Gemini API key. Open Settings and paste your key.");

  const url = `${GEMINI_BASE}/${encodeURIComponent(model)}:generateContent?key=${encodeURIComponent(apiKey)}`;

  const body = { contents };
  if (tools) body.tools = tools;
  if (systemInstruction) body.systemInstruction = { parts: [{ text: systemInstruction }] };
  if (typeof temperature === "number") body.generationConfig = { temperature };

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
  const candidate = data?.candidates?.[0];
  if (!candidate) throw new Error("Gemini returned no candidates.");
  return candidate.content; // { role: 'model', parts: [...] }
}

// Simple text-only helper for the "test API key" button etc.
export async function generateText({ apiKey, model, prompt, temperature }) {
  const content = await generate({
    apiKey,
    model,
    contents: [{ role: "user", parts: [{ text: prompt }] }],
    temperature
  });
  return content.parts.map((p) => p.text).filter(Boolean).join("\n");
}
