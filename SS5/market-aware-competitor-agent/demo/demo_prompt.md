# Demo prompt

This single prompt forces the agent to chain Tool A (web research) → Tool B
(local CRUD) → Tool C (Prefab UI), with the bonus Tool D available.

## The prompt

> I'm building Tile Vision AI (https://swayam01.github.io/tile-vision-website/),
> an AI room/tile visualizer for homeowners, designers, and tile retailers.
> Find at least 5 real competitors, research each one's pricing, features,
> strengths, and weaknesses, save complete profiles to the local competitors
> database, and render a comparison dashboard I can review.

## How to run

```bash
cd SS4/competitor-analysis-agent
uv sync                              # or: pip install -e .
cp .env.example .env                 # then fill GEMINI_API_KEY + TAVILY_API_KEY
uv run competitor-agent              # uses the demo prompt above
# OR with a custom prompt:
uv run competitor-agent "Analyze competitors for Notion in the productivity space."
```

## Expected tool sequence

1. `clear_database` — fresh run
2. `search_competitors(product_name='Tile Vision AI', category='AI room visualizer', ...)`
3. `fetch_competitor_page(<hit 1 url>)`, `fetch_competitor_page(<hit 2 url>)`, …
4. `create_competitor({...})` × 5+
5. `read_competitors()` to build the dashboard payload
6. `render_dashboard(your_product=..., competitors=..., analysis=...)`
7. (optional) `export_dashboard_pdf()`

## What to record for the YouTube demo

- Terminal scroll showing Rich-formatted `TOOL_CALL` / `TOOL_RESULT` panels.
- Browser opening `http://127.0.0.1:8765` with the live Prefab dashboard.
- `data/competitors.json` populated with 5+ records.
- (Bonus) `data/report.pdf` opened side-by-side with the live UI.

## Generic-by-design

Swap the prompt to analyze any product:

```bash
uv run competitor-agent "Analyze competitors for Linear, a project tracker for engineering teams."
uv run competitor-agent "Analyze competitors for Stripe Atlas, an LLC formation service."
```

The agent doesn't hardcode Tile Vision AI anywhere — it's just the default demo.
