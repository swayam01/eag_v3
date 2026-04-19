// Reads the extension's bundled .env file at runtime.
// Chrome extensions can fetch their own packaged files via chrome.runtime.getURL().

let cached = null;

export async function loadEnv() {
  if (cached) return cached;
  try {
    const res = await fetch(chrome.runtime.getURL(".env"));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const text = await res.text();
    cached = parseEnv(text);
  } catch (err) {
    console.warn("loadEnv failed:", err.message);
    cached = {};
  }
  return cached;
}

function parseEnv(text) {
  const out = {};
  text.split(/\r?\n/).forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) return;
    const eq = line.indexOf("=");
    if (eq === -1) return;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    out[key] = value;
  });
  return out;
}
