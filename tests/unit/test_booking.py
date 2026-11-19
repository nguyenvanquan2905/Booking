"""Unit tests for booking domain: state machine, idempotency, PII TTL purge (MVP-39, MVP-83)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from booking_agent.booking.models import BookingCreateRequest, BookingStatus
from booking_agent.booking.service import BookingService
from booking_agent.booking.state_machine import can_transition
from booking_agent.shared.clock import FakeClock
from booking_agent.shared.errors import IdempotencyConflictError, InvalidStateTransitionError


async def test_booking_lifecycle_and_events(
    booking_service: BookingService,
    fake_clock: FakeClock,
) -> None:
    req = BookingCreateRequest(
        site_id="pasgo",
        restaurant_name="Lau Nam Ashima",
        customer_name="Nguyen Van A",
        customer_phone="0901234567",
        customer_email="a@example.com",
        party_size=4,
        booking_time=fake_clock.utc_now() + timedelta(hours=4),
        notes="Ban yen tinh",
        idempotency_key="idem-001",
    )

    booking, is_replay = await booking_service.create_booking(req, trace_id="tr_bk_1")
    assert not is_replay
    assert booking.status == BookingStatus.PENDING

    replay_booking, is_replay_2 = await booking_service.create_booking(req, trace_id="tr_bk_2")
    assert is_replay_2
    assert replay_booking.booking_id == booking.booking_id

    # Idempotency conflict with different payload
    bad_req = req.model_copy(update={"party_size": 8})
    with pytest.raises(IdempotencyConflictError):
        await booking_service.create_booking(bad_req)

    # Valid transitions
    await booking_service.transition_status(booking.booking_id, BookingStatus.VALIDATED)
    await booking_service.transition_status(booking.booking_id, BookingStatus.RUNNING)
    confirmed = await booking_service.transition_status(
        booking.booking_id,
        BookingStatus.CONFIRMED,
        confirmation_code="PSG-9988",
    )
    assert confirmed.status == BookingStatus.CONFIRMED
    assert confirmed.confirmation_code == "PSG-9988"

    # Terminal state cannot transition further
    assert not can_transition(BookingStatus.CONFIRMED, BookingStatus.CANCELLED)
    with pytest.raises(InvalidStateTransitionError):
        await booking_service.cancel_booking(booking.booking_id)

    events = await booking_service.list_events(booking.booking_id)
    assert [e.to_status for e in events] == [
        BookingStatus.PENDING,
        BookingStatus.VALIDATED,
        BookingStatus.RUNNING,
        BookingStatus.CONFIRMED,
    ]


async def test_customer_pii_encryption_and_ttl_purge(
    booking_service: BookingService,
    fake_clock: FakeClock,
) -> None:
    req = BookingCreateRequest(
        site_id="pasgo",
        restaurant_name="Pho Cuon",
        customer_name="Tran Thi B",
        customer_phone="+84912345678",
        customer_email="b@example.com",
        party_size=2,
        booking_time=fake_clock.utc_now() + timedelta(days=1),
    )
    booking, _ = await booking_service.create_booking(req)

    masked = await booking_service.customers.get_customer(booking.customer_id)
    assert masked is not None
    assert masked.phone is None
    assert "12345" not in masked.masked_phone

    decrypted = await booking_service.customers.get_customer(
        booking.customer_id,
        include_decrypted=True,
    )
    assert decrypted is not None
    assert decrypted.phone == "+84912345678"
    assert decrypted.name == "Tran Thi B"

    # Before TTL expires: nothing purged
    assert await booking_service.customers.purge_expired() == 0

    # Advance past 30-day default TTL
    fake_clock.advance(31 * 86400)
    purged_count = await booking_service.customers.purge_expired()
    assert purged_count == 1

    after_purge = await booking_service.customers.get_customer(
        booking.customer_id,
        include_decrypted=True,
    )
    assert after_purge is not None
    assert after_purge.deleted_at is not None
    assert after_purge.phone is None
    assert after_purge.masked_phone == "***"

    # Booking row remains intact (FK preserved)
    still_there = await booking_service.get_booking(booking.booking_id)
    assert still_there.booking_id == booking.booking_id


async def test_natural_composite_idempotency_and_idempotent_cancel(
    booking_service: BookingService,
    fake_clock: FakeClock,
) -> None:
    target_time = fake_clock.utc_now() + timedelta(hours=5)
    req = BookingCreateRequest(
        site_id="pasgo",
        restaurant_name="Lau Nam",
        customer_name="Nguyen Van X",
        customer_phone="0905556666",
        party_size=4,
        booking_time=target_time,
    )
    first, replay1 = await booking_service.create_booking(req)
    assert not replay1

    # Second booking without Idempotency-Key for same (site, time, phone) replays existing
    second, replay2 = await booking_service.create_booking(req)
    assert replay2
    assert second.booking_id == first.booking_id

    released: list[str] = []

    async def on_cancel(bid: str) -> None:
        released.append(bid)

    c1 = await booking_service.cancel_booking(first.booking_id, on_cancel=on_cancel)
    c2 = await booking_service.cancel_booking(first.booking_id, on_cancel=on_cancel)
    assert c1.status == BookingStatus.CANCELLED
    assert c2.status == BookingStatus.CANCELLED
    assert released == [first.booking_id]

    # After cancellation, same customer may create a fresh booking at that slot
    third, replay3 = await booking_service.create_booking(req)
    assert not replay3
    assert third.booking_id != first.booking_id
