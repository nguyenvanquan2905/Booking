"""Unit tests for cross-layer trace_id propagation and JSONL trace filtering (MVP-90)."""

from __future__ import annotations

from pathlib import Path

from booking_agent.shared.logging import configure_logging, get_logger
from booking_agent.shared.trace import (
    filter_logs_by_trace_id,
    generate_span_id,
    generate_trace_id,
    get_booking_id,
    get_span_id,
    get_trace_id,
    trace_context,
)


def test_trace_id_context_and_chronological_log_retrieval(tmp_path: Path) -> None:
    tid = generate_trace_id()
    sid = generate_span_id()
    assert tid.startswith("tr_")
    assert sid.startswith("sp_")

    log_path = tmp_path / "trace_events.jsonl"
    configure_logging(level="INFO", jsonl_path=log_path)
    logger = get_logger("test_trace")

    with trace_context(tid, booking_id="bk_trace_1", span_id=sid):
        assert get_trace_id() == tid
        assert get_booking_id() == "bk_trace_1"
        assert get_span_id() == sid
        logger.info("Layer 1 API received request")
        logger.info("Layer 2 Agent normalized input")

    with trace_context("tr_other_999", booking_id="bk_other"):
        logger.info("Unrelated booking log")

    matched = filter_logs_by_trace_id(log_path, tid)
    assert len(matched) == 2
    assert [m["message"] for m in matched] == [
        "Layer 1 API received request",
        "Layer 2 Agent normalized input",
    ]
