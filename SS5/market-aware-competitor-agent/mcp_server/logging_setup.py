"""Rich-formatted logging to stdout + a rotating file at logs/agent.log.

The MCP stdio transport uses stdout for protocol frames, so all logging goes
to stderr. The log file mirrors stderr for the YouTube demo.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "agent.log"

_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(name: str = "competitor_mcp", level: int = logging.INFO) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter(_FMT, datefmt=_DATEFMT)

    stderr = logging.StreamHandler(sys.stderr)
    stderr.setFormatter(formatter)
    logger.addHandler(stderr)

    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def tool_call_log(logger: logging.Logger, tool: str, **kwargs) -> None:
    """One-line structured log line per tool invocation."""
    args = " ".join(f"{k}={_truncate(v)}" for k, v in kwargs.items())
    logger.info("TOOL_CALL %s %s", tool, args)


def tool_result_log(logger: logging.Logger, tool: str, ok: bool, **kwargs) -> None:
    status = "OK" if ok else "FAIL"
    args = " ".join(f"{k}={_truncate(v)}" for k, v in kwargs.items())
    logger.info("TOOL_RESULT %s %s %s", tool, status, args)


def _truncate(value: object, n: int = 120) -> str:
    s = str(value).replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"
