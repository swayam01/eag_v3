# SS5 — Market-Aware Competitor Analysis Agent

An evolution of [SS4](../../SS4/competitor-analysis-agent) with two new
capabilities:

1. **Configurable market context.** Every run is scoped to a `MarketConfig`
   (region, vertical, segment, pricing tier, geo strictness, must-have /
   exclude keywords). The agent filters, scores, and explains each
   competitor against that config — a global player only loosely relevant
   to your region gets `market_fit_score: 3`, while an in-region, in-tier,
   in-segment match gets `9–10`.
2. **A system prompt that qualifies on the Prompt Evaluation Assistant
   rubric.** All 9 criteria — explicit reasoning, structured output, tool
   separation, conversation loop, instructional framing, self-checks,
   reasoning-type awareness, fallbacks, overall clarity — are answered
   `true`. See [`PROMPT_EVAL.json`](PROMPT_EVAL.json) for the verdict and
   [`PROMPT_EVAL.md`](PROMPT_EVAL.md) for the rubric.

The rest — MCP server with 10 tools, Prefab UI dashboard, Tavily + DDG
search, file-locked JSON store, PDF export — is inherited from SS4.

---

## Quickstart

```bash
cd SS5/market-aware-competitor-agent
uv sync
cp .env.example .env                      # fill GEMINI_API_KEY (+ optional TAVILY_API_KEY)

# Default: Tile Vision AI demo, scoped to global market
uv run competitor-agent

# Scoped to the Indian B2C interior-design market
uv run competitor-agent --market-config markets/india_b2c_interior.json

# Same product, scoped to NA enterprise CRM (different market = different competitor set)
uv run competitor-agent \
  --product-name "Acme CRM" \
  --product-description "AI-first pipeline CRM for inside sales teams" \
  --category "B2B CRM" \
  --market-config markets/us_enterprise_crm.json \
  -n 6 --clear
```

When the run finishes a Prefab dashboard opens at `http://127.0.0.1:8765`
showing a **Market scope** banner, your product card, a comparison table
with a `Market fit` column, expandable SWOT cards, and a positioning
summary.

---

## Configuring the market

### Option A — `--market-config <file>` (JSON or YAML)

Ship one config per market and reuse it across products. Examples are
in [`markets/`](markets):

| File | Region | Vertical | Segment / Tier |
|---|---|---|---|
| `markets/global_default.json` | Global | — | Mixed / mixed |
| `markets/india_b2c_interior.json` | India | interior design tech | B2C / budget |
| `markets/us_enterprise_crm.json` | North America | B2B CRM SaaS | B2B / enterprise |
| `markets/southeast_asia_fintech.json` | Southeast Asia | consumer fintech | B2C / budget |

### Option B — individual `--market-*` flags

```bash
uv run competitor-agent \
  --product-name "Bolt EV Charge" \
  --category "EV charging app" \
  --market-region "Europe" \
  --market-countries "Germany,France,Netherlands" \
  --market-industry "EV charging networks" \
  --market-segment B2C \
  --market-pricing-tier mid-market \
  --market-geo-strictness strict \
  --market-must-have "EV,charging,Europe" \
  --market-exclude "fleet-only,US-only" \
  --market-notes "Buyers want OCPI roaming + per-kWh pricing in EUR."
```

File values are loaded first; CLI flags override individual keys.

### Full flag list

| Flag | Purpose |
|---|---|
| `--market-config PATH` | Load MarketConfig from a JSON/YAML file. |
| `--market-region` | Region label (`India`, `North America`, `Global`, …). |
| `--market-countries` | Comma-separated country whitelist. |
| `--market-industry` | Industry / vertical. |
| `--market-segment` | `B2B \| B2C \| B2B2C \| B2G \| Mixed`. |
| `--market-pricing-tier` | `budget \| mid-market \| premium \| enterprise \| mixed`. |
| `--market-channels` | Comma-separated channels (`web app,iOS,Android,…`). |
| `--market-language` | Primary content language. |
| `--market-geo-strictness` | `strict` (HQ in region) / `primary` (serves region) / `loose` (any). |
| `--market-must-have` | Comma-separated must-have keywords. |
| `--market-exclude` | Comma-separated disqualifying keywords. |
| `--market-notes` | Free-form context the agent should weigh. |

### How the market drives behaviour

Every competitor saved by the agent gets two new fields:

```json
{
  "market_fit_score": 9,
  "market_fit_reason": "HQ in Bengaluru (India), B2C tile-visualizer pricing tier matches budget segment."
}
```

The dashboard renders a `Market fit` badge on each card and a sortable
column in the comparison table. The PDF export adds a **Market scope**
section at the top and a fit column in the comparison.

The scoring rubric (in the system prompt) is:

| Score | Meaning |
|---|---|
| **10** | HQ in region + pricing tier match + segment match |
| **6**  | Serves region but pricing tier or segment is off |
| **3**  | Global player only loosely relevant |
| **0**  | Does not belong — don't save |

`geo_strictness` controls how aggressively off-region candidates are
dropped before they're even fetched.

---

## Prompt qualification (the rubric reason this is SS5, not SS4.1)

The agent's `SYSTEM_INSTRUCTION_TEMPLATE` was rewritten to satisfy all
nine criteria of the Prompt Evaluation Assistant rubric (full rubric in
[`PROMPT_EVAL.md`](PROMPT_EVAL.md)).

Run the evaluator yourself:

```bash
uv run prompt-eval
# writes PROMPT_EVAL.json, also prints to stdout
```

Sample verdict (see [`PROMPT_EVAL.json`](PROMPT_EVAL.json)):

```json
{
  "explicit_reasoning": true,
  "structured_output": true,
  "tool_separation": true,
  "conversation_loop": true,
  "instructional_framing": true,
  "internal_self_checks": true,
  "reasoning_type_awareness": true,
  "fallbacks": true,
  "overall_clarity": "Excellent. The prompt enforces a labelled per-turn protocol..."
}
```

### Where each criterion is satisfied

| Rubric criterion | Where in the prompt |
|---|---|
| Explicit reasoning instructions | `REASONING PROTOCOL` block — every turn opens with `THOUGHT [<type>]: …`. |
| Structured output format | Labelled blocks `THOUGHT / PLAN / SELF_CHECK / FALLBACK / CONFIDENCE`, plus a strict `FINAL:` block to terminate. |
| Tool separation | Reasoning is text; tool use is Gemini function-call parts emitted *after* the text block. |
| Conversation loop | Function responses are fed back via `Part.from_function_response` and the agent maintains MARKET_CONFIG as durable context across turns. |
| Instructional framing | The prompt ends with a concrete `EXAMPLE TURN` showing the exact format. |
| Internal self-checks | Mandatory `SELF_CHECK:` line per turn that re-validates the planned calls against MARKET_CONFIG. |
| Reasoning-type awareness | `THOUGHT [<type>]` where `<type> ∈ {LOOKUP, FILTER, SYNTHESIZE, VERIFY, PLAN, REPORT}`. |
| Error handling / fallbacks | Dedicated `FALLBACK:` line per turn + a `ERROR HANDLING / FALLBACKS` section covering tool errors, zero-hits, 404s, low confidence, and step-budget exhaustion. |
| Overall clarity | Sectioned with rules; MARKET_CONFIG is the single source of truth that every section references. |

### Worked qualification example

Below is the same prompt being graded by Gemini-Flash acting as the
Prompt Evaluation Assistant. The verdict in
[`PROMPT_EVAL.json`](PROMPT_EVAL.json) is the actual output of
`uv run prompt-eval` on the default `MarketConfig`.

---

## All CLI flags

```
uv run competitor-agent [PROMPT]
  # Product
  --product-name --product-url --product-description --category

  # Run sizing
  -n, --max-competitors N        # 1-50, default 5
  --max-steps N                  # override auto step budget (5 + 2N)
  --mode {live,static}           # dashboard mode
  --clear | --keep               # mutually exclusive

  # Market (see "Configuring the market" above)
  --market-config PATH
  --market-region --market-countries --market-industry
  --market-segment --market-pricing-tier --market-channels
  --market-language --market-geo-strictness
  --market-must-have --market-exclude --market-notes
```

---

## MCP tools (unchanged from SS4 except `update_dashboard_section`)

| Tool | Family | Notes |
|---|---|---|
| `search_competitors` | A | Tavily (preferred) → DuckDuckGo fallback. |
| `fetch_competitor_page` | A | httpx + BeautifulSoup, SHA-256 disk cache. |
| `create_competitor` | B | Now persists `market_fit_score` + `market_fit_reason`. |
| `read_competitors`, `update_competitor`, `delete_competitor`, `clear_database` | B | File-locked JSON store. |
| `render_dashboard` | C | `mode='live'` runs `prefab serve --reload`; `mode='static'` exports HTML. State now includes `market`. |
| `update_dashboard_section` | C | `section ∈ {product, table, cards, positioning, market}` — new `market` patch target. |
| `export_dashboard_pdf` | D | PDF now contains a Market scope section + Fit column. |

The agent runner injects the active `MarketConfig` into the MCP server's
process env as `MARKET_CONFIG_JSON`, which `prefab_ui.py` reads when
writing `dashboard_state.json`. The dashboard then renders the
**Market scope** banner from that state.

---

## Files of interest

| Path | What it does |
|---|---|
| [`mcp_server/schemas.py`](mcp_server/schemas.py) | `MarketConfig` pydantic model + `CompetitorRecord` with `market_fit_score` / `market_fit_reason`. |
| [`agent/market_config.py`](agent/market_config.py) | Loader resolving file → flag → defaults; argparse plumbing. |
| [`agent/run_agent.py`](agent/run_agent.py) | `SYSTEM_INSTRUCTION_TEMPLATE` (the qualified prompt), agent loop, market injection. |
| [`agent/prompt_eval.py`](agent/prompt_eval.py) | `prompt-eval` CLI — runs the rubric against the system prompt and writes `PROMPT_EVAL.json`. |
| [`dashboard_app/sections/market_context.py`](dashboard_app/sections/market_context.py) | Market scope banner UI. |
| [`dashboard_app/sections/comparison_table.py`](dashboard_app/sections/comparison_table.py) | Adds `Market fit` and `Fit reason` columns. |
| [`dashboard_app/sections/competitor_cards.py`](dashboard_app/sections/competitor_cards.py) | Per-card fit badge + reason line. |
| [`mcp_server/tools/pdf_export.py`](mcp_server/tools/pdf_export.py) | PDF gains a Market scope section + Fit column. |
| [`markets/`](markets) | Ready-made market configs you can drop in via `--market-config`. |
| [`PROMPT_EVAL.md`](PROMPT_EVAL.md) | Verbatim Prompt Evaluation Assistant rubric. |
| [`PROMPT_EVAL.json`](PROMPT_EVAL.json) | Verdict for the default-market rendering of the system prompt. |

---

## Common workflows

```bash
# 1. Stand up a fresh India B2C analysis for Tile Vision AI
uv run competitor-agent \
  --market-config markets/india_b2c_interior.json \
  -n 5 --clear --mode live

# 2. Reuse the saved DB but re-score everyone against a new market
#    (e.g. you decide to pivot from India B2C → SEA B2C)
uv run competitor-agent \
  "Re-score every existing competitor against the new market and update each record's market_fit_score and market_fit_reason. Then render the dashboard." \
  --market-config markets/southeast_asia_fintech.json \
  --keep

# 3. Add 3 more enterprise competitors to an existing India dataset
uv run competitor-agent \
  --product-name "Tile Vision AI" \
  --category "AI room visualizer" \
  --market-region "India" \
  --market-pricing-tier enterprise \
  --market-geo-strictness primary \
  -n 3 --keep

# 4. Export a polished PDF from whatever the dashboard currently shows
uv run python -c "from mcp_server.tools.pdf_export import export_dashboard_pdf; print(export_dashboard_pdf('data/india_report.pdf'))"

# 5. Re-grade the prompt after editing it
uv run prompt-eval --market-config markets/india_b2c_interior.json
```

---

## Logs and debugging

Same as SS4. `logs/agent.log` is the chronological tool-call trace; the
terminal output uses Rich panels.

If `prefab serve` exits immediately, run it manually to see the real
error:

```bash
uv run prefab serve dashboard_app/dashboard.py --port 8765 --reload
```

If Gemini-Flash starts skipping function calls (a known
quirk), switch to `AGENT_MODEL=gemini-2.5-pro` in `.env`.
