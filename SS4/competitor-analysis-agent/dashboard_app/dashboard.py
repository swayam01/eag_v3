"""Top-level Prefab dashboard.

Reads its data from data/dashboard_state.json so Tool C can update content
without rewriting this file. Run via:

    prefab serve dashboard_app/dashboard.py        # live preview
    prefab export dashboard_app/dashboard.py -o out.html  # static export
"""

from __future__ import annotations

import json
from pathlib import Path

from prefab_ui import PrefabApp
from prefab_ui.components import Column, Container, H1, Muted, Row

from dashboard_app.sections.comparison_table import comparison_table
from dashboard_app.sections.competitor_cards import competitor_cards
from dashboard_app.sections.positioning import positioning_section
from dashboard_app.sections.your_product import your_product_card

STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "dashboard_state.json"


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {"product": {}, "competitors": [], "analysis": {}}
    try:
        return json.loads(STATE_PATH.read_text())
    except json.JSONDecodeError:
        return {"product": {}, "competitors": [], "analysis": {}}


app = PrefabApp(title="Competitor Analysis")

with app:
    state = _load_state()
    product = state.get("product") or {}
    competitors = state.get("competitors") or []
    analysis = state.get("analysis") or {}

    with Container(css_class="max-w-[1400px] mx-auto p-6 bg-slate-100 min-h-screen"):
        with Column(css_class="gap-6"):
            with Row(css_class="items-baseline gap-3"):
                H1(
                    f"Competitor Analysis: {product.get('name', '—')}",
                    css_class="text-2xl font-bold text-slate-900",
                )
                Muted(f"{len(competitors)} competitor(s)")

            your_product_card(product)
            comparison_table(competitors)
            competitor_cards(competitors)
            positioning_section(analysis)
