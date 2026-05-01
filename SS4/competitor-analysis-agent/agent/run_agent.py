"""Gemini-Flash agent that drives the local MCP server over stdio.

Flow:
    1. Spawns `python -m mcp_server.server` via the MCP Python client.
    2. Lists MCP tools and converts their JSON Schemas → Gemini
       FunctionDeclarations.
    3. Sends the user prompt + tools to Gemini.
    4. While Gemini emits function calls, dispatches each to the MCP
       server and appends the response back to the conversation.
    5. Stops when Gemini returns plain text with no further tool calls,
       or when AGENT_MAX_STEPS is hit.

Streams every step (model thoughts, tool calls, tool results) to stdout
with rich formatting — clean material for the YouTube demo.
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

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

console = Console()

DEFAULT_PROMPT = (
    "I'm building Tile Vision AI (https://swayam01.github.io/tile-vision-website/), "
    "an AI room/tile visualizer for homeowners, designers, and tile retailers. "
    "Find at least 5 real competitors, research each one's pricing, features, "
    "strengths, and weaknesses, save complete profiles to the local competitors "
    "database, and render a comparison dashboard I can review."
)

SYSTEM_INSTRUCTION = """You are a competitor-analysis agent. The user gives you a
product and asks for a research-backed comparison.

You have these tool families:
  • web_research: search_competitors, fetch_competitor_page
  • competitors_db: create_competitor, read_competitors, update_competitor,
    delete_competitor, clear_database
  • prefab_ui: render_dashboard, update_dashboard_section
  • pdf_export: export_dashboard_pdf (optional bonus)

Standard playbook (adapt as needed):
  1. clear_database — ONLY if the user explicitly said "fresh run", "reset",
     or "start from scratch". Default is to keep existing data.
  2. read_competitors first to see what's already saved. If profiles exist
     and the user asked for additions/edits, work incrementally.
  3. search_competitors with the product name + category. Use the
     max_results value the user specified (look for "find N competitors"
     or a TARGET line in the prompt).
  4. For each promising hit, fetch_competitor_page to confirm it's a real
     competitor and pull pricing/feature evidence. If a page 404s or errors,
     pick a different hit — don't give up on the search.
     IMPORTANT: pricing is often hidden on the homepage but listed on a
     /pricing or /packages page. Fetch that explicitly when present.
  5. Run a SEPARATE search_competitors / fetch query to find each company's
     headquarters (city, country). Don't rely on the company's own About
     page alone — third-party sources (Crunchbase, LinkedIn, CB Insights)
     are more reliable. Save into the `headquarters` field as "City, Country".
  6. Build a CompetitorRecord per real competitor and create_competitor it.
     Include strengths/weaknesses based on evidence, not speculation.
  7. After the target number of profiles is saved, render the dashboard.

Rendering — pick the right tool:
  • render_dashboard(your_product, competitors, analysis, mode) — full render.
    Use this on the first run, after clear_database, or when most of the
    data has changed.
  • update_dashboard_section(section, content) — partial patch. Use this
    when only one piece changed (added a competitor, refined the analysis).
    The live UI hot-reloads without restart.

Rules:
  • Never fabricate competitors — every record must trace to a real URL you fetched.
  • Keep tool arguments minimal and correctly typed.
  • If a tool errors, read the message and adapt; don't repeat the same call.
  • Step budget is tight — emit MULTIPLE tool calls per turn whenever they're
    independent (e.g. fetch several competitor pages in parallel; save several
    create_competitor records back-to-back). Avoid one-tool-per-turn pacing.
  • Stop researching once you have the target number of solid profiles.
"""


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


async def run_agent(user_prompt: str, max_steps: int) -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        console.print("[red]GEMINI_API_KEY missing.[/] Copy .env.example → .env and fill it in.")
        sys.exit(2)

    model = os.environ.get("AGENT_MODEL", "gemini-2.5-flash")

    client = genai.Client(api_key=api_key)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        env={**os.environ, "PYTHONPATH": str(ROOT)},
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
        gemini_tool = _mcp_tools_to_gemini(tool_list)

        contents: list[gtypes.Content] = [
            gtypes.Content(role="user", parts=[gtypes.Part.from_text(text=user_prompt)])
        ]
        config = gtypes.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
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


def _build_prompt(args: argparse.Namespace) -> str:
    """Compose the user prompt from CLI flags + free-form prompt + defaults."""
    has_product_flags = any(
        [args.product_name, args.product_url, args.product_description, args.category]
    )
    target = args.max_competitors

    # Path 1: structured product flags → build a templated prompt
    if has_product_flags:
        lines = ["Analyze competitors for the following product."]
        if args.product_name:
            lines.append(f"PRODUCT_NAME: {args.product_name}")
        if args.product_url:
            lines.append(f"PRODUCT_URL: {args.product_url}")
        if args.product_description:
            lines.append(f"DESCRIPTION: {args.product_description}")
        if args.category:
            lines.append(f"CATEGORY: {args.category}")
        lines.append(
            f"TARGET: find at least {target} real competitors and call "
            f"search_competitors(max_results={target})."
        )
        lines.append(
            "Research each via fetch_competitor_page, save complete profiles "
            "via create_competitor (name, website, description, pricing, features, "
            "strengths, weaknesses, target_market), then render the comparison dashboard."
        )
        if args.clear:
            lines.append("Start with clear_database — fresh run.")
        elif args.keep:
            lines.append(
                "Keep existing competitors in the database — ADD to them. "
                "Use update_dashboard_section for incremental UI patches."
            )
        if args.mode:
            lines.append(f"Render the dashboard with mode='{args.mode}'.")
        return "\n".join(lines)

    # Path 2: free-form prompt or default — append a target hint if specified
    base = args.prompt or DEFAULT_PROMPT
    extras: list[str] = []
    if args.max_competitors_explicit:
        extras.append(
            f"TARGET: find at least {target} competitors (search_competitors max_results={target})."
        )
    if args.clear:
        extras.append("Start with clear_database — fresh run.")
    elif args.keep:
        extras.append(
            "Keep existing competitors — ADD to them. Use update_dashboard_section for incremental UI patches."
        )
    if args.mode:
        extras.append(f"Render the dashboard with mode='{args.mode}'.")
    if extras:
        base = base + "\n\n" + "\n".join(extras)
    return base


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the competitor-analysis agent.")
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
        help="Keep existing competitors and add to them (default behavior; explicit override).",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Override the agent step budget. Auto-scales with --max-competitors otherwise.",
    )
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
        # ~2 steps per competitor (fetch + create) + 5 overhead. Stay above env default.
        max_steps = max(env_default, 5 + 2 * args.max_competitors)

    prompt = _build_prompt(args)
    asyncio.run(run_agent(prompt, max_steps=max_steps))


if __name__ == "__main__":
    main()
