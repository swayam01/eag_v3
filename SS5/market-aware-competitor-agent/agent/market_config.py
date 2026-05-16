"""Load MarketConfig from CLI flags or a JSON/YAML file.

Resolution order (later wins):
  1. Built-in defaults (Global market, no filters).
  2. --market-config file (JSON or YAML).
  3. Individual --market-* CLI flags.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from mcp_server.schemas import MarketConfig


def _load_file(path: Path) -> dict[str, Any]:
    text = path.read_text()
    if path.suffix.lower() in (".yaml", ".yml"):
        return yaml.safe_load(text) or {}
    return json.loads(text)


def load_market_config(args: argparse.Namespace) -> MarketConfig:
    data: dict[str, Any] = {}

    if getattr(args, "market_config", None):
        cfg_path = Path(args.market_config).expanduser()
        if not cfg_path.exists():
            raise FileNotFoundError(f"--market-config file not found: {cfg_path}")
        data.update(_load_file(cfg_path))

    overrides: dict[str, Any] = {
        "region": args.market_region,
        "industry_vertical": args.market_industry,
        "customer_segment": args.market_segment,
        "pricing_tier": args.market_pricing_tier,
        "language": args.market_language,
        "geo_strictness": args.market_geo_strictness,
        "notes": args.market_notes,
    }
    if args.market_countries:
        overrides["countries"] = [c.strip() for c in args.market_countries.split(",") if c.strip()]
    if args.market_channels:
        overrides["channels"] = [c.strip() for c in args.market_channels.split(",") if c.strip()]
    if args.market_must_have:
        overrides["must_have_keywords"] = [
            c.strip() for c in args.market_must_have.split(",") if c.strip()
        ]
    if args.market_exclude:
        overrides["exclude_keywords"] = [
            c.strip() for c in args.market_exclude.split(",") if c.strip()
        ]

    for k, v in overrides.items():
        if v is not None:
            data[k] = v

    return MarketConfig(**data)


def add_market_flags(parser: argparse.ArgumentParser) -> None:
    g = parser.add_argument_group("Market configuration")
    g.add_argument("--market-config", help="Path to a JSON or YAML MarketConfig file.")
    g.add_argument("--market-region", help="Region label, e.g. 'India', 'North America'.")
    g.add_argument(
        "--market-countries",
        help="Comma-separated country whitelist, e.g. 'India,Bangladesh'.",
    )
    g.add_argument("--market-industry", help="Industry vertical, e.g. 'B2B CRM SaaS'.")
    g.add_argument(
        "--market-segment",
        choices=["B2B", "B2C", "B2B2C", "B2G", "Mixed"],
        help="Customer segment.",
    )
    g.add_argument(
        "--market-pricing-tier",
        choices=["budget", "mid-market", "premium", "enterprise", "mixed"],
        help="Target pricing tier.",
    )
    g.add_argument(
        "--market-channels",
        help="Comma-separated channels, e.g. 'web app,iOS,Android'.",
    )
    g.add_argument("--market-language", help="Primary content language. Default 'English'.")
    g.add_argument(
        "--market-geo-strictness",
        choices=["strict", "primary", "loose"],
        help="strict=HQ in region, primary=serves region (default), loose=any global player.",
    )
    g.add_argument(
        "--market-must-have",
        help="Comma-separated must-have keywords for a candidate to qualify.",
    )
    g.add_argument(
        "--market-exclude",
        help="Comma-separated keywords that disqualify a candidate.",
    )
    g.add_argument(
        "--market-notes",
        help="Free-form market context the agent should weigh.",
    )
