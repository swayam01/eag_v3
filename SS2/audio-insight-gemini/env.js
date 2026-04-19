// Reads the extension's bundled .env file at runtime.
// Loaded as a plain <script>; exposes a global `loadEnv()` returning a cached promise.

let _envPromise = null;

function loadEnv() {
  if (_envPromise) return _envPromise;
  _envPromise = (async () => {
    try {
      const res = await fetch(chrome.runtime.getURL(".env"));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const text = await res.text();
      return parseEnv(text);
    } catch (err) {
      console.warn("loadEnv failed:", err.message);
      return {};
    }
  })();
  return _envPromise;
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
