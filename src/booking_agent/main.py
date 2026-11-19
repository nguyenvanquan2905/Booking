"""FastAPI backend entrypoint and JSON CLI runner (MVP-03 — owner: C)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from booking_agent.agent.checkpointer import create_checkpointer
from booking_agent.agent.guardrails.layer3_hitl import HitlManager
from booking_agent.agent.queue import DurableQueue
from booking_agent.agent.registry import ProfileHealthMonitor, TierRegistry
from booking_agent.agent.router import (
    BrowserControlPort,
    BrowserExecutionRequest,
    BrowserExecutionResult,
    TaskStatusCode,
)
from booking_agent.booking.models import BookingCreateRequest
from booking_agent.booking.service import BookingService
from booking_agent.shared.clock import SystemClock
from booking_agent.shared.config import Settings, get_settings
from booking_agent.shared.db import DatabasePool
from booking_agent.shared.logging import configure_logging, get_logger
from booking_agent.shared.pii import PiiCipher
from booking_agent.telemetry.schema import (
    export_events_csv,
    export_events_jsonl,
    summarize_telemetry,
)

_logger = get_logger("main")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the backend FastAPI application."""
    cfg = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging(level=cfg.log_level, jsonl_path=cfg.log_jsonl_path)
        clock = SystemClock()
        db = DatabasePool(cfg.db_path, busy_timeout_ms=cfg.sqlite_busy_timeout_ms)
        await db.init()

        cipher = PiiCipher(cfg.pii_encryption_key)
        booking_service = BookingService(
            db,
            cipher=cipher,
            clock=clock,
            pii_ttl_days=cfg.pii_ttl_days,
            idempotency_ttl_seconds=cfg.booking_idempotency_ttl_seconds,
        )
        tier_registry = TierRegistry(db, clock=clock)
        hitl_manager = HitlManager(
            db,
            clock=clock,
            default_timeout_seconds=cfg.hitl_timeout_seconds,
        )
        queue = DurableQueue(db, clock=clock)
        profile_health = ProfileHealthMonitor(db, cipher, clock=clock)

        async with create_checkpointer(
            cfg.db_path,
            busy_timeout_ms=cfg.sqlite_busy_timeout_ms,
        ) as checkpointer:
            application.state.settings = cfg
            application.state.clock = clock
            application.state.db = db
            application.state.booking_service = booking_service
            application.state.tier_registry = tier_registry
            application.state.hitl_manager = hitl_manager
            application.state.queue = queue
            application.state.profile_health = profile_health
            application.state.checkpointer = checkpointer
            _logger.info("Booking Agent backend initialized", extra={"db_path": str(cfg.db_path)})
            try:
                yield
            finally:
                await db.close()
                _logger.info("Booking Agent backend shut down")

    application = FastAPI(
        title=cfg.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "app": cfg.app_name, "env": cfg.app_env}

    return application


app = create_app()


class DryRunBrowserControl:
    """Offline BrowserControlPort stand-in so the MVP-03 runner works before D ships tiers.

    Tier 1 reports "no template" (retryable) and Tier 2 confirms, exercising the real
    fallback path, telemetry and checkpointing without opening a browser.
    """

    async def supports_tier(self, site_id: str, tier: int) -> bool:
        return tier in (1, 2)

    async def execute_booking(self, request: BrowserExecutionRequest) -> BrowserExecutionResult:
        if request.tier == 1:
            return BrowserExecutionResult(
                success=False,
                tier_used=1,
                retryable=True,
                status_code=TaskStatusCode.FALLBACK_FAILED,
                failure_code="NO_API_TEMPLATE",
                error_message="Dry-run: no API template recorded",
            )
        return BrowserExecutionResult(
            success=True,
            tier_used=request.tier,
            status_code=TaskStatusCode.SUCCESS,
            confirmation_code=f"DRYRUN-{request.site_id.upper()}-T{request.tier}",
            artifact_id=f"art_dryrun_{request.booking_id}",
        )


async def run_json_booking(
    input_json_path: Path,
    *,
    output_dir: Path,
    settings: Settings | None = None,
    browser_control: BrowserControlPort | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """MVP-03 runner: load JSON booking payload, execute booking workflow & export CSV/JSONL."""
    from booking_agent.agent.graph import BookingAgentRunner
    from booking_agent.agent.router import MasterRouter

    cfg = settings or get_settings()
    raw = json.loads(input_json_path.read_text(encoding="utf-8"))
    request = BookingCreateRequest.model_validate(raw)
    port = browser_control or (DryRunBrowserControl() if dry_run else None)

    clock = SystemClock()
    db = DatabasePool(cfg.db_path, busy_timeout_ms=cfg.sqlite_busy_timeout_ms)
    await db.init()
    cipher = PiiCipher(cfg.pii_encryption_key)
    booking_service = BookingService(db, cipher=cipher, clock=clock)
    tier_registry = TierRegistry(db, clock=clock)
    hitl_manager = HitlManager(db, clock=clock, default_timeout_seconds=cfg.hitl_timeout_seconds)
    router = MasterRouter(tier_registry, port, clock=clock)
    started_ms = clock.monotonic_ms()

    try:
        async with create_checkpointer(
            cfg.db_path,
            busy_timeout_ms=cfg.sqlite_busy_timeout_ms,
        ) as checkpointer:
            runner = BookingAgentRunner(
                booking_service=booking_service,
                router=router,
                hitl_manager=hitl_manager,
                otp_timeout_seconds=cfg.otp_timeout_seconds,
                clock=clock,
                checkpointer=checkpointer,
            )
            res = await runner.run_booking(request)
    finally:
        await db.close()

    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = export_events_jsonl(
        res.telemetry_events, output_dir / f"{res.booking.trace_id}.jsonl"
    )
    csv_path = export_events_csv(res.telemetry_events, output_dir / f"{res.booking.trace_id}.csv")
    summary = summarize_telemetry(res.telemetry_events)
    return {
        "booking_id": res.booking.booking_id,
        "trace_id": res.booking.trace_id,
        "status": str(res.booking.status),
        "tier_used": res.tier_used,
        "confirmation_code": res.booking.confirmation_code,
        "interrupted": res.interrupted,
        "wall_ms": round(clock.monotonic_ms() - started_ms, 3),
        "p50_ms": summary.p50_ms,
        "p95_ms": summary.p95_ms,
        "total_tokens": summary.total_tokens,
        "jsonl": str(jsonl_path),
        "csv": str(csv_path),
    }


def cli(argv: list[str] | None = None) -> int:
    """`python -m booking_agent.main <input.json> [out_dir] [--dry-run]`."""
    import argparse

    parser = argparse.ArgumentParser(prog="booking_agent.main", description=cli.__doc__)
    parser.add_argument("input_json", type=Path)
    parser.add_argument("output_dir", type=Path, nargs="?", default=Path("artifacts/cli_runs"))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dùng DryRunBrowserControl (không mở trình duyệt) để chạy trọn luồng",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Đường dẫn file SQLite tùy chọn (mặc định dùng Settings.db_path)",
    )
    args = parser.parse_args(argv)
    cfg = get_settings().model_copy(update={"db_path": args.db_path}) if args.db_path else None
    result = asyncio.run(
        run_json_booking(
            args.input_json,
            output_dir=args.output_dir,
            settings=cfg,
            dry_run=args.dry_run,
        )
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
