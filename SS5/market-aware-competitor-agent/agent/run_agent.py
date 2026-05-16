"""Gemini-Flash agent that drives the local MCP server over stdio.

v0.2 — Market-aware. The user supplies a MarketConfig (region, segment,
pricing tier, keywords, geo strictness) via --market-config or --market-*
flags, and the agent uses it to filter, score, and tag every competitor.

The system instruction enforces a structured reasoning protocol so the
prompt qualifies on the Prompt Evaluation Assistant rubric — see
README.md → "Prompt qualification".
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types as gtypes
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from agent.market_config import add_market_flags, load_market_config
from mcp_server.schemas import MarketConfig

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

console = Console()

DEFAULT_PROMPT = (
    "I'm building Tile Vision AI (https://swayam01.github.io/tile-vision-website/), "
    "an AI room/tile visualizer for homeowners, designers, and tile retailers. "
    "Find real competitors that fit the configured market, research each one's "
    "pricing, features, strengths, and weaknesses, save complete profiles to the "
    "local competitors database, and render a comparison dashboard I can review."
)


SYSTEM_INSTRUCTION_TEMPLATE = """You are MarketAwareCompetitorAgent — a research agent that
produces a market-targeted competitor analysis. You ALWAYS run inside a
specific market context (see MARKET_CONFIG below).

══════════════════════════════════════════════════════════════════════
MARKET_CONFIG (authoritative — every step must respect this):
{market_brief}
══════════════════════════════════════════════════════════════════════

You have these tool families (call them via function-calling):
  • web_research      — search_competitors, fetch_competitor_page
  • competitors_db    — create_competitor, read_competitors, update_competitor,
                        delete_competitor, clear_database
  • prefab_ui         — render_dashboard, update_dashboard_section
  • pdf_export        — export_dashboard_pdf (bonus)

────────────────────────────────────────────────────────────────────
REASONING PROTOCOL (follow every turn, in order)
────────────────────────────────────────────────────────────────────
Each turn you produce a text part AND zero-or-more function_call parts.
Format the text part as the following labelled blocks, in this order:

  THOUGHT [<type>]: one short paragraph of step-by-step reasoning.
                    <type> ∈ {{LOOKUP, FILTER, SYNTHESIZE, VERIFY, PLAN, REPORT}}.
  PLAN:             1–4 numbered bullets describing what you will do next.
  SELF_CHECK:       one line confirming the planned calls respect MARKET_CONFIG
                    (region, segment, pricing tier, exclude keywords). Say
                    "OK — fits market" or list the specific fit reason.
  FALLBACK:         one line — what you will do if the next tool fails or
                    returns nothing useful (e.g. "try alternate query",
                    "skip this candidate, try the next hit", "lower
                    geo_strictness if zero matches in this region").
  CONFIDENCE:       LOW | MEDIUM | HIGH for the current step.

Then emit the function_call(s). Independent calls MUST be emitted in
parallel in the same turn — never one tool per turn.

When you have no more tool calls and are ready to finish, the text part
becomes a FINAL block with this exact shape (no function calls):

  FINAL:
    summary: <2–3 sentences referencing MARKET_CONFIG>
    competitors_saved: <int>
    dashboard_url: <url from render_dashboard, or "—" if not rendered>
    market_fit_distribution: <e.g. "3 high / 1 medium / 1 low">
    confidence: LOW|MEDIUM|HIGH

────────────────────────────────────────────────────────────────────
PLAYBOOK
────────────────────────────────────────────────────────────────────
1. (Optional) clear_database — ONLY if the user said "fresh run", "reset",
   or "start from scratch". Default: keep existing data and add to it.
2. read_competitors first to see what's already saved for this market.
3. search_competitors — bias queries with MARKET_CONFIG.region,
   MARKET_CONFIG.industry_vertical and the user's product name. Examples:
     "<product> competitors in <region>"
     "<vertical> tools <region> 2026"
     "best <vertical> for <segment> in <region>"
4. FILTER the hits against MARKET_CONFIG BEFORE fetching:
     • drop hits matching any exclude_keyword
     • prefer hits matching any must_have_keyword
     • respect geo_strictness:
         strict  → drop unless HQ likely in countries[]
         primary → drop unless the company demonstrably serves the region
         loose   → keep any plausible global player
5. fetch_competitor_page for each kept hit. Pricing is usually on /pricing
   or /packages — fetch that explicitly when present. If a page errors,
   pick a different source; never give up.
6. For every real competitor, do a SEPARATE search for headquarters
   ("<company> headquarters location"); prefer Crunchbase / LinkedIn /
   CB Insights over the company's own About page.
7. Score each competitor's market_fit_score (0–10) against MARKET_CONFIG:
     10 = HQ in region + pricing tier match + segment match
      6 = serves region but pricing tier or segment is off
      3 = global player only loosely relevant
      0 = does not belong (do not save)
   Always write a one-sentence market_fit_reason referencing the config.
8. create_competitor for each saved profile (include market_fit_score and
   market_fit_reason).
9. render_dashboard once you have the target count. Use
   update_dashboard_section for incremental tweaks afterwards.

────────────────────────────────────────────────────────────────────
ERROR HANDLING / FALLBACKS
────────────────────────────────────────────────────────────────────
  • Tool error  → read the message, change ONE thing (query, URL, args)
                  and retry. Don't repeat the exact same call.
  • Zero hits   → broaden the query OR relax geo_strictness one notch
                  (strict→primary→loose). Note this in SELF_CHECK.
  • Page 404/5xx→ pick a different hit. Never fabricate.
  • Low confidence on a record → save it with market_fit_score ≤ 4 and
                                 weaknesses noting the missing evidence.
  • Step budget nearly exhausted → skip remaining candidates, render
                                   dashboard with what you have, emit FINAL.

────────────────────────────────────────────────────────────────────
RULES
────────────────────────────────────────────────────────────────────
  • Never fabricate a competitor — every record must trace to a URL you fetched.
  • Tool arguments must be minimal and correctly typed.
  • Emit MULTIPLE tool calls per turn whenever independent (fetch many
    pages in parallel, save many records back-to-back).
  • Every saved competitor MUST have market_fit_score and market_fit_reason
    set — these are the whole point of MARKET_CONFIG.
  • Stop researching once you have the target number of solid in-market
    profiles, then render the dashboard and emit FINAL.

────────────────────────────────────────────────────────────────────
EXAMPLE TURN (illustrative — adapt to the real situation)
────────────────────────────────────────────────────────────────────
  THOUGHT [PLAN]: User wants 5 competitors for an AI room visualizer in
    India (B2C, budget tier). I'll search India-biased queries first,
    filter against must_have_keywords ["tile","visualize","India"], then
    fetch the top 3 in parallel.
  PLAN:
    1. search_competitors with India-specific query.
    2. In parallel, fetch the 3 most India-relevant hits.
  SELF_CHECK: OK — fits market (region=India, vertical=interior design).
  FALLBACK: If <3 India hits, re-search with vertical only and relax
    geo_strictness to "primary".
  CONFIDENCE: MEDIUM
  → [function_call] search_competitors(product_name="Tile Vision AI",
       product_description="AI room visualizer", category="AI room visualizer India",
       max_results=10)
"""


def _build_system_instruction(market: MarketConfig) -> str:
    return SYSTEM_INSTRUCTION_TEMPLATE.format(market_brief=market.to_brief())


def _clean_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Strip MCP/JSON-Schema fields Gemini can't parse."""
    if not isinstance(schema, dict):
        return schema
    drop = {"$schema", "title", "additionalProperties", "definitions", "$defs"}
    out: dict[str, Any] = {}
    for k, v in schema.items():
        if k in drop:
            continue
        if isinstance(v, dict):
            out[k] = _clean_schema(v)
        elif isinstance(v, list):
            out[k] = [_clean_schema(i) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    if out.get("type") == "object" and "properties" not in out:
        out["properties"] = {}
    return out


def _mcp_tools_to_gemini(tools: list[Any]) -> gtypes.Tool:
    decls: list[gtypes.FunctionDeclaration] = []
    for t in tools:
        params = _clean_schema(t.inputSchema or {"type": "object", "properties": {}})
        decls.append(
            gtypes.FunctionDeclaration(
                name=t.name,
                description=(t.description or "").strip(),
                parameters=params,
            )
        )
    return gtypes.Tool(function_declarations=decls)


def _print_step(idx: int, kind: str, payload: str) -> None:
    title = f"[bold]Step {idx}[/] · [cyan]{kind}[/]"
    console.print(Panel(payload, title=title, border_style="cyan", expand=True))


def _print_tool_call(idx: int, name: str, args: dict[str, Any]) -> None:
    body = Syntax(json.dumps(args, indent=2, ensure_ascii=False), "json", line_numbers=False)
    console.print(Panel(body, title=f"[bold]Step {idx}[/] · [yellow]TOOL_CALL[/] {name}",
                        border_style="yellow", expand=True))


def _print_tool_result(idx: int, name: str, ok: bool, payload: Any) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False)[:1800]
    color = "green" if ok else "red"
    body = Syntax(text, "json", line_numbers=False)
    console.print(Panel(body, title=f"[bold]Step {idx}[/] · [{color}]TOOL_RESULT[/] {name}",
                        border_style=color, expand=True))


async def run_agent(user_prompt: str, market: MarketConfig, max_steps: int) -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        console.print("[red]GEMINI_API_KEY missing.[/] Copy .env.example → .env and fill it in.")
        sys.exit(2)

    model = os.environ.get("AGENT_MODEL", "gemini-2.5-flash")

    client = genai.Client(api_key=api_key)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        env={**os.environ, "PYTHONPATH": str(ROOT), "MARKET_CONFIG_JSON": market.model_dump_json()},
    )

    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(server_params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        tool_list = (await session.list_tools()).tools
        console.print(
            Panel(
                "\n".join(f"• [bold]{t.name}[/] — {(t.description or '').splitlines()[0]}" for t in tool_list),
                title="MCP tools available",
                border_style="magenta",
            )
        )
        console.print(
            Panel(market.to_brief(), title="MarketConfig in effect", border_style="blue")
        )

        gemini_tool = _mcp_tools_to_gemini(tool_list)

        contents: list[gtypes.Content] = [
            gtypes.Content(role="user", parts=[gtypes.Part.from_text(text=user_prompt)])
        ]
        config = gtypes.GenerateContentConfig(
            system_instruction=_build_system_instruction(market),
            tools=[gemini_tool],
            temperature=0.3,
        )

        for step in range(1, max_steps + 1):
            response = client.models.generate_content(
                model=model, contents=contents, config=config
            )
            candidate = response.candidates[0]
            content = candidate.content
            contents.append(content)

            function_calls = [p.function_call for p in (content.parts or []) if p.function_call]
            text_parts = [p.text for p in (content.parts or []) if getattr(p, "text", None)]
            if text_parts:
                _print_step(step, "MODEL_TEXT", "\n".join(text_parts))

            if not function_calls:
                console.print(Panel("[bold green]Agent finished.[/]", border_style="green"))
                return

            tool_response_parts: list[gtypes.Part] = []
            for fc in function_calls:
                args = dict(fc.args or {})
                _print_tool_call(step, fc.name, args)
                try:
                    result = await session.call_tool(fc.name, args)
                    if result.isError:
                        payload = {"error": _result_text(result)}
                        _print_tool_result(step, fc.name, ok=False, payload=payload)
                    else:
                        payload = _result_payload(result)
                        _print_tool_result(step, fc.name, ok=True, payload=payload)
                except Exception as exc:
                    payload = {"error": f"{type(exc).__name__}: {exc}"}
                    _print_tool_result(step, fc.name, ok=False, payload=payload)

                tool_response_parts.append(
                    gtypes.Part.from_function_response(name=fc.name, response={"result": payload})
                )

            contents.append(gtypes.Content(role="user", parts=tool_response_parts))

        console.print(
            Panel(
                f"[red]Hit AGENT_MAX_STEPS={max_steps} without a final answer.[/]",
                border_style="red",
            )
        )


def _result_text(result: Any) -> str:
    chunks = []
    for c in result.content or []:
        chunks.append(getattr(c, "text", str(c)))
    return "\n".join(chunks)


def _result_payload(result: Any) -> Any:
    text = _result_text(result)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


MAX_COMPETITORS_CAP = 50


def _build_prompt(args: argparse.Namespace, market: MarketConfig) -> str:
    has_product_flags = any(
        [args.product_name, args.product_url, args.product_description, args.category]
    )
    target = args.max_competitors

    if has_product_flags:
        lines = ["Analyze competitors for the following product, scoped to MARKET_CONFIG."]
        if args.product_name:
            lines.append(f"PRODUCT_NAME: {args.product_name}")
        if args.product_url:
            lines.append(f"PRODUCT_URL: {args.product_url}")
        if args.product_description:
            lines.append(f"DESCRIPTION: {args.product_description}")
        if args.category:
            lines.append(f"CATEGORY: {args.category}")
        lines.append(f"MARKET: {market.to_brief()}")
        lines.append(
            f"TARGET: find at least {target} real competitors that fit MARKET_CONFIG "
            f"and call search_competitors(max_results={target * 2}) so you have room to filter."
        )
        lines.append(
            "Research each via fetch_competitor_page, score market_fit_score (0–10) "
            "against MARKET_CONFIG, save complete profiles via create_competitor "
            "(include market_fit_score and market_fit_reason), then render the dashboard."
        )
        if args.clear:
            lines.append("Start with clear_database — fresh run.")
        elif args.keep:
            lines.append(
                "Keep existing competitors — ADD to them. "
                "Use update_dashboard_section for incremental UI patches."
            )
        if args.mode:
            lines.append(f"Render the dashboard with mode='{args.mode}'.")
        return "\n".join(lines)

    base = args.prompt or DEFAULT_PROMPT
    extras = [f"MARKET: {market.to_brief()}"]
    if args.max_competitors_explicit:
        extras.append(
            f"TARGET: find at least {target} competitors that fit MARKET_CONFIG "
            f"(search_competitors max_results={target * 2})."
        )
    if args.clear:
        extras.append("Start with clear_database — fresh run.")
    elif args.keep:
        extras.append(
            "Keep existing competitors — ADD to them. Use update_dashboard_section for incremental UI patches."
        )
    if args.mode:
        extras.append(f"Render the dashboard with mode='{args.mode}'.")
    return base + "\n\n" + "\n".join(extras)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the market-aware competitor-analysis agent.",
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help="Free-form prompt. Omit to use the default Tile Vision AI demo prompt.",
    )
    parser.add_argument("--product-name", help="Name of the product to analyze.")
    parser.add_argument("--product-url", help="Product website URL.")
    parser.add_argument("--product-description", help="One-line description.")
    parser.add_argument("--category", help="Product category (e.g. 'AI room visualizer').")
    parser.add_argument(
        "-n",
        "--max-competitors",
        type=int,
        default=5,
        help=f"Target number of competitor profiles (1-{MAX_COMPETITORS_CAP}, default 5).",
    )
    parser.add_argument(
        "--mode",
        choices=["live", "static"],
        default=None,
        help="Dashboard render mode. 'live' = prefab serve, 'static' = standalone HTML.",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear the competitors database before this run.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep existing competitors and add to them.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Override the agent step budget. Auto-scales with --max-competitors otherwise.",
    )

    add_market_flags(parser)
    args = parser.parse_args()

    if args.clear and args.keep:
        parser.error("--clear and --keep are mutually exclusive.")
    if not 1 <= args.max_competitors <= MAX_COMPETITORS_CAP:
        parser.error(f"--max-competitors must be between 1 and {MAX_COMPETITORS_CAP}.")
    args.max_competitors_explicit = "--max-competitors" in sys.argv or "-n" in sys.argv

    if args.max_steps is not None:
        max_steps = args.max_steps
    else:
        env_default = int(os.environ.get("AGENT_MAX_STEPS", "30"))
        max_steps = max(env_default, 5 + 2 * args.max_competitors)

    market = load_market_config(args)
    prompt = _build_prompt(args, market)
    asyncio.run(run_agent(prompt, market=market, max_steps=max_steps))


if __name__ == "__main__":
    main()
