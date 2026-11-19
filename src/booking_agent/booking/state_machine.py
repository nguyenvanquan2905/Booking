"""Booking lifecycle state machine and transition validation (MVP-39)."""

from __future__ import annotations

from booking_agent.booking.models import BookingStatus
from booking_agent.shared.errors import InvalidStateTransitionError

TERMINAL_STATUSES: frozenset[BookingStatus] = frozenset(
    {
        BookingStatus.CONFIRMED,
        BookingStatus.FAILED,
        BookingStatus.CANCELLED,
        BookingStatus.EXPIRED,
    }
)

ALLOWED_TRANSITIONS: dict[BookingStatus, frozenset[BookingStatus]] = {
    BookingStatus.PENDING: frozenset(
        {
            BookingStatus.VALIDATED,
            BookingStatus.QUEUED,
            BookingStatus.FAILED,
            BookingStatus.CANCELLED,
        }
    ),
    BookingStatus.VALIDATED: frozenset(
        {
            BookingStatus.QUEUED,
            BookingStatus.AWAITING_HITL,
            BookingStatus.RUNNING,
            BookingStatus.FAILED,
            BookingStatus.CANCELLED,
        }
    ),
    BookingStatus.QUEUED: frozenset(
        {
            BookingStatus.VALIDATED,
            BookingStatus.RUNNING,
            BookingStatus.AWAITING_HITL,
            BookingStatus.FAILED,
            BookingStatus.CANCELLED,
            BookingStatus.EXPIRED,
        }
    ),
    BookingStatus.RUNNING: frozenset(
        {
            BookingStatus.VALIDATED,
            BookingStatus.AWAITING_HITL,
            BookingStatus.CONFIRMED,
            BookingStatus.QUEUED,
            BookingStatus.FAILED,
            BookingStatus.CANCELLED,
            BookingStatus.EXPIRED,
        }
    ),
    BookingStatus.AWAITING_HITL: frozenset(
        {
            BookingStatus.RUNNING,
            BookingStatus.QUEUED,
            BookingStatus.CONFIRMED,
            BookingStatus.FAILED,
            BookingStatus.CANCELLED,
            BookingStatus.EXPIRED,
        }
    ),
    BookingStatus.CONFIRMED: frozenset(),
    BookingStatus.FAILED: frozenset(),
    BookingStatus.CANCELLED: frozenset(),
    BookingStatus.EXPIRED: frozenset(),
}


def can_transition(current: BookingStatus, target: BookingStatus) -> bool:
    """Return True if transitioning from current to target status is permitted."""
    if current == target:
        return True
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def validate_transition(current: BookingStatus, target: BookingStatus) -> None:
    """Validate state transition or raise InvalidStateTransitionError."""
    if not can_transition(current, target):
        raise InvalidStateTransitionError(
            f"Cannot transition booking status from '{current}' to '{target}'",
            details={"from_status": str(current), "to_status": str(target)},
        )
