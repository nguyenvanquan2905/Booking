"""Booking domain models and status definitions (MVP-39)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class BookingStatus(StrEnum):
    PENDING = "pending"
    VALIDATED = "validated"
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_HITL = "awaiting_hitl"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class BookingCreateRequest(BaseModel):
    site_id: str = Field(min_length=1, max_length=100)
    restaurant_name: str = Field(min_length=1, max_length=200)
    customer_name: str = Field(min_length=1, max_length=120)
    customer_phone: str = Field(min_length=5, max_length=32)
    customer_email: str | None = Field(default=None, max_length=200)
    party_size: int = Field(ge=1, le=100)
    booking_time: datetime
    allow_deposit_max: int = Field(default=0, ge=0)
    channel: str = Field(default="web", max_length=32)
    notes: str = Field(default="", max_length=1000)
    idempotency_key: str | None = Field(default=None, max_length=128)


class CustomerRecord(BaseModel):
    customer_id: str
    masked_phone: str
    masked_name: str
    masked_email: str | None = None
    phone: str | None = None
    name: str | None = None
    email: str | None = None
    created_at: datetime
    expires_at: datetime
    deleted_at: datetime | None = None


class BookingRecord(BaseModel):
    booking_id: str
    customer_id: str
    idempotency_key: str | None = None
    site_id: str
    restaurant_name: str
    party_size: int
    booking_time: datetime
    allow_deposit_max: int = 0
    notes: str = ""
    status: BookingStatus
    confirmation_code: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    trace_id: str
    created_at: datetime
    updated_at: datetime


class BookingEventRecord(BaseModel):
    event_id: str
    booking_id: str
    from_status: BookingStatus | None = None
    to_status: BookingStatus
    reason: str = ""
    actor: str = "system"
    trace_id: str
    created_at: datetime
