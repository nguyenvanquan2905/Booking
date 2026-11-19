"""Shared pytest fixtures providing isolated SQLite databases per test (KHÓA CHUNG)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from booking_agent.agent.guardrails.layer3_hitl import HitlManager
from booking_agent.agent.queue import DurableQueue
from booking_agent.agent.registry import TierRegistry
from booking_agent.booking.service import BookingService
from booking_agent.shared.clock import FakeClock
from booking_agent.shared.db import DatabasePool
from booking_agent.shared.pii import PiiCipher


@pytest.fixture
def fake_clock() -> FakeClock:
    """Deterministic UTC + monotonic clock starting at 2026-11-18T12:00:00Z."""
    return FakeClock()


@pytest.fixture
def pii_cipher() -> PiiCipher:
    return PiiCipher("test-pii-secret-key-for-unit-tests")


@pytest.fixture
async def tmp_db(tmp_path: Path) -> AsyncIterator[DatabasePool]:
    """Fresh SQLite database initialized with shared/schema.py for each test."""
    db_file = tmp_path / "test_app.db"
    pool = DatabasePool(db_file)
    await pool.init()
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
def booking_service(
    tmp_db: DatabasePool,
    pii_cipher: PiiCipher,
    fake_clock: FakeClock,
) -> BookingService:
    return BookingService(tmp_db, cipher=pii_cipher, clock=fake_clock)


@pytest.fixture
def tier_registry(tmp_db: DatabasePool, fake_clock: FakeClock) -> TierRegistry:
    return TierRegistry(tmp_db, clock=fake_clock)


@pytest.fixture
def hitl_manager(tmp_db: DatabasePool, fake_clock: FakeClock) -> HitlManager:
    return HitlManager(tmp_db, clock=fake_clock)


@pytest.fixture
def durable_queue(tmp_db: DatabasePool, fake_clock: FakeClock) -> DurableQueue:
    return DurableQueue(tmp_db, clock=fake_clock)
