"""SQLite repository for booking_requests and booking_events (MVP-39)."""

from __future__ import annotations

import uuid
from contextlib import nullcontext
from datetime import datetime
from typing import TYPE_CHECKING

from booking_agent.booking.models import BookingEventRecord, BookingRecord, BookingStatus
from booking_agent.shared.clock import Clock, SystemClock
from booking_agent.shared.db import DatabasePool

if TYPE_CHECKING:
    import aiosqlite


class BookingRepository:
    """Data access layer strictly scoped to booking_requests and booking_events."""

    def __init__(self, db: DatabasePool, *, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    @staticmethod
    def _row_to_booking(row: object) -> BookingRecord:
        return BookingRecord(
            booking_id=row["booking_id"],  # type: ignore[index]
            customer_id=row["customer_id"],  # type: ignore[index]
            idempotency_key=row["idempotency_key"],  # type: ignore[index]
            site_id=row["site_id"],  # type: ignore[index]
            restaurant_name=row["restaurant_name"],  # type: ignore[index]
            party_size=int(row["party_size"]),  # type: ignore[index]
            booking_time=datetime.fromisoformat(row["booking_time"]),  # type: ignore[index]
            allow_deposit_max=int(row["allow_deposit_max"]),  # type: ignore[index]
            notes=row["notes"],  # type: ignore[index]
            status=BookingStatus(row["status"]),  # type: ignore[index]
            confirmation_code=row["confirmation_code"],  # type: ignore[index]
            error_code=row["error_code"],  # type: ignore[index]
            error_message=row["error_message"],  # type: ignore[index]
            trace_id=row["trace_id"],  # type: ignore[index]
            created_at=datetime.fromisoformat(row["created_at"]),  # type: ignore[index]
            updated_at=datetime.fromisoformat(row["updated_at"]),  # type: ignore[index]
        )

    @staticmethod
    def _row_to_event(row: object) -> BookingEventRecord:
        from_raw = row["from_status"]  # type: ignore[index]
        return BookingEventRecord(
            event_id=row["event_id"],  # type: ignore[index]
            booking_id=row["booking_id"],  # type: ignore[index]
            from_status=BookingStatus(from_raw) if from_raw else None,
            to_status=BookingStatus(row["to_status"]),  # type: ignore[index]
            reason=row["reason"],  # type: ignore[index]
            actor=row["actor"],  # type: ignore[index]
            trace_id=row["trace_id"],  # type: ignore[index]
            created_at=datetime.fromisoformat(row["created_at"]),  # type: ignore[index]
        )

    async def insert_booking(
        self,
        *,
        booking_id: str,
        customer_id: str,
        idempotency_key: str | None,
        site_id: str,
        restaurant_name: str,
        party_size: int,
        booking_time: datetime,
        allow_deposit_max: int = 0,
        notes: str,
        status: BookingStatus,
        trace_id: str,
        conn: aiosqlite.Connection | None = None,
    ) -> BookingRecord:
        now_iso = self._clock.utc_now_iso()
        event_id = f"bevt_{uuid.uuid4().hex[:20]}"
        tx_ctx = nullcontext(conn) if conn is not None else self._db.transaction()
        async with tx_ctx as active_conn:
            await active_conn.execute(
                """
                INSERT INTO booking_requests (
                    booking_id, customer_id, idempotency_key, site_id,
                    restaurant_name, party_size, booking_time, allow_deposit_max, notes,
                    status, confirmation_code, error_code, error_message,
                    trace_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?)
                """,
                (
                    booking_id,
                    customer_id,
                    idempotency_key,
                    site_id,
                    restaurant_name,
                    party_size,
                    booking_time.isoformat(),
                    allow_deposit_max,
                    notes,
                    str(status),
                    trace_id,
                    now_iso,
                    now_iso,
                ),
            )
            await active_conn.execute(
                """
                INSERT INTO booking_events (
                    event_id, booking_id, from_status, to_status,
                    reason, actor, trace_id, created_at
                ) VALUES (?, ?, NULL, ?, 'created', 'api', ?, ?)
                """,
                (event_id, booking_id, str(status), trace_id, now_iso),
            )
            cursor = await active_conn.execute(
                "SELECT * FROM booking_requests WHERE booking_id = ?",
                (booking_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_booking(row)

    async def get_booking(
        self,
        booking_id: str,
        *,
        conn: aiosqlite.Connection | None = None,
    ) -> BookingRecord | None:
        conn_ctx = nullcontext(conn) if conn is not None else self._db.connection()
        async with conn_ctx as active_conn:
            cursor = await active_conn.execute(
                "SELECT * FROM booking_requests WHERE booking_id = ?",
                (booking_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_booking(row) if row is not None else None

    async def find_active_duplicate(
        self,
        *,
        site_id: str,
        booking_time: datetime,
        customer_id: str,
        conn: aiosqlite.Connection | None = None,
    ) -> BookingRecord | None:
        """Look up an active non-terminal duplicate booking by (site_id, booking_time, customer)."""
        conn_ctx = nullcontext(conn) if conn is not None else self._db.connection()
        async with conn_ctx as active_conn:
            cursor = await active_conn.execute(
                """
                SELECT * FROM booking_requests
                WHERE site_id = ?
                  AND booking_time = ?
                  AND customer_id = ?
                  AND status NOT IN ('cancelled', 'failed', 'expired')
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (site_id.strip().lower(), booking_time.isoformat(), customer_id),
            )
            row = await cursor.fetchone()
        return self._row_to_booking(row) if row is not None else None

    async def list_bookings(
        self,
        *,
        status: BookingStatus | None = None,
        limit: int = 50,
    ) -> list[BookingRecord]:
        async with self._db.connection() as conn:
            if status is not None:
                cursor = await conn.execute(
                    """
                    SELECT * FROM booking_requests
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (str(status), limit),
                )
            else:
                cursor = await conn.execute(
                    """
                    SELECT * FROM booking_requests
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            rows = await cursor.fetchall()
        return [self._row_to_booking(r) for r in rows]

    async def update_status(
        self,
        *,
        booking_id: str,
        from_status: BookingStatus,
        to_status: BookingStatus,
        reason: str = "",
        actor: str = "system",
        trace_id: str,
        confirmation_code: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> BookingRecord | None:
        now_iso = self._clock.utc_now_iso()
        event_id = f"bevt_{uuid.uuid4().hex[:20]}"
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                """
                UPDATE booking_requests
                SET status = ?,
                    confirmation_code = COALESCE(?, confirmation_code),
                    error_code = COALESCE(?, error_code),
                    error_message = COALESCE(?, error_message),
                    updated_at = ?
                WHERE booking_id = ? AND status = ?
                """,
                (
                    str(to_status),
                    confirmation_code,
                    error_code,
                    error_message,
                    now_iso,
                    booking_id,
                    str(from_status),
                ),
            )
            if cursor.rowcount == 0:
                return None

            await conn.execute(
                """
                INSERT INTO booking_events (
                    event_id, booking_id, from_status, to_status,
                    reason, actor, trace_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    booking_id,
                    str(from_status),
                    str(to_status),
                    reason,
                    actor,
                    trace_id,
                    now_iso,
                ),
            )
            cursor = await conn.execute(
                "SELECT * FROM booking_requests WHERE booking_id = ?",
                (booking_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_booking(row) if row is not None else None

    async def list_events(self, booking_id: str) -> list[BookingEventRecord]:
        async with self._db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM booking_events
                WHERE booking_id = ?
                ORDER BY created_at ASC
                """,
                (booking_id,),
            )
            rows = await cursor.fetchall()
        return [self._row_to_event(r) for r in rows]
