"""Unit tests for shared kernel (MVP-01, MVP-83, MVP-90)."""

from __future__ import annotations

import json
from pathlib import Path

from booking_agent.shared.clock import FakeClock
from booking_agent.shared.config import Settings
from booking_agent.shared.db import DatabasePool
from booking_agent.shared.errors import ErrorCategory, ErrorCode, ValidationError
from booking_agent.shared.logging import configure_logging, get_logger
from booking_agent.shared.pii import (
    PiiCipher,
    mask_email,
    mask_name,
    mask_phone,
    redact_pii_in_dict,
    redact_pii_in_text,
)
from booking_agent.shared.trace import get_booking_id, get_trace_id, trace_context


def test_settings_defaults() -> None:
    cfg = Settings(_env_file=None)
    assert cfg.app_name == "vb-browser-use"
    assert cfg.pii_ttl_days >= 1
    assert cfg.sqlite_busy_timeout_ms >= 100


def test_fake_clock_advances_deterministically() -> None:
    clock = FakeClock()
    t0 = clock.monotonic_ms()
    u0 = clock.utc_now()
    clock.advance(12.5)
    assert clock.monotonic_ms() - t0 == 12500.0
    assert (clock.utc_now() - u0).total_seconds() == 12.5


def test_trace_context_and_errors() -> None:
    assert get_trace_id() is None
    with trace_context("tr_test123", booking_id="bk_999") as active:
        assert active == "tr_test123"
        assert get_trace_id() == "tr_test123"
        assert get_booking_id() == "bk_999"
        err = ValidationError("bad phone", code=ErrorCode.INVALID_PHONE)
        payload = err.to_dict()
        assert payload["trace_id"] == "tr_test123"
        assert payload["category"] == ErrorCategory.VALIDATION
        assert payload["code"] == ErrorCode.INVALID_PHONE
        assert payload["taxonomy_code"] == "INPUT_INVALID"
        assert "SĐT" in payload["message_vi"]
    assert get_trace_id() is None


def test_pii_masking_and_aes_gcm_roundtrip() -> None:
    assert mask_phone("0901234567") == "090***4567"
    assert mask_email("nguyenvana@gmail.com") == "n***@gmail.com"
    assert mask_name("Nguyen Van An") == "N*** V*** A***"

    text = "Call 0901234567 or mail user@example.com with Bearer secret_tok_123"
    redacted = redact_pii_in_text(text)
    assert "0901234567" not in redacted
    assert "user@example.com" not in redacted
    assert "secret_tok_123" not in redacted

    nested = redact_pii_in_dict(
        {
            "customer_phone": "+84901234567",
            "customer_email": "alice@test.vn",
            "customer_name": "Tran Thi B",
            "api_key": "super-secret",
            "safe": "pasgo",
        }
    )
    assert nested["customer_phone"] != "+84901234567"
    assert nested["customer_email"] != "alice@test.vn"
    assert nested["api_key"] == "***REDACTED***"
    assert nested["safe"] == "pasgo"

    cipher = PiiCipher("my-secret-passphrase")
    enc = cipher.encrypt("0901234567")
    assert enc.startswith("enc:v1:")
    assert "0901234567" not in enc
    assert cipher.decrypt(enc) == "0901234567"
    assert cipher.hash_value("0901234567") == cipher.hash_value(" 0901234567 ")


def test_jsonl_logging_redacts_pii_and_binds_trace(tmp_path: Path) -> None:
    log_file = tmp_path / "app.jsonl"
    configure_logging(level="INFO", jsonl_path=log_file)
    logger = get_logger("unit_test")

    with trace_context("tr_log_001", booking_id="bk_log_001"):
        logger.info(
            "Booking for 0909888777",
            extra={"customer_email": "khach@example.com", "tier": 1},
        )

    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["trace_id"] == "tr_log_001"
    assert entry["booking_id"] == "bk_log_001"
    assert "0909888777" not in entry["message"]
    assert entry["extra"]["customer_email"] != "khach@example.com"
    assert entry["extra"]["tier"] == 1


async def test_database_pool_wal_and_schema(tmp_db: DatabasePool) -> None:
    async with tmp_db.connection() as conn:
        cursor = await conn.execute("PRAGMA journal_mode;")
        row = await cursor.fetchone()
        assert row is not None
        assert str(row[0]).lower() == "wal"

        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        )
        tables = {r["name"] for r in await cursor.fetchall()}

    expected = {
        "booking_customers",
        "booking_requests",
        "booking_events",
        "booking_idempotency",
        "agent_tasks",
        "agent_checkpoints",
        "agent_hitl_requests",
        "agent_tier_registry",
        "bc_workflows",
        "bc_executions",
        "sandbox_sessions",
        "profile_records",
        "profile_lease",
        "artifact_index",
        "telemetry_events",
        "telemetry_benchmark_runs",
    }
    assert expected.issubset(tables)


def test_schema_sql_applies_to_fresh_sqlite_db(tmp_path: Path) -> None:
    import sqlite3

    from booking_agent.shared.schema import get_schema_sql

    db_file = tmp_path / "schema_applied.db"
    with sqlite3.connect(db_file) as conn:
        conn.executescript(get_schema_sql())
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        }
    assert "booking_requests" in tables
    assert "agent_tasks" in tables
    assert "agent_profile_health" in tables
