"""Section 4 — market positioning summary."""

from __future__ import annotations

from typing import Any

from prefab_ui.components import (
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


def positioning_section(analysis: dict[str, Any]) -> None:
    with Card(css_class="bg-white shadow-sm"):
        with CardHeader():
            CardTitle("Market positioning")
            Muted("Synthesized by the agent across all profiles above.")
        with CardContent():
            with Column(gap=4):
                Text(
                    analysis.get("summary") or "No summary yet — run the agent.",
                    css_class="text-slate-800 leading-relaxed",
                )
                with Row(gap=6, css_class="flex-wrap"):
                    _bullets("Differentiators", analysis.get("differentiators"), "emerald")
                    _bullets("Threats", analysis.get("threats"), "rose")
                    _bullets("Opportunities", analysis.get("opportunities"), "indigo")


def _coerce_items(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return [str(value)]


def _bullets(label: str, value: Any, tone: str) -> None:
    color = {
        "emerald": "text-emerald-700",
        "rose": "text-rose-700",
        "indigo": "text-indigo-700",
    }.get(tone, "text-slate-700")
    with Column(gap=1, css_class="min-w-[220px] flex-1"):
        Label(label, css_class=f"text-xs uppercase tracking-wide {color}")
        items = _coerce_items(value)
        if not items:
            Muted("—")
            return
        for it in items:
            Text(f"• {it}", css_class="text-sm text-slate-800")
