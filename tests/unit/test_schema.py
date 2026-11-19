"""Unit tests for SQLite DDL schema, PRAGMAs, indexes, and VACUUM INTO backup (MVP-80)."""

from __future__ import annotations

from pathlib import Path

from booking_agent.shared.db import DatabasePool


async def test_sqlite_schema_indexes_and_atomic_backup(
    tmp_db: DatabasePool,
    tmp_path: Path,
) -> None:
    assert await tmp_db.check_integrity() is True

    async with tmp_db.connection() as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name;"
        )
        indexes = {r["name"] for r in await cursor.fetchall()}

    assert "idx_booking_requests_trace_id" in indexes
    assert "idx_booking_requests_site_id" in indexes
    assert "idx_telemetry_events_trace_id" in indexes
    assert "idx_agent_tasks_claim" in indexes

    backup_file = await tmp_db.backup_to(tmp_path / "backup" / "snapshot.db")
    assert backup_file.is_file()
    backup_pool = DatabasePool(backup_file)
    try:
        assert await backup_pool.check_integrity() is True
    finally:
        await backup_pool.close()
