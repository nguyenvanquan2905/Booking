"""Unit tests for 4-layer telemetry schema, seams, exports & SA report (MVP-01/03/04/05)."""

from __future__ import annotations

from pathlib import Path

from booking_agent.shared.trace import trace_context
from booking_agent.telemetry.schema import (
    EventStatus,
    TelemetryEvent,
    TelemetryLayer,
    TokenCounter,
    export_events_csv,
    export_events_jsonl,
    make_agent_event,
    render_sa_report_template,
    summarize_telemetry,
)


def test_telemetry_event_redacts_pii_has_seams_and_serializes(tmp_path: Path) -> None:
    with trace_context("tr_tel_1", booking_id="bk_tel_1"):
        evt = make_agent_event(
            "booking_started",
            tier=2,
            artifact_id="art_001",
            cache_hit=True,
            cold_warm="warm",
            loop_count=1,
            token_count=250,
            duration_ms=42.5,
            message="User phone 0912345678 booked",
            customer_email="demo@example.com",
            site_id="pasgo",
        )

    assert evt.layer == TelemetryLayer.LAYER_2_AGENT
    assert evt.trace_id == "tr_tel_1"
    assert evt.booking_id == "bk_tel_1"
    assert evt.tier_used == 2
    assert evt.artifact_id == "art_001"
    assert evt.cache_hit is True
    assert evt.cold_warm == "warm"
    assert evt.loop_count == 1
    assert evt.status == EventStatus.SUCCEEDED
    assert "0912345678" not in evt.message
    assert evt.attributes["customer_email"] != "demo@example.com"

    # MVP-04: 4 nullable self-learning seam fields
    assert evt.seam_api_template_id is None
    assert evt.seam_playwright_workflow_id is None
    assert evt.seam_dom_signature is None
    assert evt.seam_replay_payload is None

    params = evt.to_db_params()
    assert params["layer"] == "layer2_agent"
    assert params["tier"] == 2
    assert "demo@example.com" not in params["payload_json"]

    # MVP-03 export & p50/p95 summary
    evt2 = make_agent_event("step2", duration_ms=100.0, token_count=150)
    summary = summarize_telemetry([evt, evt2])
    assert summary.total_events == 2
    assert summary.total_tokens == 400
    assert summary.p50_ms == 71.25
    assert summary.p95_ms > 95.0

    csv_file = export_events_csv([evt, evt2], tmp_path / "tel.csv")
    jsonl_file = export_events_jsonl([evt, evt2], tmp_path / "tel.jsonl")
    assert csv_file.exists() and "tier_used" in csv_file.read_text(encoding="utf-8")
    assert jsonl_file.exists() and len(jsonl_file.read_text(encoding="utf-8").splitlines()) == 2


def test_token_counter_and_sa_report_template() -> None:
    counter = TokenCounter()
    counter.add(prompt=120, completion=30)
    counter.add(prompt=80, completion=20)
    assert counter.total_tokens == 250

    report = render_sa_report_template()
    assert "Bảng Hạ tầng" in report
    assert "Bảng Điều khiển" in report
    assert "Bảng Anti-bot" in report
    assert "Bảng Chi phí" in report
    assert "Khuyến nghị" in report
    assert "Điều chưa kiểm chứng" in report


def test_telemetry_accepts_all_four_layers() -> None:
    for layer in (
        TelemetryLayer.LAYER_1_API,
        TelemetryLayer.LAYER_2_AGENT,
        TelemetryLayer.LAYER_3_BROWSER,
        TelemetryLayer.LAYER_4_INFRA,
    ):
        evt = TelemetryEvent(layer=layer, component="test", event_name="ping")
        assert evt.layer == layer
