# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

This repo is a container for multiple independent assignments (`SS1`, `SS2`, …). Each subdirectory is its own self-contained project with no shared build system, package manager, or tooling at the repo root.

- [SS1/research-clip-extension/](SS1/research-clip-extension/) — "Research Clip", a Manifest V3 Chrome extension (vanilla JS/HTML/CSS, no build step).
- [SS2/research-clip-gemini/](SS2/research-clip-gemini/) — "Research Clip + Gemini", extends SS1 with Gemini Flash Lite for auto-summarization, tag suggestion, and a chat-with-your-clips feature.
- [SS2/audio-insight-gemini/](SS2/audio-insight-gemini/) — "Audio Insight", detects audio/video on pages, transcribes with Gemini (multimodal), stores transcripts with summaries, and supports Q&A over them.
- [SS2/.env](SS2/.env) — holds `GEMINI_API_KEY` for dev reference only; Chrome extensions can't read `.env` files, so the key is pasted into each extension's Settings tab at runtime.

When asked to "add a feature" or "fix a bug" without a path, ask which subproject — they are unrelated.

## SS1 — Research Clip Chrome extension

### Running / testing

There is no build, bundler, linter, or test runner. To exercise changes:

1. `chrome://extensions/` → enable **Developer mode** → **Load unpacked** → select [SS1/research-clip-extension/](SS1/research-clip-extension/).
2. After editing files, click the reload icon on the extension card in `chrome://extensions/`. For `content.js` changes, also reload the target web page.
3. Debug the popup via right-click on the extension icon → **Inspect popup**. Debug `content.js` via the target page's DevTools.

### Architecture

Two JS contexts communicate via `chrome.runtime` messaging:

- [popup.js](SS1/research-clip-extension/popup.js) runs in the popup window. It owns all UI state, persists clips to `chrome.storage.local` under the key `researchClipItems`, and persists theme under `researchClipTheme`. All CRUD, search, and rendering lives here — rendering uses the `<template id="itemTemplate">` in [popup.html](SS1/research-clip-extension/popup.html) cloned per item rather than a framework.
- [content.js](SS1/research-clip-extension/content.js) is injected into every page at `document_idle` and only responds to one message type — `GET_PAGE_CONTEXT` — returning `{ title, url, selectedText }` from `window.getSelection()`.

`popup.js → fetchPageContext()` sends `GET_PAGE_CONTEXT` to the active tab. If the content script isn't reachable (e.g. `chrome://` pages, just-installed state), it falls back to `chrome.tabs.query` data — preserve this fallback when editing.

Clip records are plain objects: `{ id, title, url, selectedText, manualNote, tags[], createdAt, updatedAt }`. IDs are generated in-page via `Date.now() + random hex`; there is no backend.

### Manifest constraints

[manifest.json](SS1/research-clip-extension/manifest.json) requests `storage`, `activeTab`, `scripting`, and `<all_urls>`. If you add features that touch new Chrome APIs (e.g. `tabs.captureVisibleTab`, `downloads`), update `permissions` accordingly — the extension will silently fail otherwise.

## SS2 — Research Clip + Gemini

Same load-unpacked workflow as SS1 (point Chrome at [SS2/research-clip-gemini/](SS2/research-clip-gemini/)). Inherits SS1's popup ↔ content-script pattern and adds:

- [gemini.js](SS2/research-clip-gemini/gemini.js) — thin REST wrapper for `generativelanguage.googleapis.com`. Three entry points: `callGemini` (raw), `enrichClip` (returns `{summary, suggestedTags, keyClaims}` as strict JSON), `askClips` (answers a question over the whole clip corpus, citing clip IDs inline as `[id]`).
- Tabbed popup ([popup.html](SS2/research-clip-gemini/popup.html)): **Save**, **Clips**, **Ask**, **Settings**. Tab switching is CSS-only (`.panel.active`) — keep that pattern when adding tabs rather than introducing a router.
- Clip records extend SS1's shape with `summary`, `keyClaims`, and `aiTags` (subset of `tags` flagged with ✨ in the UI). Re-enriching strips previous `aiTags` before merging in new ones, so AI tags don't accumulate across runs.

### Gemini-specific gotchas

- **Popup lifecycle kills in-flight requests.** MV3 popup JS dies on close, aborting `fetch`. `handleSave` and `handleAsk` therefore block with a visible "working" state — don't move enrichment off-popup without also moving it into a service worker.
- **API key ships client-side.** `chrome.storage.local` is not a secret store — the key is accessible to anyone with the unpacked extension. Fine for a personal experiment; if we ever distribute, add a proxy server and strip the key from the client.
- **Manifest host permission.** `https://generativelanguage.googleapis.com/*` is listed in `host_permissions`. Any new external API needs to be added there or `fetch` will fail silently with a CORS-ish error.
- **Model ID.** Default is `gemini-2.5-flash-lite`. "Flash Lite 3.0" is not a known Google model ID as of the last update; user can override in Settings.

### When changing the enrichment prompt

`enrichClip` relies on `responseMimeType: "application/json"` plus strict shape instructions. If you loosen the prompt, also add a `JSON.parse` fallback in [gemini.js](SS2/research-clip-gemini/gemini.js) — right now a malformed response surfaces as an unhelpful parse error to the user.

## SS2 — Audio Insight + Gemini

Load-unpacked at [SS2/audio-insight-gemini/](SS2/audio-insight-gemini/). Same MV3 pattern as above (popup + content script + shared Gemini API key in Settings).

### Architecture

- [content.js](SS2/audio-insight-gemini/content.js) — responds to `SCAN_MEDIA`. Scans for `<audio>`/`<video>` elements, extracts `{src, mimeType, duration, label}`. Skips `blob:` URLs (they can't be fetched cross-context). Falls back to `<source>` children and `currentSrc`.
- [gemini.js](SS2/audio-insight-gemini/gemini.js) — extends the text-only wrapper from research-clip-gemini with **multimodal** support:
  - `fetchAudioAsBase64(url)` — fetches audio, caps at 20 MB, returns `{base64, mimeType}`.
  - `transcribeAudio(key, model, audioUrl)` — sends audio as `inlineData` part to Gemini, returns verbatim transcript.
  - `transcribeAudioBlob(key, model, blob)` — same but accepts a raw `Blob` directly (used for mic recordings). Shares the same base64 encoding and size cap.
  - `summarizeTranscript(key, model, transcript, title)` — text-only call, returns `{summary, keyPoints[], topics[]}` as strict JSON.
  - `askTranscript` / `askAllTranscripts` — Q&A over one or all transcripts.
- [popup.js](SS2/audio-insight-gemini/popup.js) — tabs: **Detect** (scan page + manual URL), **Library** (stored transcripts with summaries), **Ask** (single or cross-library Q&A), **Settings**.

### Key differences from research-clip-gemini

- **Multimodal Gemini calls.** `callGemini` accepts a `parts` array instead of a single string, enabling `inlineData` (base64 audio). If adapting prompts, keep the parts-based signature.
- **Two-step save flow.** Transcription and summarization are separate Gemini calls. If transcription succeeds but summary fails, the transcript is still saved — the summary field will be empty.
- **Ask modes.** Users can Q&A over a single transcript (full text sent) or across all transcripts (truncated to 4K chars each to fit context). When corpus grows large, the truncation in `buildAskCorpus` / `askAllTranscripts` may need tuning.
- **No content-script fallback for media.** Unlike research-clip-gemini which falls back to `chrome.tabs.query` for page context, if the content script can't run (e.g. `chrome://` pages), the Detect tab simply shows "No audio found."

### Limits to be aware of

- `blob:` and `mediaSource:` URLs are skipped — JavaScript-based players (Spotify, SoundCloud, YouTube) won't be detected.
- The 20 MB inline data cap means ~30 min of 128kbps MP3. Longer audio needs the Gemini File API (upload → reference), which is not implemented.
- **Mic recording** uses `MediaRecorder` (webm/opus) in the popup. The recorded blob lives in JS memory — closing the popup before transcribing loses it. The browser prompts for mic permission on first use; no extra manifest permission is needed.
