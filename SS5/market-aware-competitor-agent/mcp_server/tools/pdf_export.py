"""Bonus Tool D — Export the dashboard state as a PDF report.

Reads the same data/dashboard_state.json that Tool C writes, so the PDF
always matches the live UI. Uses ReportLab (no headless Chrome required).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from mcp_server.logging_setup import setup_logging, tool_call_log, tool_result_log

logger = setup_logging("competitor_mcp.pdf")

ROOT = Path(__file__).resolve().parent.parent.parent
STATE_PATH = ROOT / "data" / "dashboard_state.json"
DEFAULT_OUT = ROOT / "data" / "report.pdf"


def export_dashboard_pdf(out_path: str | None = None) -> str:
    """Render the current dashboard state as a PDF. Returns the absolute path."""
    target = Path(out_path) if out_path else DEFAULT_OUT
    target.parent.mkdir(parents=True, exist_ok=True)
    tool_call_log(logger, "export_dashboard_pdf", out=str(target))

    if not STATE_PATH.exists():
        raise RuntimeError(
            "dashboard_state.json missing — run render_dashboard first to populate state."
        )
    state = json.loads(STATE_PATH.read_text())
    product = state.get("product") or {}
    competitors = state.get("competitors") or []
    analysis = state.get("analysis") or {}
    market = state.get("market") or {}

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], textColor=colors.HexColor("#0F172A"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=colors.HexColor("#334155"))
    body = ParagraphStyle("body", parent=styles["BodyText"], leading=14)
    muted = ParagraphStyle(
        "muted", parent=styles["BodyText"], textColor=colors.HexColor("#64748B"), fontSize=9
    )

    doc = SimpleDocTemplate(
        str(target),
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title=f"Competitor Analysis — {product.get('name', '')}",
    )
    flow: list[Any] = []

    flow.append(Paragraph(f"Competitor Analysis: {product.get('name', '—')}", h1))
    flow.append(Paragraph(product.get("description", ""), body))
    flow.append(
        Paragraph(
            f"Category: {product.get('category', '—')} &nbsp;·&nbsp; "
            f"Target: {product.get('target_market', '—')} &nbsp;·&nbsp; "
            f"Pricing: {product.get('pricing', '—')}",
            muted,
        )
    )
    flow.append(Spacer(1, 0.18 * inch))

    if market:
        flow.append(Paragraph("Market scope", h2))
        flow.append(
            Paragraph(
                f"Region: <b>{market.get('region', 'Global')}</b> &nbsp;·&nbsp; "
                f"Vertical: {market.get('industry_vertical') or '—'} &nbsp;·&nbsp; "
                f"Segment: {market.get('customer_segment', 'Mixed')} &nbsp;·&nbsp; "
                f"Pricing tier: {market.get('pricing_tier', 'mixed')} &nbsp;·&nbsp; "
                f"Geo: {market.get('geo_strictness', 'primary')}",
                body,
            )
        )
        if market.get("notes"):
            flow.append(Paragraph(market["notes"], muted))
        flow.append(Spacer(1, 0.15 * inch))

    flow.append(Paragraph("Comparison", h2))
    table_data = [["Name", "HQ", "Fit", "Pricing", "Top features", "Target market"]]
    for c in competitors:
        table_data.append(
            [
                c.get("name", "—"),
                _short(c.get("headquarters") or "—", 22),
                f"{c.get('market_fit_score', 0)}/10",
                _short(c.get("pricing", "—"), 36),
                _short(", ".join(c.get("features", [])[:4]), 56),
                _short(c.get("target_market", "—"), 32),
            ]
        )
    if len(table_data) > 1:
        tbl = Table(
            table_data,
            repeatRows=1,
            colWidths=[1.2 * inch, 1.0 * inch, 0.6 * inch, 1.3 * inch, 2.2 * inch, 1.2 * inch],
        )
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F46E5")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                ]
            )
        )
        flow.append(tbl)
    else:
        flow.append(Paragraph("No competitors saved yet.", muted))
    flow.append(Spacer(1, 0.25 * inch))

    flow.append(Paragraph("Profiles", h2))
    for c in competitors:
        flow.append(Paragraph(f"<b>{c.get('name', '—')}</b>", styles["Heading3"]))
        if c.get("website"):
            flow.append(Paragraph(c["website"], muted))
        if c.get("headquarters"):
            flow.append(Paragraph(f"HQ: {c['headquarters']}", muted))
        if c.get("market_fit_score"):
            flow.append(
                Paragraph(
                    f"<b>Market fit:</b> {c['market_fit_score']}/10 — "
                    f"{c.get('market_fit_reason', '')}",
                    body,
                )
            )
        flow.append(Paragraph(c.get("description", ""), body))
        flow.append(Paragraph(f"<b>Strengths:</b> {_join(c.get('strengths', []))}", body))
        flow.append(Paragraph(f"<b>Weaknesses:</b> {_join(c.get('weaknesses', []))}", body))
        flow.append(Paragraph(f"<b>Features:</b> {_join(c.get('features', []))}", body))
        flow.append(Spacer(1, 0.12 * inch))

    flow.append(Spacer(1, 0.15 * inch))
    flow.append(Paragraph("Market positioning", h2))
    flow.append(Paragraph(analysis.get("summary", "—"), body))
    flow.append(Paragraph(f"<b>Differentiators:</b> {_join(analysis.get('differentiators', []))}", body))
    flow.append(Paragraph(f"<b>Threats:</b> {_join(analysis.get('threats', []))}", body))
    flow.append(Paragraph(f"<b>Opportunities:</b> {_join(analysis.get('opportunities', []))}", body))

    doc.build(flow)
    tool_result_log(logger, "export_dashboard_pdf", ok=True, path=str(target))
    return str(target.resolve())


def _short(s: str, n: int) -> str:
    s = s or "—"
    return s if len(s) <= n else s[: n - 1] + "…"


def _join(items: list[str]) -> str:
    return ", ".join(items) if items else "—"
