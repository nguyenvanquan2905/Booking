"""Shared kernel package (MVP-01, MVP-83, MVP-90 — owner: C)."""

from booking_agent.shared.clock import Clock, FakeClock, SystemClock
from booking_agent.shared.config import Settings, get_settings
from booking_agent.shared.db import DatabasePool
from booking_agent.shared.errors import (
    TAXONOMY_MESSAGES_VI,
    BookingAgentError,
    ConflictError,
    ErrorCategory,
    ErrorCode,
    HitlRequiredError,
    IdempotencyConflictError,
    InvalidStateTransitionError,
    NotFoundError,
    PolicyViolationError,
    RetryableInfraError,
    TierExecutionError,
    ValidationError,
)
from booking_agent.shared.logging import configure_logging, get_logger
from booking_agent.shared.pii import (
    PiiCipher,
    mask_email,
    mask_name,
    mask_phone,
    redact_pii_in_dict,
    redact_pii_in_text,
)
from booking_agent.shared.trace import (
    filter_logs_by_trace_id,
    generate_span_id,
    generate_trace_id,
    get_booking_id,
    get_span_id,
    get_trace_id,
    trace_context,
)

__all__ = [
    "BookingAgentError",
    "Clock",
    "ConflictError",
    "DatabasePool",
    "ErrorCategory",
    "ErrorCode",
    "FakeClock",
    "HitlRequiredError",
    "IdempotencyConflictError",
    "InvalidStateTransitionError",
    "NotFoundError",
    "PiiCipher",
    "PolicyViolationError",
    "RetryableInfraError",
    "Settings",
    "SystemClock",
    "TAXONOMY_MESSAGES_VI",
    "TierExecutionError",
    "ValidationError",
    "configure_logging",
    "filter_logs_by_trace_id",
    "generate_span_id",
    "generate_trace_id",
    "get_booking_id",
    "get_logger",
    "get_settings",
    "get_span_id",
    "get_trace_id",
    "mask_email",
    "mask_name",
    "mask_phone",
    "redact_pii_in_dict",
    "redact_pii_in_text",
    "trace_context",
]
