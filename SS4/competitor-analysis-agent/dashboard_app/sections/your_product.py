"""Section 1 — 'Your Product' card."""

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


def your_product_card(product: dict[str, Any]) -> None:
    with Card(css_class="border-indigo-200 bg-white shadow-sm"):
        with CardHeader():
            with Row(gap=3, css_class="items-center"):
                Badge("Your Product", variant="info")
                CardTitle(product.get("name", "Untitled product"))
        with CardContent():
            with Column(gap=4):
                Muted(product.get("description", ""))
                with Row(gap=6, css_class="flex-wrap"):
                    _kv("Category", product.get("category", "—"))
                    _kv("Target market", product.get("target_market", "—"))
                    _kv("Pricing", product.get("pricing", "—"))
                if product.get("url"):
                    Text(product["url"], css_class="text-indigo-600 underline text-sm")


def _kv(label: str, value: str) -> None:
    with Column(gap=1, css_class="min-w-[160px]"):
        Label(label, css_class="text-xs uppercase tracking-wide text-slate-500")
        Text(value, css_class="text-sm font-medium text-slate-900")
