"""Layer 3 HITL & Web OTP hibernation store/manager (MVP-11, MVP-12, MVP-27 — owner: C)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from booking_agent.shared.clock import Clock, SystemClock
from booking_agent.shared.db import DatabasePool
from booking_agent.shared.errors import (
    BookingAgentError,
    ErrorCategory,
    ErrorCode,
    NotFoundError,
    ValidationError,
)
from booking_agent.shared.trace import generate_trace_id, get_trace_id

OTP_MAX_TIMEOUT_SECONDS = 900  # 15-minute ceiling (web OTP only; social wait removed)
_OTP_CODE_RE = re.compile(r"^[A-Za-z0-9]{4,12}$")


class WaitKind(StrEnum):
    APPROVAL = "approval"
    OTP = "otp"


class ActionRiskLevel(StrEnum):
    LOW = "low"
    HIGH = "high"


class ActionType(StrEnum):
    OPEN_PAGE = "open_page"
    SELECT_DATE = "select_date"
    SELECT_TIME = "select_time"
    FILL_NAME = "fill_name"
    FILL_PHONE = "fill_phone"
    CHECK_AVAILABILITY = "check_availability"
    CONFIRM_DEPOSIT = "confirm_deposit"
    ENTER_CARD = "enter_card"
    ENTER_OTP = "enter_otp"
    FINAL_SUBMIT = "final_submit"


_LOW_RISK_ACTIONS = frozenset(
    {
        ActionType.OPEN_PAGE,
        ActionType.SELECT_DATE,
        ActionType.SELECT_TIME,
        ActionType.FILL_NAME,
        ActionType.FILL_PHONE,
        ActionType.CHECK_AVAILABILITY,
    }
)


class ActionRiskDecision(BaseModel):
    action: ActionType
    risk_level: ActionRiskLevel
    requires_hitl: bool
    blocked_by_deposit_cap: bool = False
    reason: str


def classify_action_risk(
    action: ActionType | str,
    *,
    deposit_amount: int = 0,
    allow_deposit_max: int = 0,
    require_submit_approval: bool = True,
) -> ActionRiskDecision:
    """Classify action risk before dispatching to Tier 3 (MVP-17)."""
    act = action if isinstance(action, ActionType) else ActionType(action)

    if act in _LOW_RISK_ACTIONS:
        return ActionRiskDecision(
            action=act,
            risk_level=ActionRiskLevel.LOW,
            requires_hitl=False,
            reason="Low-risk read/fill action executes automatically",
        )

    if act == ActionType.CONFIRM_DEPOSIT:
        if deposit_amount > allow_deposit_max:
            return ActionRiskDecision(
                action=act,
                risk_level=ActionRiskLevel.HIGH,
                requires_hitl=True,
                blocked_by_deposit_cap=True,
                reason=(
                    f"Deposit {deposit_amount} exceeds allow_deposit_max ({allow_deposit_max})"
                ),
            )
        return ActionRiskDecision(
            action=act,
            risk_level=ActionRiskLevel.LOW,
            requires_hitl=False,
            blocked_by_deposit_cap=False,
            reason=(
                f"Deposit {deposit_amount} is within allow_deposit_max ({allow_deposit_max})"
            ),
        )

    if act == ActionType.FINAL_SUBMIT and not require_submit_approval:
        return ActionRiskDecision(
            action=act,
            risk_level=ActionRiskLevel.LOW,
            requires_hitl=False,
            reason="Auto-submit enabled for low-risk booking",
        )

    return ActionRiskDecision(
        action=act,
        risk_level=ActionRiskLevel.HIGH,
        requires_hitl=True,
        reason=f"High-risk action '{act}' gated by Safety HITL",
    )


class HitlStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class HitlRequest(BaseModel):
    hitl_id: str
    booking_id: str
    task_id: str | None = None
    reason: str
    prompt_text: str
    status: HitlStatus
    decision: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    expires_at: datetime
    trace_id: str
    created_at: datetime


class HitlManager:
    """Manages HITL approval lifecycle in agent_hitl_requests."""

    def __init__(
        self,
        db: DatabasePool,
        *,
        clock: Clock | None = None,
        default_timeout_seconds: int = 300,
    ) -> None:
        self._db = db
        self._clock = clock or SystemClock()
        self._default_timeout_seconds = default_timeout_seconds

    @staticmethod
    def _row_to_model(row: object) -> HitlRequest:
        decided_at_raw = row["decided_at"]  # type: ignore[index]
        return HitlRequest(
            hitl_id=row["hitl_id"],  # type: ignore[index]
            booking_id=row["booking_id"],  # type: ignore[index]
            task_id=row["task_id"],  # type: ignore[index]
            reason=row["reason"],  # type: ignore[index]
            prompt_text=row["prompt_text"],  # type: ignore[index]
            status=HitlStatus(row["status"]),  # type: ignore[index]
            decision=row["decision"],  # type: ignore[index]
            decided_by=row["decided_by"],  # type: ignore[index]
            decided_at=datetime.fromisoformat(decided_at_raw) if decided_at_raw else None,
            expires_at=datetime.fromisoformat(row["expires_at"]),  # type: ignore[index]
            trace_id=row["trace_id"],  # type: ignore[index]
            created_at=datetime.fromisoformat(row["created_at"]),  # type: ignore[index]
        )

    async def create_request(
        self,
        *,
        booking_id: str,
        reason: str,
        prompt_text: str,
        task_id: str | None = None,
        ttl_seconds: int | None = None,
        trace_id: str | None = None,
    ) -> HitlRequest:
        now = self._clock.utc_now()
        expires_at = now + timedelta(seconds=ttl_seconds or self._default_timeout_seconds)
        hitl_id = f"hitl_{uuid.uuid4().hex[:20]}"
        active_trace = trace_id or get_trace_id() or generate_trace_id()

        async with self._db.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO agent_hitl_requests (
                    hitl_id, booking_id, task_id, reason, prompt_text,
                    status, decision, decided_by, decided_at,
                    expires_at, trace_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?)
                """,
                (
                    hitl_id,
                    booking_id,
                    task_id,
                    reason,
                    prompt_text,
                    str(HitlStatus.PENDING),
                    expires_at.isoformat(),
                    active_trace,
                    now.isoformat(),
                ),
            )
            cursor = await conn.execute(
                "SELECT * FROM agent_hitl_requests WHERE hitl_id = ?",
                (hitl_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_model(row)

    async def get_request(self, hitl_id: str) -> HitlRequest:
        async with self._db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM agent_hitl_requests WHERE hitl_id = ?",
                (hitl_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            raise NotFoundError(
                f"HITL request '{hitl_id}' not found",
                code=ErrorCode.HITL_NOT_FOUND,
                details={"hitl_id": hitl_id},
            )
        return self._row_to_model(row)

    async def resolve(
        self,
        hitl_id: str,
        *,
        decision: Literal["approved", "rejected"],
        decided_by: str = "operator",
    ) -> HitlRequest:
        now = self._clock.utc_now()
        now_iso = now.isoformat()
        target_status = HitlStatus.APPROVED if decision == "approved" else HitlStatus.REJECTED

        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                "SELECT * FROM agent_hitl_requests WHERE hitl_id = ?",
                (hitl_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                raise NotFoundError(
                    f"HITL request '{hitl_id}' not found",
                    code=ErrorCode.HITL_NOT_FOUND,
                )
            current = self._row_to_model(row)
            if current.status != HitlStatus.PENDING:
                raise BookingAgentError(
                    f"HITL request '{hitl_id}' already finalized as '{current.status}'",
                    code=ErrorCode.INVALID_STATE_TRANSITION,
                    category=ErrorCategory.STATE_TRANSITION,
                )
            if current.expires_at <= now:
                await conn.execute(
                    "UPDATE agent_hitl_requests SET status = ? WHERE hitl_id = ?",
                    (str(HitlStatus.EXPIRED), hitl_id),
                )
                raise BookingAgentError(
                    f"HITL request '{hitl_id}' expired at {current.expires_at.isoformat()}",
                    code=ErrorCode.HITL_EXPIRED,
                    category=ErrorCategory.TIMEOUT,
                )

            await conn.execute(
                """
                UPDATE agent_hitl_requests
                SET status = ?, decision = ?, decided_by = ?, decided_at = ?
                WHERE hitl_id = ?
                """,
                (str(target_status), decision, decided_by, now_iso, hitl_id),
            )
            cursor = await conn.execute(
                "SELECT * FROM agent_hitl_requests WHERE hitl_id = ?",
                (hitl_id,),
            )
            updated_row = await cursor.fetchone()
        return self._row_to_model(updated_row)

    async def list_pending(self, *, booking_id: str | None = None) -> list[HitlRequest]:
        async with self._db.connection() as conn:
            if booking_id is not None:
                cursor = await conn.execute(
                    """
                    SELECT * FROM agent_hitl_requests
                    WHERE status = ? AND booking_id = ?
                    ORDER BY created_at ASC
                    """,
                    (str(HitlStatus.PENDING), booking_id),
                )
            else:
                cursor = await conn.execute(
                    """
                    SELECT * FROM agent_hitl_requests
                    WHERE status = ?
                    ORDER BY created_at ASC
                    """,
                    (str(HitlStatus.PENDING),),
                )
            rows = await cursor.fetchall()
        return [self._row_to_model(r) for r in rows]

    async def expire_stale(self) -> int:
        expired = await self.expire_stale_requests()
        return len(expired)

    async def expire_stale_requests(self) -> list[HitlRequest]:
        """Mark all timed-out PENDING requests as EXPIRED and return them."""
        now_iso = self._clock.utc_now().isoformat()
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM agent_hitl_requests
                WHERE status = ? AND expires_at <= ?
                ORDER BY created_at ASC
                """,
                (str(HitlStatus.PENDING), now_iso),
            )
            rows = await cursor.fetchall()
            if not rows:
                return []

            await conn.execute(
                """
                UPDATE agent_hitl_requests
                SET status = ?
                WHERE status = ? AND expires_at <= ?
                """,
                (str(HitlStatus.EXPIRED), str(HitlStatus.PENDING), now_iso),
            )
        return [
            self._row_to_model(r).model_copy(update={"status": HitlStatus.EXPIRED})
            for r in rows
        ]

    async def create_otp_request(
        self,
        *,
        booking_id: str,
        channel: str = "sms",
        prompt_text: str | None = None,
        task_id: str | None = None,
        ttl_seconds: int = OTP_MAX_TIMEOUT_SECONDS,
        trace_id: str | None = None,
    ) -> HitlRequest:
        """Create a web-only OTP hibernation request capped at 15 minutes (900s)."""
        bounded_ttl = max(1, min(int(ttl_seconds), OTP_MAX_TIMEOUT_SECONDS))
        clean_channel = channel.strip().lower() or "sms"
        return await self.create_request(
            booking_id=booking_id,
            reason=f"otp:{clean_channel}",
            prompt_text=prompt_text
            or f"Enter {clean_channel.upper()} OTP for booking {booking_id}",
            task_id=task_id,
            ttl_seconds=bounded_ttl,
            trace_id=trace_id,
        )

    async def resolve_otp(
        self,
        hitl_id: str,
        *,
        otp_code: str,
        submitted_by: str = "user",
    ) -> HitlRequest:
        """Verify and consume an OTP challenge within its 15-minute window."""
        cleaned = otp_code.strip()
        if not _OTP_CODE_RE.match(cleaned):
            raise ValidationError(
                "OTP code must be 4-12 alphanumeric characters",
                code=ErrorCode.OTP_INVALID,
            )

        now = self._clock.utc_now()
        now_iso = now.isoformat()
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                "SELECT * FROM agent_hitl_requests WHERE hitl_id = ?",
                (hitl_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                raise NotFoundError(
                    f"OTP request '{hitl_id}' not found",
                    code=ErrorCode.HITL_NOT_FOUND,
                )
            current = self._row_to_model(row)
            if current.status != HitlStatus.PENDING:
                code = (
                    ErrorCode.OTP_TIMEOUT
                    if current.status == HitlStatus.EXPIRED
                    else ErrorCode.INVALID_STATE_TRANSITION
                )
                raise BookingAgentError(
                    f"OTP request '{hitl_id}' already finalized as '{current.status}'",
                    code=code,
                    category=ErrorCategory.TIMEOUT
                    if current.status == HitlStatus.EXPIRED
                    else ErrorCategory.STATE_TRANSITION,
                )
            if current.expires_at <= now:
                await conn.execute(
                    "UPDATE agent_hitl_requests SET status = ? WHERE hitl_id = ?",
                    (str(HitlStatus.EXPIRED), hitl_id),
                )
                raise BookingAgentError(
                    f"OTP request '{hitl_id}' timed out at {current.expires_at.isoformat()}",
                    code=ErrorCode.OTP_TIMEOUT,
                    category=ErrorCategory.TIMEOUT,
                )

            await conn.execute(
                """
                UPDATE agent_hitl_requests
                SET status = ?, decision = ?, decided_by = ?, decided_at = ?
                WHERE hitl_id = ?
                """,
                (
                    str(HitlStatus.APPROVED),
                    f"otp_verified:{len(cleaned)}c",
                    submitted_by,
                    now_iso,
                    hitl_id,
                ),
            )
            cursor = await conn.execute(
                "SELECT * FROM agent_hitl_requests WHERE hitl_id = ?",
                (hitl_id,),
            )
            updated_row = await cursor.fetchone()
        return self._row_to_model(updated_row)
