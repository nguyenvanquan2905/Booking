"""Unified error taxonomy for Booking Agent (MVP-01)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from booking_agent.shared.trace import get_trace_id


class ErrorCategory(StrEnum):
    VALIDATION = "validation"
    POLICY = "policy"
    AUTHENTICATION = "authentication"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    STATE_TRANSITION = "state_transition"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    INFRASTRUCTURE = "infrastructure"
    BROWSER = "browser"
    SANDBOX = "sandbox"
    HITL_REQUIRED = "hitl_required"
    INTERNAL = "internal"


class ErrorCode(StrEnum):
    # Canonical 6 public API taxonomy codes (System Design v2.1 §7.3, MVP-110, MVP-123)
    INPUT_INVALID = "INPUT_INVALID"
    TIER_EXHAUSTED = "TIER_EXHAUSTED"
    HITL_REQUIRED = "HITL_REQUIRED"
    SANDBOX_UNAVAILABLE = "SANDBOX_UNAVAILABLE"
    PROFILE_LOCKED = "PROFILE_LOCKED"
    SITE_BLOCKED = "SITE_BLOCKED"

    # Granular domain error codes
    INVALID_INPUT = "INVALID_INPUT"
    INVALID_PHONE = "INVALID_PHONE"
    INVALID_BOOKING_TIME = "INVALID_BOOKING_TIME"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    UNSUPPORTED_CHANNEL = "UNSUPPORTED_CHANNEL"
    PROMPT_INJECTION_DETECTED = "PROMPT_INJECTION_DETECTED"
    BOOKING_NOT_FOUND = "BOOKING_NOT_FOUND"
    CUSTOMER_NOT_FOUND = "CUSTOMER_NOT_FOUND"
    HITL_NOT_FOUND = "HITL_NOT_FOUND"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    HITL_REJECTED = "HITL_REJECTED"
    HITL_EXPIRED = "HITL_EXPIRED"
    OTP_REQUIRED = "OTP_REQUIRED"
    OTP_INVALID = "OTP_INVALID"
    OTP_TIMEOUT = "OTP_TIMEOUT"
    LOOP_DETECTED = "LOOP_DETECTED"
    DEPOSIT_EXCEEDS_LIMIT = "DEPOSIT_EXCEEDS_LIMIT"
    PROFILE_DEGRADED = "PROFILE_DEGRADED"
    QUEUE_EMPTY = "QUEUE_EMPTY"
    TIER_UNAVAILABLE = "TIER_UNAVAILABLE"
    SANDBOX_ERROR = "SANDBOX_ERROR"
    DB_ERROR = "DB_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


TAXONOMY_MESSAGES_VI: dict[str, str] = {
    "INPUT_INVALID": (
        "Thông tin đặt bàn không hợp lệ. Vui lòng kiểm tra lại SĐT, ngày giờ và số người."
    ),
    "TIER_EXHAUSTED": "Không thể tự động đặt bàn trên trang này sau khi đã thử các phương thức.",
    "HITL_REQUIRED": "Cần khách hàng xác nhận mã OTP hoặc điều kiện đặt cọc để tiếp tục.",
    "SANDBOX_UNAVAILABLE": "Hệ thống phiên trình duyệt đang đầy, vui lòng thử lại sau ít phút.",
    "PROFILE_LOCKED": "Phiên tài khoản đặt bàn đang bận xử lý yêu cầu khác.",
    "SITE_BLOCKED": "Trang web nhà hàng hiện bị chặn hoặc không thuộc danh sách hỗ trợ.",
}


class BookingAgentError(Exception):
    """Base structured error with taxonomy category, error code, and trace_id."""

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        category: ErrorCategory = ErrorCategory.INTERNAL,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.category = category
        self.retryable = retryable
        self.details = details or {}
        self.trace_id = trace_id or get_trace_id()

    @property
    def taxonomy_code(self) -> str:
        """Map granular domain error code to the 6 public API taxonomy codes (§7.3)."""
        if self.code in (
            ErrorCode.INPUT_INVALID,
            ErrorCode.INVALID_INPUT,
            ErrorCode.INVALID_PHONE,
            ErrorCode.INVALID_BOOKING_TIME,
            ErrorCode.OTP_INVALID,
        ):
            return str(ErrorCode.INPUT_INVALID)
        if self.code in (
            ErrorCode.HITL_REQUIRED,
            ErrorCode.OTP_REQUIRED,
            ErrorCode.DEPOSIT_EXCEEDS_LIMIT,
        ):
            return str(ErrorCode.HITL_REQUIRED)
        if self.code in (ErrorCode.SANDBOX_UNAVAILABLE, ErrorCode.SANDBOX_ERROR):
            return str(ErrorCode.SANDBOX_UNAVAILABLE)
        if self.code in (ErrorCode.PROFILE_LOCKED, ErrorCode.PROFILE_DEGRADED):
            return str(ErrorCode.PROFILE_LOCKED)
        if self.code in (
            ErrorCode.SITE_BLOCKED,
            ErrorCode.POLICY_BLOCKED,
            ErrorCode.UNSUPPORTED_CHANNEL,
            ErrorCode.PROMPT_INJECTION_DETECTED,
        ):
            return str(ErrorCode.SITE_BLOCKED)
        return str(ErrorCode.TIER_EXHAUSTED)

    @property
    def message_vi(self) -> str:
        return TAXONOMY_MESSAGES_VI.get(
            self.taxonomy_code,
            TAXONOMY_MESSAGES_VI["TIER_EXHAUSTED"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": str(self.code),
            "taxonomy_code": self.taxonomy_code,
            "category": str(self.category),
            "message": self.message,
            "message_vi": self.message_vi,
            "retryable": self.retryable,
            "details": self.details,
            "trace_id": self.trace_id,
        }


class ValidationError(BookingAgentError):
    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.INVALID_INPUT,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            category=ErrorCategory.VALIDATION,
            retryable=False,
            details=details,
        )


class PolicyViolationError(BookingAgentError):
    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.POLICY_BLOCKED,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            category=ErrorCategory.POLICY,
            retryable=False,
            details=details,
        )


class NotFoundError(BookingAgentError):
    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.BOOKING_NOT_FOUND,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            category=ErrorCategory.NOT_FOUND,
            retryable=False,
            details=details,
        )


class ConflictError(BookingAgentError):
    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.IDEMPOTENCY_CONFLICT,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            category=ErrorCategory.CONFLICT,
            retryable=False,
            details=details,
        )


class IdempotencyConflictError(ConflictError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code=ErrorCode.IDEMPOTENCY_CONFLICT, details=details)


class InvalidStateTransitionError(BookingAgentError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code=ErrorCode.INVALID_STATE_TRANSITION,
            category=ErrorCategory.STATE_TRANSITION,
            retryable=False,
            details=details,
        )


class HitlRequiredError(BookingAgentError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code=ErrorCode.HITL_REQUIRED,
            category=ErrorCategory.HITL_REQUIRED,
            retryable=False,
            details=details,
        )


class RetryableInfraError(BookingAgentError):
    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.SANDBOX_ERROR,
        category: ErrorCategory = ErrorCategory.INFRASTRUCTURE,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            category=category,
            retryable=True,
            details=details,
        )


class TierExecutionError(BookingAgentError):
    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.TIER_EXHAUSTED,
        retryable: bool = True,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            category=ErrorCategory.BROWSER,
            retryable=retryable,
            details=details,
        )
