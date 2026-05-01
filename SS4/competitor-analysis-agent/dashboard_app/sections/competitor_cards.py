"""Section 3 — one expandable SWOT card per competitor."""

from __future__ import annotations

from typing import Any

from prefab_ui.components import (
    Accordion,
    AccordionItem,
    Badge,
    Column,
    H3,
    Label,
    Muted,
    Row,
    Text,
)


def competitor_cards(competitors: list[dict[str, Any]]) -> None:
    H3("Competitor profiles", css_class="text-slate-900 font-semibold mb-3")
    if not competitors:
        Muted("No competitors saved yet. Run the agent to populate.")
        return

    with Accordion(multiple=True, css_class="space-y-2"):
        for c in competitors:
            _competitor_item(c)


def _competitor_item(c: dict[str, Any]) -> None:
    name = c.get("name", "—")
    pricing = c.get("pricing") or "Pricing not listed"
    hq = c.get("headquarters") or ""
    suffix = f"  ·  {hq}" if hq else ""
    title = f"{name}  ·  {_short(pricing, 60)}{suffix}"
    with AccordionItem(title):
        with Column(gap=4, css_class="pt-2"):
            Text(c.get("description", ""), css_class="text-sm text-slate-700")
            with Row(gap=6, css_class="flex-wrap"):
                _list_block("Strengths", c.get("strengths", []), tone="emerald")
                _list_block("Weaknesses", c.get("weaknesses", []), tone="rose")
            with Row(gap=6, css_class="flex-wrap"):
                _list_block("Features", c.get("features", []), tone="indigo")
                _list_block("Target market", [c.get("target_market") or "—"], tone="slate")
                _list_block("Headquarters", [hq or "—"], tone="slate")
            if c.get("website"):
                Text(c["website"], css_class="text-indigo-600 underline text-sm")


def _list_block(label: str, items: list[str], tone: str) -> None:
    color = {
        "emerald": "text-emerald-700",
        "rose": "text-rose-700",
        "indigo": "text-indigo-700",
        "slate": "text-slate-700",
    }.get(tone, "text-slate-700")
    with Column(gap=1, css_class="min-w-[220px] flex-1"):
        Label(label, css_class=f"text-xs uppercase tracking-wide {color}")
        if not items:
            Muted("—")
            return
        for item in items:
            Text(f"• {item}", css_class="text-sm text-slate-800")


def _short(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"
