"""Booking domain service coordinating PII, idempotency, state machine, and repository (MVP-39)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from booking_agent.booking.idempotency import IdempotencyStore, compute_request_hash
from booking_agent.booking.models import (
    BookingCreateRequest,
    BookingEventRecord,
    BookingRecord,
    BookingStatus,
)
from booking_agent.booking.pii import CustomerRepository
from booking_agent.booking.repository import BookingRepository
from booking_agent.booking.state_machine import validate_transition
from booking_agent.shared.clock import Clock, SystemClock
from booking_agent.shared.db import DatabasePool
from booking_agent.shared.errors import ErrorCode, InvalidStateTransitionError, NotFoundError
from booking_agent.shared.pii import PiiCipher
from booking_agent.shared.trace import generate_trace_id, get_trace_id


class BookingService:
    """Public facade for creating, reading, and transitioning bookings."""

    def __init__(
        self,
        db: DatabasePool,
        *,
        cipher: PiiCipher,
        clock: Clock | None = None,
        pii_ttl_days: int = 30,
        idempotency_ttl_seconds: int = 86400,
    ) -> None:
        self._db = db
        self._clock = clock or SystemClock()
        self.customers = CustomerRepository(
            db,
            cipher,
            clock=self._clock,
            default_ttl_days=pii_ttl_days,
        )
        self.bookings = BookingRepository(db, clock=self._clock)
        self.idempotency = IdempotencyStore(
            db,
            clock=self._clock,
            ttl_seconds=idempotency_ttl_seconds,
        )

    async def create_booking(
        self,
        request: BookingCreateRequest,
        *,
        trace_id: str | None = None,
    ) -> tuple[BookingRecord, bool]:
        """Create a booking or replay atomically within one SQLite transaction."""
        active_trace = trace_id or get_trace_id() or generate_trace_id()
        candidate_booking_id = f"bk_{uuid.uuid4().hex[:20]}"

        async with self._db.transaction() as conn:
            if request.idempotency_key:
                req_hash = compute_request_hash(
                    request.model_dump(exclude={"idempotency_key"}, mode="json")
                )
                existing_entry, is_replay = await self.idempotency.reserve_or_replay(
                    idempotency_key=request.idempotency_key,
                    request_hash=req_hash,
                    booking_id=candidate_booking_id,
                    conn=conn,
                )
                if is_replay and existing_entry is not None:
                    existing_booking = await self.bookings.get_booking(
                        existing_entry.booking_id,
                        conn=conn,
                    )
                    if existing_booking is None:
                        raise NotFoundError(
                            f"Booking '{existing_entry.booking_id}' not found",
                            code=ErrorCode.BOOKING_NOT_FOUND,
                            details={"booking_id": existing_entry.booking_id},
                        )
                    return existing_booking, True

            customer = await self.customers.upsert_customer(
                phone=request.customer_phone,
                name=request.customer_name,
                email=request.customer_email,
                conn=conn,
            )
            natural_dup = await self.bookings.find_active_duplicate(
                site_id=request.site_id,
                booking_time=request.booking_time,
                customer_id=customer.customer_id,
                conn=conn,
            )
            if natural_dup is not None:
                if request.idempotency_key:
                    await self.idempotency.save_response(
                        request.idempotency_key,
                        natural_dup.model_dump_json(),
                        conn=conn,
                    )
                return natural_dup, True

            record = await self.bookings.insert_booking(
                booking_id=candidate_booking_id,
                customer_id=customer.customer_id,
                idempotency_key=request.idempotency_key,
                site_id=request.site_id.strip().lower(),
                restaurant_name=request.restaurant_name,
                party_size=request.party_size,
                booking_time=request.booking_time,
                allow_deposit_max=request.allow_deposit_max,
                notes=request.notes,
                status=BookingStatus.PENDING,
                trace_id=active_trace,
                conn=conn,
            )
            if request.idempotency_key:
                await self.idempotency.save_response(
                    request.idempotency_key,
                    record.model_dump_json(),
                    conn=conn,
                )
        return record, False

    async def get_booking(self, booking_id: str) -> BookingRecord:
        record = await self.bookings.get_booking(booking_id)
        if record is None:
            raise NotFoundError(
                f"Booking '{booking_id}' not found",
                code=ErrorCode.BOOKING_NOT_FOUND,
                details={"booking_id": booking_id},
            )
        return record

    async def list_bookings(
        self,
        *,
        status: BookingStatus | None = None,
        limit: int = 50,
    ) -> list[BookingRecord]:
        return await self.bookings.list_bookings(status=status, limit=limit)

    async def transition_status(
        self,
        booking_id: str,
        target_status: BookingStatus,
        *,
        reason: str = "",
        actor: str = "system",
        trace_id: str | None = None,
        confirmation_code: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> BookingRecord:
        current = await self.get_booking(booking_id)
        if current.status == target_status:
            return current
        validate_transition(current.status, target_status)

        active_trace = trace_id or get_trace_id() or current.trace_id
        updated = await self.bookings.update_status(
            booking_id=booking_id,
            from_status=current.status,
            to_status=target_status,
            reason=reason,
            actor=actor,
            trace_id=active_trace,
            confirmation_code=confirmation_code,
            error_code=error_code,
            error_message=error_message,
        )
        if updated is None:
            raise InvalidStateTransitionError(
                f"Concurrent state change prevented transition to '{target_status}'",
                details={"booking_id": booking_id, "expected_status": str(current.status)},
            )
        return updated

    async def cancel_booking(
        self,
        booking_id: str,
        *,
        reason: str = "user_cancelled",
        actor: str = "user",
        trace_id: str | None = None,
        on_cancel: Callable[[str], Awaitable[None]] | None = None,
    ) -> BookingRecord:
        current = await self.get_booking(booking_id)
        if current.status == BookingStatus.CANCELLED:
            return current
        cancelled = await self.transition_status(
            booking_id,
            BookingStatus.CANCELLED,
            reason=reason,
            actor=actor,
            trace_id=trace_id,
        )
        if on_cancel is not None:
            await on_cancel(booking_id)
        return cancelled

    async def list_events(self, booking_id: str) -> list[BookingEventRecord]:
        await self.get_booking(booking_id)
        return await self.bookings.list_events(booking_id)
