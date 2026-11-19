"""Monotonic and UTC clock abstractions (MVP-01)."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Clock interface supporting deterministic testing."""

    def monotonic_ns(self) -> int: ...

    def monotonic_ms(self) -> float: ...

    def monotonic_s(self) -> float: ...

    def utc_now(self) -> datetime: ...

    def utc_now_iso(self) -> str: ...


class SystemClock:
    """Production system clock using time.monotonic and UTC wall clock."""

    def monotonic_ns(self) -> int:
        return time.monotonic_ns()

    def monotonic_ms(self) -> float:
        return time.monotonic_ns() / 1_000_000.0

    def monotonic_s(self) -> float:
        return time.monotonic()

    def utc_now(self) -> datetime:
        return datetime.now(UTC)

    def utc_now_iso(self) -> str:
        return self.utc_now().isoformat()


class FakeClock:
    """Deterministic clock for unit and integration tests."""

    def __init__(self, initial_utc: datetime | None = None, monotonic_ns: int = 0) -> None:
        if initial_utc is None:
            initial_utc = datetime(2026, 11, 18, 12, 0, 0, tzinfo=UTC)
        elif initial_utc.tzinfo is None:
            initial_utc = initial_utc.replace(tzinfo=UTC)
        self._utc = initial_utc
        self._monotonic_ns = monotonic_ns

    def advance(self, seconds: float) -> None:
        delta_ns = int(seconds * 1_000_000_000)
        self._monotonic_ns += delta_ns
        self._utc += timedelta(seconds=seconds)

    def monotonic_ns(self) -> int:
        return self._monotonic_ns

    def monotonic_ms(self) -> float:
        return self._monotonic_ns / 1_000_000.0

    def monotonic_s(self) -> float:
        return self._monotonic_ns / 1_000_000_000.0

    def utc_now(self) -> datetime:
        return self._utc

    def utc_now_iso(self) -> str:
        return self._utc.isoformat()
