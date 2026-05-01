"""Section 2 — feature/pricing comparison table."""

from __future__ import annotations

from typing import Any

from prefab_ui.components import (
    Card,
    CardContent,
    CardHeader,
    CardTitle,
    DataTable,
    DataTableColumn,
    Muted,
)


def comparison_table(competitors: list[dict[str, Any]]) -> None:
    with Card(css_class="bg-white shadow-sm"):
        with CardHeader():
            CardTitle("Feature & pricing comparison")
            Muted(f"{len(competitors)} competitor(s) tracked.")
        with CardContent():
            rows = [
                {
                    "name": c.get("name", "—"),
                    "headquarters": c.get("headquarters") or "—",
                    "pricing": c.get("pricing") or "—",
                    "features": ", ".join(c.get("features", [])) or "—",
                    "target_market": c.get("target_market") or "—",
                    "last_updated": (c.get("last_updated", "") or "—")[:10],
                }
                for c in competitors
            ]
            DataTable(
                rows=rows,
                columns=[
                    DataTableColumn(key="name", header="Name", sortable=True, width="140px"),
                    DataTableColumn(key="headquarters", header="HQ", sortable=True, width="160px"),
                    DataTableColumn(key="pricing", header="Pricing", width="260px"),
                    DataTableColumn(key="features", header="Top features", width="360px"),
                    DataTableColumn(key="target_market", header="Target market", width="240px"),
                    DataTableColumn(
                        key="last_updated", header="Updated", sortable=True, width="110px"
                    ),
                ],
                search=True,
                paginated=False,
                css_class=(
                    "text-sm [&_td]:align-top [&_td]:whitespace-normal "
                    "[&_td]:break-words [&_td]:py-3 [&_th]:py-3"
                ),
            )


