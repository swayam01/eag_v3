"""Tool C — Prefab UI bridge.

Persists dashboard state to data/dashboard_state.json, then either:
  * starts `prefab serve` (live, hot-reloading) and returns the URL, or
  * runs `prefab export` and returns a file:// path to the static HTML.

A single live-serve subprocess is reused across calls; subsequent
update_dashboard_section() calls just rewrite the state file and the live
server hot-reloads.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from filelock import FileLock

from mcp_server.logging_setup import setup_logging, tool_call_log, tool_result_log
from mcp_server.schemas import DashboardHandle

logger = setup_logging("competitor_mcp.prefab")

ROOT = Path(__file__).resolve().parent.parent.parent
STATE_PATH = ROOT / "data" / "dashboard_state.json"
STATE_LOCK = STATE_PATH.with_suffix(".json.lock")
DASHBOARD_PY = ROOT / "dashboard_app" / "dashboard.py"
EXPORT_HTML = ROOT / "data" / "dashboard.html"

_serve_proc: subprocess.Popen | None = None
_serve_url: str | None = None


def _empty_state() -> dict[str, Any]:
    return {"product": {}, "competitors": [], "analysis": {}, "updated_at": _now()}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return _empty_state()
    try:
        return json.loads(STATE_PATH.read_text())
    except json.JSONDecodeError:
        return _empty_state()


def _write_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _now()
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def _ensure_prefab_cli() -> str:
    cli = shutil.which("prefab")
    if not cli:
        raise RuntimeError(
            "`prefab` CLI not found on PATH. Install with `uv add prefab-ui` or "
            "`pip install prefab-ui`, then ensure your venv is active."
        )
    return cli


def _start_serve() -> tuple[str, int]:
    global _serve_proc, _serve_url
    if _serve_proc and _serve_proc.poll() is None and _serve_url:
        return _serve_url, _serve_proc.pid

    cli = _ensure_prefab_cli()
    host = "127.0.0.1"
    port = int(os.environ.get("PREFAB_PORT", "8765"))

    cmd = [cli, "serve", str(DASHBOARD_PY), "--port", str(port), "--reload"]
    logger.info("Starting prefab serve: %s", " ".join(cmd))
    _serve_proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    time.sleep(1.5)
    if _serve_proc.poll() is not None:
        raise RuntimeError(
            f"prefab serve exited immediately (rc={_serve_proc.returncode}). "
            "Check `prefab serve dashboard_app/dashboard.py` manually for errors."
        )
    _serve_url = f"http://{host}:{port}"
    return _serve_url, _serve_proc.pid


def _export_static() -> str:
    cli = _ensure_prefab_cli()
    EXPORT_HTML.parent.mkdir(parents=True, exist_ok=True)
    cmd = [cli, "export", str(DASHBOARD_PY), "-o", str(EXPORT_HTML)]
    logger.info("Exporting prefab static: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"prefab export failed:\n{result.stderr}")
    return f"file://{EXPORT_HTML}"


def render_dashboard(
    your_product: dict[str, Any],
    competitors: list[dict[str, Any]],
    analysis: dict[str, Any] | None = None,
    mode: Literal["live", "static"] = "live",
) -> dict[str, Any]:
    """Push the full dashboard to Prefab.

    `mode="live"` starts (or reuses) `prefab serve` and returns its URL.
    `mode="static"` runs `prefab export` and returns a file:// path.
    """
    tool_call_log(
        logger,
        "render_dashboard",
        product=your_product.get("name"),
        competitor_count=len(competitors),
        mode=mode,
    )
    with FileLock(str(STATE_LOCK), timeout=10):
        _write_state(
            {"product": your_product, "competitors": competitors, "analysis": analysis or {}}
        )

    if mode == "static":
        url = _export_static()
        handle = DashboardHandle(url=url, mode="static")
    else:
        url, pid = _start_serve()
        handle = DashboardHandle(url=url, mode="live", pid=pid)

    tool_result_log(logger, "render_dashboard", ok=True, url=handle.url, mode=handle.mode)
    return handle.model_dump()


def update_dashboard_section(
    section: Literal["product", "table", "cards", "positioning"],
    content: dict[str, Any],
) -> bool:
    """Patch a single section in the live dashboard.

    `section`:
      - 'product'      → replaces state['product']
      - 'table'/'cards'→ replaces state['competitors'] (both views share data)
      - 'positioning'  → replaces state['analysis']
    """
    tool_call_log(logger, "update_dashboard_section", section=section)
    with FileLock(str(STATE_LOCK), timeout=10):
        state = _read_state()
        if section == "product":
            state["product"] = content
        elif section in ("table", "cards"):
            state["competitors"] = content.get("competitors", content) if isinstance(content, dict) else content
        elif section == "positioning":
            state["analysis"] = content
        else:
            raise ValueError(f"Unknown section: {section}")
        _write_state(state)
    tool_result_log(logger, "update_dashboard_section", ok=True, section=section)
    return True


def stop_dashboard() -> bool:
    """Stop the live serve subprocess if running. Useful between demo runs."""
    global _serve_proc, _serve_url
    if _serve_proc and _serve_proc.poll() is None:
        _serve_proc.terminate()
        try:
            _serve_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _serve_proc.kill()
        _serve_proc = None
        _serve_url = None
        logger.info("prefab serve stopped")
        return True
    return False
