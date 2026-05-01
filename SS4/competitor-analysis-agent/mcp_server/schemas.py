"""Pydantic models shared between MCP tools and the agent."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


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
