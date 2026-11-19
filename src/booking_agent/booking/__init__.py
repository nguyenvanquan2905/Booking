"""Booking domain package (MVP-39, MVP-83 — owner: C)."""

from booking_agent.booking.models import (
    BookingCreateRequest,
    BookingEventRecord,
    BookingRecord,
    BookingStatus,
    CustomerRecord,
)
from booking_agent.booking.pii import CustomerRepository
from booking_agent.booking.service import BookingService
from booking_agent.booking.state_machine import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    can_transition,
    validate_transition,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "BookingCreateRequest",
    "BookingEventRecord",
    "BookingRecord",
    "BookingService",
    "BookingStatus",
    "CustomerRecord",
    "CustomerRepository",
    "TERMINAL_STATUSES",
    "can_transition",
    "validate_transition",
]
