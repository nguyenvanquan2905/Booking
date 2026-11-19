"""4-layer telemetry log contract, token counter, summary & SA template (MVP-01/03/04/05/91)."""

from __future__ import annotations

import csv
import json
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from booking_agent.shared.pii import redact_pii_in_dict, redact_pii_in_text
from booking_agent.shared.trace import get_booking_id, get_trace_id


class TelemetryLayer(StrEnum):
    """Four architectural telemetry layers."""

    LAYER_1_API = "layer1_api"
    LAYER_2_AGENT = "layer2_agent"
    LAYER_3_BROWSER = "layer3_browser"
    LAYER_4_INFRA = "layer4_infra"


class EventStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    HITL_PAUSED = "hitl_paused"


class TelemetryEvent(BaseModel):
    """Canonical 4-layer structured log contract (MVP-01, MVP-04, MVP-91)."""

    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:20]}")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trace_id: str = Field(default_factory=lambda: get_trace_id() or "tr_unknown")
    booking_id: str | None = Field(default_factory=get_booking_id)
    layer: TelemetryLayer
    component: str = Field(min_length=1)
    event_name: str = Field(min_length=1)
    status: EventStatus = EventStatus.SUCCEEDED
    tier: int | None = Field(default=None, ge=1, le=4)
    tier_used: int | None = Field(default=None, ge=1, le=4)
    artifact_id: str | None = None
    cache_hit: bool = False
    cold_warm: Literal["cold", "warm"] = "cold"
    loop_count: int = Field(default=0, ge=0)
    token_count: int = Field(default=0, ge=0)
    duration_ms: float | None = Field(default=None, ge=0.0)
    cost_usd: float | None = Field(default=None, ge=0.0)
    error_code: str | None = None
    error_class: str | None = None
    message: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)

    # MVP-04: 4 nullable self-learning seam fields (reserved as None in MVP)
    seam_api_template_id: str | None = None
    seam_playwright_workflow_id: str | None = None
    seam_dom_signature: str | None = None
    seam_replay_payload: dict[str, Any] | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.tier_used is None and self.tier is not None:
            self.tier_used = self.tier
        elif self.tier is None and self.tier_used is not None:
            self.tier = self.tier_used

    @field_validator("message")
    @classmethod
    def _redact_message(cls, value: str) -> str:
        return redact_pii_in_text(value) if value else value

    @field_validator("attributes")
    @classmethod
    def _redact_attributes(cls, value: dict[str, Any]) -> dict[str, Any]:
        return redact_pii_in_dict(value) if value else value

    def to_db_params(self) -> dict[str, Any]:
        """Serialize to parameters matching telemetry_events table columns."""
        return {
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "booking_id": self.booking_id,
            "layer": str(self.layer),
            "component": self.component,
            "event_name": self.event_name,
            "status": str(self.status),
            "tier": self.tier_used or self.tier,
            "duration_ms": self.duration_ms,
            "cost_usd": self.cost_usd,
            "error_code": self.error_code,
            "payload_json": json.dumps(
                {
                    "message": self.message,
                    "artifact_id": self.artifact_id,
                    "cache_hit": self.cache_hit,
                    "cold_warm": self.cold_warm,
                    "loop_count": self.loop_count,
                    "token_count": self.token_count,
                    "error_class": self.error_class,
                    "attributes": self.attributes,
                },
                ensure_ascii=False,
            ),
            "created_at": self.timestamp.isoformat(),
        }


@dataclass(slots=True)
class TokenCounter:
    """Tracks prompt & completion tokens per booking run (MVP-03)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, *, prompt: int = 0, completion: int = 0) -> None:
        self.prompt_tokens += max(0, prompt)
        self.completion_tokens += max(0, completion)


@dataclass(slots=True)
class TelemetrySummary:
    """Summary statistics computed from TelemetryEvent list (MVP-03)."""

    total_events: int
    succeeded_count: int
    success_rate: float
    p50_ms: float
    p95_ms: float
    total_tokens: int


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return sorted_values[low]
    weight = rank - low
    return sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight


def summarize_telemetry(events: list[TelemetryEvent]) -> TelemetrySummary:
    """Compute p50/p95 latency, token totals, and success rate from telemetry events."""
    latencies = sorted(float(e.duration_ms) for e in events if e.duration_ms is not None)
    total = len(events)
    succeeded = sum(1 for e in events if e.status == EventStatus.SUCCEEDED)
    tokens = sum(e.token_count for e in events)
    return TelemetrySummary(
        total_events=total,
        succeeded_count=succeeded,
        success_rate=(succeeded / total) if total else 0.0,
        p50_ms=round(_percentile(latencies, 50.0), 3),
        p95_ms=round(_percentile(latencies, 95.0), 3),
        total_tokens=tokens,
    )


def export_events_jsonl(events: list[TelemetryEvent], path: Path) -> Path:
    """Write telemetry events to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for evt in events:
            fh.write(evt.model_dump_json() + "\n")
    return path


def export_events_csv(events: list[TelemetryEvent], path: Path) -> Path:
    """Write telemetry events to a flat CSV file matching MVP-01/MVP-03 schema."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "event_id",
        "timestamp",
        "trace_id",
        "booking_id",
        "layer",
        "component",
        "event_name",
        "status",
        "tier_used",
        "artifact_id",
        "cache_hit",
        "cold_warm",
        "loop_count",
        "token_count",
        "duration_ms",
        "cost_usd",
        "error_code",
        "error_class",
        "message",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for evt in events:
            writer.writerow(
                {
                    "event_id": evt.event_id,
                    "timestamp": evt.timestamp.isoformat(),
                    "trace_id": evt.trace_id,
                    "booking_id": evt.booking_id or "",
                    "layer": str(evt.layer),
                    "component": evt.component,
                    "event_name": evt.event_name,
                    "status": str(evt.status),
                    "tier_used": evt.tier_used if evt.tier_used is not None else "",
                    "artifact_id": evt.artifact_id or "",
                    "cache_hit": evt.cache_hit,
                    "cold_warm": evt.cold_warm,
                    "loop_count": evt.loop_count,
                    "token_count": evt.token_count,
                    "duration_ms": evt.duration_ms if evt.duration_ms is not None else "",
                    "cost_usd": evt.cost_usd if evt.cost_usd is not None else "",
                    "error_code": evt.error_code or "",
                    "error_class": evt.error_class or "",
                    "message": evt.message,
                }
            )
    return path


def make_agent_event(
    event_name: str,
    *,
    component: str = "agent.graph",
    status: EventStatus = EventStatus.SUCCEEDED,
    booking_id: str | None = None,
    trace_id: str | None = None,
    tier: int | None = None,
    artifact_id: str | None = None,
    cache_hit: bool = False,
    cold_warm: Literal["cold", "warm"] = "cold",
    loop_count: int = 0,
    token_count: int = 0,
    duration_ms: float | None = None,
    error_code: str | None = None,
    error_class: str | None = None,
    message: str = "",
    **attributes: Any,
) -> TelemetryEvent:
    """Factory for Layer 2 (Agent) telemetry events."""
    return TelemetryEvent(
        trace_id=trace_id or get_trace_id() or "tr_unknown",
        booking_id=booking_id or get_booking_id(),
        layer=TelemetryLayer.LAYER_2_AGENT,
        component=component,
        event_name=event_name,
        status=status,
        tier=tier,
        tier_used=tier,
        artifact_id=artifact_id,
        cache_hit=cache_hit,
        cold_warm=cold_warm,
        loop_count=loop_count,
        token_count=token_count,
        duration_ms=duration_ms,
        error_code=error_code,
        error_class=error_class,
        message=message,
        attributes=attributes,
    )


def render_sa_report_template() -> str:
    """Return the SA evaluation report skeleton (MVP-05)."""
    return """# Báo cáo Đánh giá Kiến trúc — vb-browser-use (Web-only MVP)

## 1. Bảng Hạ tầng (Sandbox & Browser Infra)
| Engine / Sandbox | Cold-start (ms) | RAM 1 phiên (MB) | RAM 3–5 phiên (MB) | Ghi chú |
|---|---|---|---|---|
| Chromium / Patchright | — | — | — | — |
| Camoufox | — | — | — | — |

## 2. Bảng Điều khiển (4 Cấp Thác Đổ)
| Cấp | Success Rate (%) | p50 Latency (ms) | p95 Latency (ms) | Token / bước |
|---|---|---|---|---|
| Cấp 1 — API Replay | — | — | — | 0 |
| Cấp 2 — Playwright | — | — | — | 0 |
| Cấp 3 — Stagehand + BAML | — | — | — | — |
| Cấp 4 — Vision API | — | — | — | — |

## 3. Bảng Anti-bot
| Engine | Browserscan / CreepJS | Cloudflare Turnstile | Tỷ lệ bị chặn (%) |
|---|---|---|---|
| Chromium / Patchright | — | — | — |
| Camoufox | — | — | — |

## 4. Bảng Chi phí ($ / đơn đặt bàn thành công)
| Tổ hợp công nghệ | Compute | Token LLM | Proxy | Lưu trữ | Tổng $/task |
|---|---|---|---|---|---|
| Cấp 1/2 (Web chuẩn) | — | — | — | — | — |
| Cấp 3/4 (Loại B / Anti-bot) | — | — | — | — | — |

## 5. Khuyến nghị cho SA
- (Điền sau khi chạy benchmark trên tập site đã đóng băng)

## 6. Điều chưa kiểm chứng
- Ngưỡng nghẽn ghi SQLite khi tải cao trên cấu hình máy đo thực tế.
- Chi phí proxy thực tế khi mở rộng vượt quá 1 máy.
"""


@dataclass(slots=True)
class Mvp18ScenarioMetric:
    """Per-scenario acceptance metrics for MVP-18 4-criteria report table."""

    scenario_name: str
    passed: bool
    latency_per_step_ms: float
    tokens_per_step: float
    hibernate_ram_mb: float = 0.0


def render_mvp18_acceptance_table(metrics: list[Mvp18ScenarioMetric]) -> str:
    """Format the MVP-18 4-criteria acceptance table (latency/step, token/step, RAM, pass rate)."""
    total = len(metrics)
    passed_count = sum(1 for m in metrics if m.passed)
    pass_rate = (passed_count / total * 100.0) if total else 0.0

    lines = [
        "| Kịch bản E2E (MVP-18) | Latency / bước (ms) | Token / bước "
        "| RAM lúc hibernate (MB) | Kết quả |",
        "|---|---:|---:|---:|---|",
    ]
    for m in metrics:
        verdict = "PASS" if m.passed else "FAIL"
        lines.append(
            f"| {m.scenario_name} | {m.latency_per_step_ms:.2f} | "
            f"{m.tokens_per_step:.1f} | {m.hibernate_ram_mb:.1f} | {verdict} |"
        )
    lines.append(f"\n**Tỷ lệ pass tổng hợp:** {passed_count}/{total} ({pass_rate:.1f}%)")
    return "\n".join(lines)

