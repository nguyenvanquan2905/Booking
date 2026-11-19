"""Layer 1 input normalization & validation with phonenumbers (MVP-11 — owner: C)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat
from pydantic import BaseModel

from booking_agent.booking.models import BookingCreateRequest
from booking_agent.shared.clock import Clock, SystemClock
from booking_agent.shared.errors import ErrorCode, ValidationError

_WHITESPACE_RE = re.compile(r"\s+")
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class NormalizedBookingInput(BaseModel):
    site_id: str
    restaurant_name: str
    customer_name: str
    customer_phone: str
    customer_email: str | None = None
    party_size: int
    booking_date: str
    booking_time: datetime
    allow_deposit_max: int = 0
    channel: str = "web"
    notes: str = ""


def _collapse_ws(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()


@lru_cache(maxsize=4096)
def normalize_phone_vn(raw_phone: str) -> str:
    """Validate and normalize a Vietnamese (or international) phone number to E.164."""
    cleaned = _collapse_ws(raw_phone)
    if not cleaned:
        raise ValidationError(
            "Phone number must not be empty",
            code=ErrorCode.INVALID_PHONE,
        )
    try:
        parsed = phonenumbers.parse(cleaned, "VN")
    except NumberParseException as exc:
        raise ValidationError(
            f"Invalid phone number format: {exc}",
            code=ErrorCode.INVALID_PHONE,
        ) from exc

    if not phonenumbers.is_valid_number(parsed):
        raise ValidationError(
            "Phone number is not valid for Vietnam or international format",
            code=ErrorCode.INVALID_PHONE,
        )
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)


def normalize_booking_input(
    raw: BookingCreateRequest | dict[str, Any],
    *,
    clock: Clock | None = None,
    max_party_size: int = 50,
    allow_past_booking: bool = False,
) -> NormalizedBookingInput:
    """Normalize and validate incoming booking input before policy & routing."""
    if isinstance(raw, dict):
        party_val = raw.get("party_size")
        if isinstance(party_val, bool) or not isinstance(party_val, int):
            raise ValidationError(
                "party_size must be a strict positive integer",
                details={"party_size": repr(party_val)},
            )
        dep_val = raw.get("allow_deposit_max", 0)
        if isinstance(dep_val, bool) or not isinstance(dep_val, int) or dep_val < 0:
            raise ValidationError(
                "allow_deposit_max must be a non-negative integer",
                details={"allow_deposit_max": repr(dep_val)},
            )

    try:
        req = (
            raw
            if isinstance(raw, BookingCreateRequest)
            else BookingCreateRequest.model_validate(raw)
        )
    except Exception as exc:
        raise ValidationError(f"Invalid booking input: {exc}") from exc

    active_clock = clock or SystemClock()

    site_id = _collapse_ws(req.site_id).lower()
    restaurant_name = _collapse_ws(req.restaurant_name)
    customer_name = _collapse_ws(req.customer_name)
    notes = _collapse_ws(req.notes)
    channel = _collapse_ws(req.channel).lower() or "web"

    if not site_id or not restaurant_name or not customer_name:
        raise ValidationError("site_id, restaurant_name, and customer_name must not be blank")

    if req.party_size < 1 or req.party_size > max_party_size:
        raise ValidationError(
            f"party_size must be between 1 and {max_party_size}",
            details={"party_size": req.party_size},
        )

    normalized_phone = normalize_phone_vn(req.customer_phone)

    normalized_email: str | None = None
    if req.customer_email:
        candidate_email = _collapse_ws(req.customer_email).lower()
        if not _EMAIL_RE.match(candidate_email):
            raise ValidationError("Invalid customer_email format")
        normalized_email = candidate_email

    booking_time = req.booking_time
    if booking_time.tzinfo is None:
        booking_time = booking_time.replace(tzinfo=UTC)
    else:
        booking_time = booking_time.astimezone(UTC)

    if not allow_past_booking and booking_time <= active_clock.utc_now():
        raise ValidationError(
            "booking_time must be in the future",
            code=ErrorCode.INVALID_BOOKING_TIME,
            details={"booking_time": booking_time.isoformat()},
        )

    return NormalizedBookingInput(
        site_id=site_id,
        restaurant_name=restaurant_name,
        customer_name=customer_name,
        customer_phone=normalized_phone,
        customer_email=normalized_email,
        party_size=req.party_size,
        booking_date=booking_time.strftime("%Y-%m-%d"),
        booking_time=booking_time,
        allow_deposit_max=req.allow_deposit_max,
        channel=channel,
        notes=notes,
    )
