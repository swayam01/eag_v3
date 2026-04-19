# Market Pulse — Agentic AI 📈

A Manifest V3 Chrome extension where a Gemini-powered agent fetches gold, silver, and USD/INR prices, fetches news to explain significant moves, writes a narrative report, and delivers it to your Telegram — all autonomously, with every step visible in the UI.

## Demo

[https://youtu.be/JnicJGIZrIw](https://youtu.be/2QRMkW3U34w)

## What makes it *agentic*

The LLM is not called once. It loops:

```
User prompt
  ↓
LLM → decides to call get_price(gold)
  ↓  (tool runs, result goes back to LLM)
LLM → decides to call get_price(silver)
  ↓
LLM → decides to call calc_change for each
  ↓
LLM → sees gold moved +1.8% → decides to call search_news("gold price fed")
  ↓
LLM → writes a Markdown report
  ↓
LLM → calls send_telegram(message)
  ↓
LLM → returns a final confirmation
```

Each thought, tool call, and tool result is streamed live to the popup so you can watch the agent think.

## Four tools

| Tool | What it does |
|------|--------------|
| `get_price(asset)` | Fetches current gold (INR/10g), silver (INR/kg), or USD/INR from [gold-api.com](https://gold-api.com) + [open.er-api.com](https://open.er-api.com). Also appends to local price history. |
| `calc_change(asset)` | Reads stored history and returns day-over-day % and 7-day % change. |
| `search_news(query, max_results)` | Hits Google News RSS, parses items, returns `{title, source, link, publishedAt}`. |
| `send_telegram(message)` | POSTs to the Telegram Bot API using your saved bot token + chat ID. |

## Load it

1. `chrome://extensions/` → enable **Developer mode** → **Load unpacked** → select this folder.
2. Open the extension → **Settings** tab:
   - Paste your **Gemini API key** (needs a model that supports function calling — `gemini-2.5-flash` is the safe default; Flash Lite variants may not).
   - **Create a Telegram bot**: message `@BotFather` on Telegram → `/newbot` → copy the token.
   - **Get your chat ID**: send any message to your bot, then visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` and copy `result[0].message.chat.id`.
   - Paste token + chat ID → **Save Settings** → **Test Telegram** to verify.
3. **Schedule** tab → pick a time → toggle "Run daily" → save. Alarms fire while Chrome is running.
4. **Run** tab → click **Run Now** to kick off the agent immediately. Watch the trace populate in real time.

## Architecture

Four MV3 contexts:

- **Popup** ([popup.js](popup.js)) — UI only. Sends `RUN_AGENT` to the service worker, listens for `AGENT_STEP` messages to render the live trace.
- **Service worker** ([background.js](background.js)) — owns `chrome.alarms`, executes agent runs, persists results. Runs survive popup closure.
- **Agent loop** ([agent.js](agent.js)) — the Gemini function-calling orchestrator. Maintains `contents` (full conversation), invokes tools, emits trace events.
- **Tools** ([tools.js](tools.js)) — tool implementations + Gemini `functionDeclarations` schemas.

## Why runs happen in the service worker, not the popup

A Gemini agent run makes 6–10 API calls. MV3 popup JS dies the instant the popup closes, aborting every pending fetch. So the popup just *dispatches* a `RUN_AGENT` message; the service worker does the heavy lifting and broadcasts `AGENT_STEP` events back. The popup renders them if it's still open; otherwise the full trace is persisted to `chrome.storage.local` under `marketPulseReports` and viewable in the **History** tab.

## Known limits

- **Alarms only fire while Chrome is running.** Closed browser = missed run. The next open will *not* fire a missed alarm; it fires on the next scheduled time.
- **Free data sources have rate limits and can lag.** `gold-api.com` and `open.er-api.com` are unauthenticated; they occasionally return stale values. Good enough for a daily briefing, not for intraday trading.
- **Google News RSS is unofficial.** It works today but Google has killed similar endpoints before.
- **API keys are client-side.** Both the Gemini key and the Telegram bot token sit in `chrome.storage.local`. Don't distribute the unpacked extension.
- **Function calling needs a capable model.** Default `gemini-2.5-flash`. Flash Lite may silently skip tool use and dump a plain-text answer.
