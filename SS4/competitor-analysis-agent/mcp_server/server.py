"""FastMCP server exposing competitor-analysis tools.

Run as: `competitor-mcp` (after `uv sync`) or `python -m mcp_server.server`.
The server uses stdio transport so the agent runner can spawn it directly.
"""

from __future__ import annotations

from typing import Any, Literal

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from mcp_server.logging_setup import setup_logging
from mcp_server.tools import competitors_db, pdf_export, prefab_ui, web_research

load_dotenv()
logger = setup_logging("competitor_mcp")

mcp = FastMCP("competitor-analysis-agent")


# ---- Tool A: web_research ------------------------------------------------

@mcp.tool()
def search_competitors(
    product_name: str,
    product_description: str,
    category: str,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Discover candidate competitors via web search.

    Uses Tavily when TAVILY_API_KEY is set, else DuckDuckGo (no key needed).
    Issues several queries derived from the product name + category.

    Args:
        product_name: Name of the product the user is analyzing (e.g. 'Tile Vision AI').
        product_description: One-line description of what the product does.
        category: Product category, e.g. 'AI room visualizer', 'CRM', 'task tracker'.
        max_results: Max number of de-duplicated hits to return. Default 10.

    Returns:
        List of {name, url, snippet, source} dicts. Pass each url to
        fetch_competitor_page() to enrich.
    """
    return web_research.search_competitors(
        product_name=product_name,
        product_description=product_description,
        category=category,
        max_results=max_results,
    )


@mcp.tool()
def fetch_competitor_page(url: str, force_refresh: bool = False) -> dict[str, Any]:
    """Download + extract a competitor page.

    Caches results on disk; pass force_refresh=True to bypass the cache.
    Returns cleaned text plus pricing_hints[] and feature_mentions[]
    derived heuristically. On 404/5xx, raises with a hint to try a
    different source.
    """
    return web_research.fetch_competitor_page(url=url, force_refresh=force_refresh)


# ---- Tool B: competitors_db ---------------------------------------------

@mcp.tool()
def create_competitor(record: dict[str, Any]) -> dict[str, Any]:
    """Insert a new competitor profile into data/competitors.json.

    `record` must include: name, website, description.
    Optional: pricing, features[], strengths[], weaknesses[], target_market.
    Errors if a competitor with the same name (case-insensitive) exists —
    use update_competitor instead.
    """
    return competitors_db.create_competitor(record)


@mcp.tool()
def read_competitors(filter: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """List saved competitors, optionally filtered.

    Filter does substring-match on string fields. Pass None for all.
    Example filter: {"target_market": "designer"} returns competitors whose
    target_market contains 'designer'.
    """
    return competitors_db.read_competitors(filter=filter)


@mcp.tool()
def update_competitor(name: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Patch fields on an existing competitor (case-insensitive name match).

    Provide only the fields you want to change. last_updated is set
    automatically. Returns the full updated record.
    """
    return competitors_db.update_competitor(name=name, updates=updates)


@mcp.tool()
def delete_competitor(name: str) -> bool:
    """Delete a competitor by name. Returns True if removed, False if absent."""
    return competitors_db.delete_competitor(name=name)


@mcp.tool()
def clear_database() -> int:
    """Wipe every competitor record. Returns count cleared.

    Use this at the start of a fresh analysis run if you want to discard
    previous data.
    """
    return competitors_db.clear_database()


# ---- Tool C: prefab_ui --------------------------------------------------

@mcp.tool()
def render_dashboard(
    your_product: dict[str, Any],
    competitors: list[dict[str, Any]],
    analysis: dict[str, Any] | None = None,
    mode: Literal["live", "static"] = "live",
) -> dict[str, Any]:
    """Push the analysis to a Prefab UI dashboard.

    `mode='live'` starts (or reuses) `prefab serve` and returns the local
    URL to open in a browser. `mode='static'` runs `prefab export` and
    returns a file:// URL for the standalone HTML.

    Returns: {url, mode, served_at, pid?}.

    Call this once after you've populated the database; for in-flight
    updates use update_dashboard_section.
    """
    return prefab_ui.render_dashboard(
        your_product=your_product,
        competitors=competitors,
        analysis=analysis,
        mode=mode,
    )


@mcp.tool()
def update_dashboard_section(
    section: Literal["product", "table", "cards", "positioning"],
    content: dict[str, Any],
) -> bool:
    """Hot-update a single dashboard section.

    `section`:
      - 'product'      → replaces the 'Your Product' card.
      - 'table'/'cards'→ replaces the competitor list (both views share data).
      - 'positioning'  → replaces the market-positioning summary.

    Live `prefab serve` picks up the change automatically; static exports
    must be re-rendered with render_dashboard(mode='static').
    """
    return prefab_ui.update_dashboard_section(section=section, content=content)


# ---- Bonus Tool D: pdf_export -------------------------------------------

@mcp.tool()
def export_dashboard_pdf(out_path: str | None = None) -> str:
    """Render the current dashboard state to a polished PDF report.

    Reads from the same dashboard_state.json that render_dashboard wrote,
    so the PDF always matches the live UI. Returns the absolute file path.
    """
    return pdf_export.export_dashboard_pdf(out_path=out_path)


def main() -> None:
    logger.info("Starting competitor-analysis MCP server (stdio transport).")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
