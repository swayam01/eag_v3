"""Section — Market context banner.

Displays the active MarketConfig so reviewers can see which market the
agent was scoped to. Driven by state['market'] in dashboard_state.json.
"""

from __future__ import annotations

from typing import Any

from prefab_ui.components import (
    Badge,
    Card,
    CardContent,
    CardHeader,
    CardTitle,
    Column,
    Label,
    Muted,
    Row,
    Text,
)


def market_context_card(market: dict[str, Any]) -> None:
    if not market:
        return
    with Card(css_class="border-blue-200 bg-blue-50/40 shadow-sm"):
        with CardHeader():
            with Row(gap=3, css_class="items-center flex-wrap"):
                Badge("Market scope", variant="info")
                CardTitle(market.get("region", "Global"))
                _strictness_badge(market.get("geo_strictness", "primary"))
        with CardContent():
            with Column(gap=4):
                if market.get("notes"):
                    Muted(market["notes"])
                with Row(gap=6, css_class="flex-wrap"):
                    _kv("Vertical", market.get("industry_vertical") or "—")
                    _kv("Segment", market.get("customer_segment", "Mixed"))
                    _kv("Pricing tier", market.get("pricing_tier", "mixed"))
                    _kv("Language", market.get("language", "English"))
                    if market.get("countries"):
                        _kv("Countries", ", ".join(market["countries"]))
                    if market.get("channels"):
                        _kv("Channels", ", ".join(market["channels"]))
                if market.get("must_have_keywords") or market.get("exclude_keywords"):
                    with Row(gap=2, css_class="flex-wrap"):
                        for kw in market.get("must_have_keywords") or []:
                            Badge(f"must: {kw}", variant="success")
                        for kw in market.get("exclude_keywords") or []:
                            Badge(f"exclude: {kw}", variant="warning")


def _strictness_badge(strictness: str) -> None:
    variant = {"strict": "warning", "primary": "info", "loose": "default"}.get(
        strictness, "default"
    )
    Badge(f"geo: {strictness}", variant=variant)


def _kv(label: str, value: str) -> None:
    with Column(gap=1, css_class="min-w-[160px]"):
        Label(label, css_class="text-xs uppercase tracking-wide text-slate-500")
        Text(str(value), css_class="text-sm font-medium text-slate-900")
