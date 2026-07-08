"""Structured JSON logging for all ACDE components.

Every log line is a single JSON object with at least ``ts``, ``level``,
``component`` and ``event``; ``experiment_run`` and arbitrary structured extras
pass through so any experiment can be reconstructed from logs alone.

Usage::

    log = get_logger("chaos.injector")
    log.info("fault_injected", extra={"experiment_run": run, "fault_type": "schema_drift"})
"""

import datetime as _dt
import json
import logging
import sys
from typing import Any

# Attributes present on every LogRecord; anything else was passed via ``extra``.
_STANDARD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class JSONFormatter(logging.Formatter):
    """Render a LogRecord as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": _dt.datetime.fromtimestamp(record.created, tz=_dt.UTC).isoformat(),
            "level": record.levelname,
            "component": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: str | None = None) -> None:
    """Configure the root logger with a JSON stdout handler (idempotent)."""
    from acde.config import get_settings

    root = logging.getLogger()
    root.setLevel(level or get_settings().log_level)
    if not any(isinstance(h.formatter, JSONFormatter) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        root.addHandler(handler)


def get_logger(component: str) -> logging.Logger:
    """Return a logger named after the ACDE component (e.g. ``agents.recovery``)."""
    setup_logging()
    return logging.getLogger(component)
