"""JSONL structured logging with trace_id and automatic PII redaction (MVP-01)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from booking_agent.shared.pii import redact_pii_in_dict, redact_pii_in_text
from booking_agent.shared.trace import get_booking_id, get_span_id, get_trace_id

_STANDARD_LOG_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
    "message",
    "asctime",
}


class JsonlFormatter(logging.Formatter):
    """Formats log records as single-line JSON with trace context and PII redaction."""

    def format(self, record: logging.LogRecord) -> str:
        raw_message = record.getMessage()
        extra_fields: dict[str, Any] = {
            k: v for k, v in record.__dict__.items() if k not in _STANDARD_LOG_ATTRS
        }
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "trace_id": getattr(record, "trace_id", None) or get_trace_id(),
            "span_id": getattr(record, "span_id", None) or get_span_id(),
            "booking_id": getattr(record, "booking_id", None) or get_booking_id(),
            "message": redact_pii_in_text(raw_message),
        }
        if extra_fields:
            payload["extra"] = redact_pii_in_dict(extra_fields)
        if record.exc_info:
            payload["exception"] = redact_pii_in_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(
    level: str = "INFO",
    jsonl_path: Path | None = None,
) -> logging.Logger:
    """Configure root booking_agent logger with JSONL formatting."""
    logger = logging.getLogger("booking_agent")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    formatter = JsonlFormatter()
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if jsonl_path is not None:
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(jsonl_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the booking_agent namespace."""
    if name.startswith("booking_agent"):
        return logging.getLogger(name)
    return logging.getLogger(f"booking_agent.{name}")
