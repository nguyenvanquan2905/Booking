"""Idempotency-Key store for booking requests (MVP-39)."""

from __future__ import annotations

import hashlib
import json
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from booking_agent.shared.clock import Clock, SystemClock
from booking_agent.shared.db import DatabasePool
from booking_agent.shared.errors import IdempotencyConflictError

if TYPE_CHECKING:
    import aiosqlite


@dataclass(slots=True)
class IdempotencyEntry:
    idempotency_key: str
    request_hash: str
    booking_id: str
    response_json: str | None
    created_at: datetime
    expires_at: datetime


def compute_request_hash(payload: dict[str, Any]) -> str:
    """Compute canonical SHA-256 hash of a booking request payload."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class IdempotencyStore:
    """SQLite-backed store ensuring safe retry of booking creation calls."""

    def __init__(
        self,
        db: DatabasePool,
        *,
        clock: Clock | None = None,
        ttl_seconds: int = 86400,
    ) -> None:
        self._db = db
        self._clock = clock or SystemClock()
        self._ttl_seconds = ttl_seconds

    async def reserve_or_replay(
        self,
        *,
        idempotency_key: str,
        request_hash: str,
        booking_id: str,
        conn: aiosqlite.Connection | None = None,
    ) -> tuple[IdempotencyEntry | None, bool]:
        """Reserve a key or return existing entry on replay; raise on payload mismatch."""
        now = self._clock.utc_now()
        now_iso = now.isoformat()
        expires_iso = (now + timedelta(seconds=self._ttl_seconds)).isoformat()

        tx_ctx = nullcontext(conn) if conn is not None else self._db.transaction()
        async with tx_ctx as active_conn:
            cursor = await active_conn.execute(
                "SELECT * FROM booking_idempotency WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            row = await cursor.fetchone()
            if row is not None and row["expires_at"] > now_iso:
                if row["request_hash"] != request_hash:
                    raise IdempotencyConflictError(
                        "Idempotency-Key reused with a different request payload",
                        details={"idempotency_key": idempotency_key},
                    )
                entry = IdempotencyEntry(
                    idempotency_key=row["idempotency_key"],
                    request_hash=row["request_hash"],
                    booking_id=row["booking_id"],
                    response_json=row["response_json"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    expires_at=datetime.fromisoformat(row["expires_at"]),
                )
                return entry, True

            await active_conn.execute(
                """
                INSERT OR REPLACE INTO booking_idempotency (
                    idempotency_key, request_hash, booking_id,
                    response_json, created_at, expires_at
                ) VALUES (?, ?, ?, NULL, ?, ?)
                """,
                (idempotency_key, request_hash, booking_id, now_iso, expires_iso),
            )
        return None, False

    async def save_response(
        self,
        idempotency_key: str,
        response_json: str,
        *,
        conn: aiosqlite.Connection | None = None,
    ) -> None:
        tx_ctx = nullcontext(conn) if conn is not None else self._db.transaction()
        async with tx_ctx as active_conn:
            await active_conn.execute(
                """
                UPDATE booking_idempotency
                SET response_json = ?
                WHERE idempotency_key = ?
                """,
                (response_json, idempotency_key),
            )

    async def purge_expired(self) -> int:
        now_iso = self._clock.utc_now().isoformat()
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                "DELETE FROM booking_idempotency WHERE expires_at <= ?",
                (now_iso,),
            )
            return cursor.rowcount or 0
