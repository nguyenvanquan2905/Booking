"""Cross-layer trace_id, span_id, and booking_id propagation (MVP-90)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Any

TRACE_HEADER = "X-Trace-Id"

_trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
_span_id_var: ContextVar[str | None] = ContextVar("span_id", default=None)
_booking_id_var: ContextVar[str | None] = ContextVar("booking_id", default=None)


def generate_trace_id() -> str:
    """Generate a globally unique trace identifier."""
    return f"tr_{uuid.uuid4().hex[:24]}"


def generate_span_id() -> str:
    """Generate a span identifier for a sub-operation."""
    return f"sp_{uuid.uuid4().hex[:16]}"


def get_trace_id() -> str | None:
    return _trace_id_var.get()


def get_span_id() -> str | None:
    return _span_id_var.get()


def get_booking_id() -> str | None:
    return _booking_id_var.get()


def set_trace_id(trace_id: str) -> Token[str | None]:
    return _trace_id_var.set(trace_id)


def reset_trace_id(token: Token[str | None]) -> None:
    _trace_id_var.reset(token)


@contextmanager
def trace_context(
    trace_id: str | None = None,
    *,
    booking_id: str | None = None,
    span_id: str | None = None,
) -> Iterator[str]:
    """Bind trace_id (and optional booking_id/span_id) for the active async/sync context."""
    active_trace = trace_id or get_trace_id() or generate_trace_id()
    active_span = span_id or generate_span_id()

    t_token = _trace_id_var.set(active_trace)
    s_token = _span_id_var.set(active_span)
    b_token = _booking_id_var.set(booking_id) if booking_id is not None else None
    try:
        yield active_trace
    finally:
        if b_token is not None:
            _booking_id_var.reset(b_token)
        _span_id_var.reset(s_token)
        _trace_id_var.reset(t_token)


def filter_logs_by_trace_id(jsonl_path: Path, trace_id: str) -> list[dict[str, Any]]:
    """Load and chronologically order all JSONL log entries matching trace_id (MVP-90)."""
    if not jsonl_path.is_file():
        return []
    matched: list[dict[str, Any]] = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        record = json.loads(text)
        if record.get("trace_id") == trace_id:
            matched.append(record)
    matched.sort(key=lambda r: str(r.get("timestamp", "")))
    return matched
