"""Pydantic models shared between MCP tools and the agent."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


CustomerSegment = Literal["B2B", "B2C", "B2B2C", "B2G", "Mixed"]
PricingTier = Literal["budget", "mid-market", "premium", "enterprise", "mixed"]
GeoStrictness = Literal["strict", "primary", "loose"]


class MarketConfig(BaseModel):
    """Configurable market the agent should research competitors for.

    Drives which results are kept vs. filtered out, which queries the agent
    issues, and how each competitor is scored. Loaded from a JSON/YAML file
    (--market-config) or assembled from CLI flags.
    """

    region: str = Field(
        default="Global",
        description="Geographic market, e.g. 'India', 'North America', 'Europe', 'Global'.",
    )
    countries: list[str] = Field(
        default_factory=list,
        description="Optional explicit country whitelist, e.g. ['India','Bangladesh'].",
    )
    industry_vertical: str = Field(
        default="",
        description="Industry / vertical, e.g. 'interior design tech', 'CRM SaaS'.",
    )
    customer_segment: CustomerSegment = "Mixed"
    pricing_tier: PricingTier = "mixed"
    channels: list[str] = Field(
        default_factory=list,
        description="Distribution channels, e.g. ['web app','iOS','retail partners'].",
    )
    language: str = Field(
        default="English",
        description="Primary content language. Drives search query language.",
    )
    geo_strictness: GeoStrictness = Field(
        default="primary",
        description=(
            "strict = HQ must be in region; "
            "primary = company primarily serves the region (default); "
            "loose = any global player that addresses the region."
        ),
    )
    must_have_keywords: list[str] = Field(
        default_factory=list,
        description="Keep candidate only if any of these appear in its profile.",
    )
    exclude_keywords: list[str] = Field(
        default_factory=list,
        description="Drop candidate if any of these appear in name/description.",
    )
    notes: str = Field(
        default="",
        description="Free-form market context the agent should weigh (regulations, buying habits, etc.).",
    )

    def to_brief(self) -> str:
        """Render a compact human-readable brief the agent can paste into prompts."""
        lines = [f"region={self.region}"]
        if self.countries:
            lines.append("countries=" + ",".join(self.countries))
        if self.industry_vertical:
            lines.append(f"vertical={self.industry_vertical}")
        lines.append(f"segment={self.customer_segment}")
        lines.append(f"pricing_tier={self.pricing_tier}")
        if self.channels:
            lines.append("channels=" + ",".join(self.channels))
        lines.append(f"language={self.language}")
        lines.append(f"geo_strictness={self.geo_strictness}")
        if self.must_have_keywords:
            lines.append("must_have=" + ",".join(self.must_have_keywords))
        if self.exclude_keywords:
            lines.append("exclude=" + ",".join(self.exclude_keywords))
        if self.notes:
            lines.append(f"notes={self.notes}")
        return " | ".join(lines)


class ProductInput(BaseModel):
    name: str
    url: str | None = None
    description: str
    category: str
    target_market: str | None = None
    pricing: str | None = None


class SearchHit(BaseModel):
    name: str
    url: str
    snippet: str
    source: Literal["tavily", "duckduckgo"] = "duckduckgo"


class PageContent(BaseModel):
    url: str
    title: str
    cleaned_text: str
    pricing_hints: list[str] = Field(default_factory=list)
    feature_mentions: list[str] = Field(default_factory=list)
    cached: bool = False
    fetched_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CompetitorRecord(BaseModel):
    name: str
    website: str
    description: str
    pricing: str = ""
    features: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    target_market: str = ""
    headquarters: str = Field(
        default="",
        description="Company HQ as 'City, Country'. Researched via a separate web "
        "search, not just the company's own About page.",
    )
    market_fit_score: int = Field(
        default=0,
        ge=0,
        le=10,
        description="0–10 score for how well this competitor fits the configured market. "
        "The agent assigns it after applying MarketConfig filters.",
    )
    market_fit_reason: str = Field(
        default="",
        description="One-sentence justification for market_fit_score, referencing MarketConfig.",
    )
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PositioningAnalysis(BaseModel):
    summary: str
    differentiators: list[str] = Field(default_factory=list)
    threats: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)


class DashboardHandle(BaseModel):
    url: str
    mode: Literal["live", "static"]
    served_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    pid: int | None = None
