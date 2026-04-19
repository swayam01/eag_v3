// Tool implementations + Gemini function declarations.
// Each tool is an async JS function; declarations describe the schema to Gemini.

const PRICE_HISTORY_KEY = "marketPulsePriceHistory";
const SETTINGS_KEY = "marketPulseSettings";
const OUNCE_TO_GRAMS = 31.1035;

// ---------- Gemini function declarations ----------
export const TOOL_DECLARATIONS = [
  {
    name: "get_price",
    description: "Fetch the current market price for a tracked asset. Returns the latest price. Also records the price in local history so calc_change can use it later.",
    parameters: {
      type: "object",
      properties: {
        asset: {
          type: "string",
          enum: ["gold", "silver", "usd_inr"],
          description: "Which asset to fetch. 'gold' and 'silver' return INR per 10 grams; 'usd_inr' returns INR per 1 USD."
        }
      },
      required: ["asset"]
    }
  },
  {
    name: "calc_change",
    description: "Compute the change for an asset from locally stored history. Returns day-over-day %, 7-day %, and the raw prices used. Returns zeros if no history exists yet.",
    parameters: {
      type: "object",
      properties: {
        asset: {
          type: "string",
          enum: ["gold", "silver", "usd_inr"]
        }
      },
      required: ["asset"]
    }
  },
  {
    name: "search_news",
    description: "Search Google News for recent headlines on a topic. Returns an array of {title, source, publishedAt, link}. Use this to explain significant price moves.",
    parameters: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "Search query, e.g. 'gold price federal reserve' or 'rupee depreciation'"
        },
        max_results: {
          type: "integer",
          description: "Maximum number of headlines to return (1-10). Defaults to 5."
        }
      },
      required: ["query"]
    }
  },
  {
    name: "send_telegram",
    description: "Send a message to the user's configured Telegram chat. Use Markdown formatting. Call this ONCE at the end with the final report.",
    parameters: {
      type: "object",
      properties: {
        message: {
          type: "string",
          description: "The report text (Markdown). Keep under 4000 characters."
        }
      },
      required: ["message"]
    }
  }
];

// ---------- Registry ----------
export const TOOLS = {
  get_price,
  calc_change,
  search_news,
  send_telegram
};

// ---------- Implementations ----------

async function get_price({ asset }) {
  if (asset === "gold") {
    const usdPerOz = await fetchGoldApi("XAU");
    const usdInr = await fetchUsdInr();
    const inrPer10g = (usdPerOz / OUNCE_TO_GRAMS) * usdInr * 10;
    const price = Math.round(inrPer10g);
    await appendHistory(asset, price);
    return { asset, price, unit: "INR per 10g", source: "gold-api.com + open.er-api.com" };
  }
  if (asset === "silver") {
    const usdPerOz = await fetchGoldApi("XAG");
    const usdInr = await fetchUsdInr();
    const inrPerKg = (usdPerOz / OUNCE_TO_GRAMS) * usdInr * 1000;
    const price = Math.round(inrPerKg);
    await appendHistory(asset, price);
    return { asset, price, unit: "INR per kg", source: "gold-api.com + open.er-api.com" };
  }
  if (asset === "usd_inr") {
    const rate = await fetchUsdInr();
    const price = Number(rate.toFixed(4));
    await appendHistory(asset, price);
    return { asset, price, unit: "INR per USD", source: "open.er-api.com" };
  }
  throw new Error(`Unknown asset: ${asset}`);
}

async function calc_change({ asset }) {
  const data = await chrome.storage.local.get(PRICE_HISTORY_KEY);
  const history = (data[PRICE_HISTORY_KEY] || []).filter((h) => h.asset === asset);
  if (history.length < 2) {
    return { asset, dayOverDayPct: 0, sevenDayPct: 0, latest: history.at(-1)?.price ?? null, note: "Not enough history yet — save more snapshots over time." };
  }
  history.sort((a, b) => a.ts - b.ts);
  const latest = history.at(-1);
  const now = latest.ts;
  const oneDayAgo = findClosest(history, now - 86400000);
  const sevenDayAgo = findClosest(history, now - 7 * 86400000);
  return {
    asset,
    latest: latest.price,
    dayOverDayPct: pct(latest.price, oneDayAgo?.price),
    sevenDayPct: pct(latest.price, sevenDayAgo?.price),
    samplesUsed: { latest: latest.ts, oneDayAgo: oneDayAgo?.ts, sevenDayAgo: sevenDayAgo?.ts }
  };
}

async function search_news({ query, max_results = 5 }) {
  const url = `https://news.google.com/rss/search?q=${encodeURIComponent(query)}&hl=en-US&gl=US&ceid=US:en`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`News fetch failed: ${res.status}`);
  const xml = await res.text();
  const items = parseRssItems(xml).slice(0, Math.min(Math.max(1, max_results), 10));
  return { query, count: items.length, headlines: items };
}

async function send_telegram({ message }) {
  const data = await chrome.storage.local.get(SETTINGS_KEY);
  const settings = data[SETTINGS_KEY] || {};
  const token = settings.telegramBotToken;
  const chatId = settings.telegramChatId;
  if (!token || !chatId) {
    throw new Error("Telegram not configured. Paste bot token + chat ID in Settings.");
  }
  const url = `https://api.telegram.org/bot${token}/sendMessage`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text: message.slice(0, 4000),
      parse_mode: "Markdown"
    })
  });
  const raw = await res.text();
  if (!res.ok) throw new Error(`Telegram ${res.status}: ${raw}`);
  const parsed = JSON.parse(raw);
  return { ok: true, messageId: parsed?.result?.message_id };
}

// ---------- Helpers ----------

async function fetchGoldApi(symbol) {
  const res = await fetch(`https://api.gold-api.com/price/${symbol}`);
  if (!res.ok) throw new Error(`gold-api ${symbol} failed: ${res.status}`);
  const data = await res.json();
  if (typeof data.price !== "number") throw new Error(`Unexpected gold-api response: ${JSON.stringify(data)}`);
  return data.price;
}

async function fetchUsdInr() {
  const res = await fetch("https://open.er-api.com/v6/latest/USD");
  if (!res.ok) throw new Error(`exchange rate fetch failed: ${res.status}`);
  const data = await res.json();
  const inr = data?.rates?.INR;
  if (typeof inr !== "number") throw new Error("No INR rate in response.");
  return inr;
}

async function appendHistory(asset, price) {
  const data = await chrome.storage.local.get(PRICE_HISTORY_KEY);
  const history = Array.isArray(data[PRICE_HISTORY_KEY]) ? data[PRICE_HISTORY_KEY] : [];
  history.push({ asset, price, ts: Date.now() });
  const trimmed = history.slice(-500);
  await chrome.storage.local.set({ [PRICE_HISTORY_KEY]: trimmed });
}

function findClosest(history, targetTs) {
  let best = null;
  let bestDiff = Infinity;
  for (const h of history) {
    const diff = Math.abs(h.ts - targetTs);
    if (diff < bestDiff) { bestDiff = diff; best = h; }
  }
  return best;
}

function pct(current, previous) {
  if (!previous || !current) return 0;
  return Number((((current - previous) / previous) * 100).toFixed(2));
}

function parseRssItems(xml) {
  const items = [];
  const itemRegex = /<item>([\s\S]*?)<\/item>/g;
  let m;
  while ((m = itemRegex.exec(xml)) !== null) {
    const block = m[1];
    const title = extractTag(block, "title");
    const link = extractTag(block, "link");
    const pubDate = extractTag(block, "pubDate");
    const source = extractTag(block, "source");
    items.push({
      title: decodeEntities(stripCdata(title)),
      link: stripCdata(link),
      publishedAt: pubDate,
      source: decodeEntities(stripCdata(source))
    });
  }
  return items;
}

function extractTag(xml, tag) {
  const m = new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`).exec(xml);
  return m ? m[1].trim() : "";
}

function stripCdata(s) {
  return (s || "").replace(/^<!\[CDATA\[|\]\]>$/g, "");
}

function decodeEntities(s) {
  return (s || "")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}
