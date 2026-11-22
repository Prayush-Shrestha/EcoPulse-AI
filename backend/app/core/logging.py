"""Structured logging for the API process.

Logs are emitted as one JSON object per line. Request identifiers are carried in
a context variable so the HTTP middleware and service logs stay correlated.
Secrets and request bodies are never logged.
"""

from __future__ import annotations

import contextvars
import json
import logging
from datetime import UTC, datetime
from typing import Any

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id",
    default=None,
)

_RESERVED = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Render a log record as a compact JSON document."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id

        for key, value in record.__dict__.items():
            if (
                key not in _RESERVED
                and not key.startswith("_")
                and (isinstance(value, str | int | float | bool) or value is None)
            ):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger once using the structured formatter."""

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn keeps its own handlers; make them use the same structured format.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
