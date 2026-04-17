# Audio Insight 

A Manifest V3 Chrome extension that detects audio/video on any webpage, transcribes it using Gemini, stores transcripts with AI-generated summaries, and lets you Q&A over them.

Demo

![Demo](https://youtu.be/JnicJGIZrIw)

## Features

- **Detect** — auto-scans the current page for `<audio>` and `<video>` elements. Also supports pasting a direct audio URL or **recording live audio from your microphone**.
- **Transcribe** — sends audio to Gemini for verbatim transcription (supports mp3, wav, ogg, flac, aac, m4a, webm, mp4).
- **Summarize** — after transcribing, Gemini generates a 2–4 sentence summary, key points, and topic tags.
- **Ask** — Q&A over a single transcript or across your entire library. Answers cite transcript IDs as clickable chips.
- **Library** — search, copy, or delete saved transcripts. Summary + key points shown up front so you know the gist before diving in.

## Load it

1. `chrome://extensions/` → enable **Developer mode** → **Load unpacked** → select this folder.
2. Click the extension icon → **Settings** tab.
3. Paste your Gemini API key (from `SS2/.env`) → **Save Settings** → **Test API key**.
4. Default model is `gemini-2.5-flash-lite`. Use `gemini-2.5-flash` for better transcription of noisy/multilingual audio.

## Architecture

- [content.js](content.js) — injected into every page. Responds to `SCAN_MEDIA` by finding all `<audio>`/`<video>` elements and returning `{src, mimeType, duration, label}` for each.
- [gemini.js](gemini.js) — Gemini REST wrapper:
  - `transcribeAudio(key, model, audioUrl)` — fetches audio → base64 → multimodal Gemini call
  - `transcribeAudioBlob(key, model, blob)` — same but takes a raw Blob (used for mic recordings)
  - `summarizeTranscript(key, model, transcript, title)` — returns `{summary, keyPoints, topics}` as JSON
  - `askTranscript(key, model, record, question, history)` — Q&A over one transcript
  - `askAllTranscripts(key, model, records, question, history)` — Q&A across all, citing IDs as `[id]`
- [popup.js](popup.js) — main logic: scan page, transcription flow, library CRUD, chat, settings.
- [popup.html](popup.html) — tabbed UI: Detect · Library · Ask · Settings.

## Data model

Each transcript record stored in `chrome.storage.local`:
```
{ id, title, pageUrl, audioUrl, transcript, summary, keyPoints[], topics[], createdAt, updatedAt }
```

## Known limits

- **Mic recording** — uses `MediaRecorder` (webm/opus). The browser will prompt for mic permission on first use. Recording stays in memory until you transcribe or discard — closing the popup loses it.
- **20 MB max audio** — `fetchAudioAsBase64` and `blobToBase64` cap at 20 MB (Gemini inline data limit). Longer podcasts/recordings may need trimming.
- **blob: URLs not supported** — streaming players (Spotify, SoundCloud) use blob/media-source URLs that can't be fetched. Only standard `<audio>/<video>` with accessible `src` attributes work.
- **Popup must stay open** — MV3 popup JS dies on close, killing in-flight fetch/Gemini calls.
- **API key is client-side** — stored in `chrome.storage.local`, visible to anyone with access to the extension.
