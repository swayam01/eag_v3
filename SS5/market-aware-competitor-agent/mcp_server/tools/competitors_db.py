"""Tool B — Local competitors database (JSON store with file locking).

All operations are atomic: read → mutate → write under an exclusive
filelock so concurrent agent runs don't corrupt the store.
Records are keyed by lowercased name (case-insensitive uniqueness).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock

from mcp_server.logging_setup import setup_logging, tool_call_log, tool_result_log
from mcp_server.schemas import CompetitorRecord

logger = setup_logging("competitor_mcp.db")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "competitors.json"
LOCK_PATH = DB_PATH.with_suffix(".json.lock")


def _ensure_file() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        DB_PATH.write_text("[]\n")


def _read_all() -> list[dict[str, Any]]:
    _ensure_file()
    raw = DB_PATH.read_text().strip() or "[]"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("competitors.json corrupted, resetting to []")
        data = []
    return data if isinstance(data, list) else []


def _write_all(records: list[dict[str, Any]]) -> None:
    DB_PATH.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _matches(record: dict[str, Any], filter: dict[str, Any]) -> bool:
    for k, v in filter.items():
        rv = record.get(k)
        if isinstance(v, str) and isinstance(rv, str):
            if v.lower() not in rv.lower():
                return False
        elif rv != v:
            return False
    return True


def create_competitor(record: dict[str, Any]) -> dict[str, Any]:
    """Insert a new competitor. Errors if the name (case-insensitive) exists."""
    parsed = CompetitorRecord(**record)
    parsed.last_updated = _now()
    tool_call_log(logger, "create_competitor", name=parsed.name)
    with FileLock(str(LOCK_PATH), timeout=10):
        records = _read_all()
        if any(r.get("name", "").lower() == parsed.name.lower() for r in records):
            tool_result_log(logger, "create_competitor", ok=False, name=parsed.name, error="duplicate")
            raise ValueError(
                f"Competitor '{parsed.name}' already exists. Use update_competitor instead."
            )
        records.append(parsed.model_dump())
        _write_all(records)
    tool_result_log(logger, "create_competitor", ok=True, name=parsed.name)
    return parsed.model_dump()


def read_competitors(filter: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return records matching the filter (substring match on string fields)."""
    tool_call_log(logger, "read_competitors", filter=filter)
    with FileLock(str(LOCK_PATH), timeout=10):
        records = _read_all()
    if filter:
        records = [r for r in records if _matches(r, filter)]
    tool_result_log(logger, "read_competitors", ok=True, count=len(records))
    return records


def update_competitor(name: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Patch the named record. Adds/overwrites fields; refreshes last_updated."""
    tool_call_log(logger, "update_competitor", name=name, fields=list(updates.keys()))
    with FileLock(str(LOCK_PATH), timeout=10):
        records = _read_all()
        target_idx = next(
            (i for i, r in enumerate(records) if r.get("name", "").lower() == name.lower()),
            None,
        )
        if target_idx is None:
            tool_result_log(logger, "update_competitor", ok=False, name=name, error="not found")
            raise ValueError(f"Competitor '{name}' not found.")
        merged = {**records[target_idx], **updates, "last_updated": _now()}
        validated = CompetitorRecord(**merged).model_dump()
        records[target_idx] = validated
        _write_all(records)
    tool_result_log(logger, "update_competitor", ok=True, name=name)
    return validated


def delete_competitor(name: str) -> bool:
    """Remove a record by name. Returns True if removed, False if not found."""
    tool_call_log(logger, "delete_competitor", name=name)
    with FileLock(str(LOCK_PATH), timeout=10):
        records = _read_all()
        before = len(records)
        records = [r for r in records if r.get("name", "").lower() != name.lower()]
        removed = len(records) < before
        if removed:
            _write_all(records)
    tool_result_log(logger, "delete_competitor", ok=True, name=name, removed=removed)
    return removed


def clear_database() -> int:
    """Wipe all records. Returns the count cleared. Use for fresh runs."""
    tool_call_log(logger, "clear_database")
    with FileLock(str(LOCK_PATH), timeout=10):
        records = _read_all()
        count = len(records)
        _write_all([])
    tool_result_log(logger, "clear_database", ok=True, cleared=count)
    return count
