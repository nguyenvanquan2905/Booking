"""SQLite Durable Queue, scheduled_wakeups, & LongTaskRunner wrapper (MVP-16 — owner: C)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel

from booking_agent.agent.guardrails.layer3_hitl import OTP_MAX_TIMEOUT_SECONDS, HitlManager
from booking_agent.booking.models import BookingCreateRequest, BookingRecord, BookingStatus
from booking_agent.booking.service import BookingService
from booking_agent.shared.clock import Clock, SystemClock
from booking_agent.shared.db import DatabasePool
from booking_agent.shared.errors import BookingAgentError, ErrorCategory, ErrorCode, NotFoundError
from booking_agent.shared.trace import generate_trace_id, get_trace_id

if TYPE_CHECKING:
    from booking_agent.agent.graph import BookingAgentRunner, BookingRunResult


class TaskStatus(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class WakeupStatus(StrEnum):
    SCHEDULED = "scheduled"
    AWOKEN = "awoken"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class AgentTask(BaseModel):
    task_id: str
    booking_id: str
    site_id: str
    tier: int
    status: TaskStatus
    priority: int
    attempts: int
    max_attempts: int
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    error_code: str | None = None
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    locked_by: str | None = None
    locked_until: datetime | None = None
    available_at: datetime
    trace_id: str
    created_at: datetime
    updated_at: datetime


class ScheduledWakeup(BaseModel):
    wakeup_id: str
    task_id: str | None = None
    thread_id: str
    booking_id: str
    kind: str
    wake_at: datetime
    status: WakeupStatus
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@runtime_checkable
class LongTaskRunner(Protocol):
    """MVP-16 abstract interface allowing future Temporal upgrade without graph changes."""

    async def start_task(
        self,
        request: BookingCreateRequest,
        *,
        requested_tier: int | None = None,
        priority: int = 0,
        trace_id: str | None = None,
    ) -> tuple[str, AgentTask | None]: ...

    async def wait_event_with_timeout(
        self,
        *,
        thread_id: str,
        booking_id: str,
        kind: str = "otp",
        timeout_seconds: int = OTP_MAX_TIMEOUT_SECONDS,
        task_id: str | None = None,
    ) -> ScheduledWakeup: ...

    async def wake_task(
        self,
        thread_id: str,
        *,
        otp_code: str,
        submitted_by: str = "user",
    ) -> BookingRunResult: ...


class DurableQueue:
    """Persistent task queue in agent_tasks with BEGIN IMMEDIATE claim & retry/backoff."""

    def __init__(self, db: DatabasePool, *, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    @staticmethod
    def _row_to_task(row: object) -> AgentTask:
        result_raw = row["result_json"]  # type: ignore[index]
        locked_until_raw = row["locked_until"]  # type: ignore[index]
        claimed_at_raw = row["claimed_at"]  # type: ignore[index]
        return AgentTask(
            task_id=row["task_id"],  # type: ignore[index]
            booking_id=row["booking_id"],  # type: ignore[index]
            site_id=row["site_id"],  # type: ignore[index]
            tier=int(row["tier"]),  # type: ignore[index]
            status=TaskStatus(row["status"]),  # type: ignore[index]
            priority=int(row["priority"]),  # type: ignore[index]
            attempts=int(row["attempts"]),  # type: ignore[index]
            max_attempts=int(row["max_attempts"]),  # type: ignore[index]
            payload=json.loads(row["payload_json"]),  # type: ignore[index]
            result=json.loads(result_raw) if result_raw else None,
            error_code=row["error_code"],  # type: ignore[index]
            claimed_by=row["claimed_by"],  # type: ignore[index]
            claimed_at=datetime.fromisoformat(claimed_at_raw) if claimed_at_raw else None,
            locked_by=row["locked_by"],  # type: ignore[index]
            locked_until=datetime.fromisoformat(locked_until_raw) if locked_until_raw else None,
            available_at=datetime.fromisoformat(row["available_at"]),  # type: ignore[index]
            trace_id=row["trace_id"],  # type: ignore[index]
            created_at=datetime.fromisoformat(row["created_at"]),  # type: ignore[index]
            updated_at=datetime.fromisoformat(row["updated_at"]),  # type: ignore[index]
        )

    @staticmethod
    def _row_to_wakeup(row: object) -> ScheduledWakeup:
        return ScheduledWakeup(
            wakeup_id=row["wakeup_id"],  # type: ignore[index]
            task_id=row["task_id"],  # type: ignore[index]
            thread_id=row["thread_id"],  # type: ignore[index]
            booking_id=row["booking_id"],  # type: ignore[index]
            kind=row["kind"],  # type: ignore[index]
            wake_at=datetime.fromisoformat(row["wake_at"]),  # type: ignore[index]
            status=WakeupStatus(row["status"]),  # type: ignore[index]
            payload=json.loads(row["payload_json"]),  # type: ignore[index]
            created_at=datetime.fromisoformat(row["created_at"]),  # type: ignore[index]
            updated_at=datetime.fromisoformat(row["updated_at"]),  # type: ignore[index]
        )

    async def enqueue(
        self,
        *,
        booking_id: str,
        site_id: str,
        payload: dict[str, Any],
        tier: int = 1,
        priority: int = 0,
        max_attempts: int = 3,
        delay_seconds: float = 0.0,
        trace_id: str | None = None,
    ) -> AgentTask:
        now = self._clock.utc_now()
        available_at = now + timedelta(seconds=max(0.0, delay_seconds))
        task_id = f"tsk_{uuid.uuid4().hex[:20]}"
        active_trace = trace_id or get_trace_id() or generate_trace_id()

        async with self._db.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO agent_tasks (
                    task_id, booking_id, site_id, tier, status,
                    priority, attempts, max_attempts, payload_json,
                    result_json, error_code, claimed_by, claimed_at,
                    locked_by, locked_until, available_at, trace_id,
                    created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL, NULL, NULL, NULL,
                    NULL, NULL, ?, ?, ?, ?
                )
                """,
                (
                    task_id,
                    booking_id,
                    site_id.strip().lower(),
                    tier,
                    str(TaskStatus.PENDING),
                    priority,
                    max_attempts,
                    json.dumps(payload, ensure_ascii=False, default=str),
                    available_at.isoformat(),
                    active_trace,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            cursor = await conn.execute(
                "SELECT * FROM agent_tasks WHERE task_id = ?",
                (task_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_task(row)

    async def claim_next(
        self,
        worker_id: str,
        *,
        lease_seconds: int = 60,
    ) -> AgentTask | None:
        """Reclaim stale leases and atomically claim next ready task in BEGIN IMMEDIATE."""
        now = self._clock.utc_now()
        now_iso = now.isoformat()
        locked_until_iso = (now + timedelta(seconds=lease_seconds)).isoformat()

        async with self._db.transaction() as conn:
            await conn.execute(
                """
                UPDATE agent_tasks
                SET status = CASE
                        WHEN attempts >= max_attempts THEN ?
                        ELSE ?
                    END,
                    claimed_by = NULL,
                    claimed_at = NULL,
                    locked_by = NULL,
                    locked_until = NULL,
                    updated_at = ?
                WHERE status = ? AND locked_until <= ?
                """,
                (
                    str(TaskStatus.DEAD_LETTER),
                    str(TaskStatus.PENDING),
                    now_iso,
                    str(TaskStatus.LEASED),
                    now_iso,
                ),
            )

            cursor = await conn.execute(
                """
                SELECT task_id FROM agent_tasks
                WHERE status = ? AND available_at <= ?
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """,
                (str(TaskStatus.PENDING), now_iso),
            )
            candidate = await cursor.fetchone()
            if candidate is None:
                return None

            task_id = candidate["task_id"]
            await conn.execute(
                """
                UPDATE agent_tasks
                SET status = ?,
                    attempts = attempts + 1,
                    claimed_by = ?,
                    claimed_at = ?,
                    locked_by = ?,
                    locked_until = ?,
                    updated_at = ?
                WHERE task_id = ? AND status = ?
                """,
                (
                    str(TaskStatus.LEASED),
                    worker_id,
                    now_iso,
                    worker_id,
                    locked_until_iso,
                    now_iso,
                    task_id,
                    str(TaskStatus.PENDING),
                ),
            )
            cursor = await conn.execute(
                "SELECT * FROM agent_tasks WHERE task_id = ?",
                (task_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_task(row)

    async def complete(self, task_id: str, result: dict[str, Any] | None = None) -> AgentTask:
        now_iso = self._clock.utc_now_iso()
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                """
                UPDATE agent_tasks
                SET status = ?,
                    result_json = ?,
                    claimed_by = NULL,
                    claimed_at = NULL,
                    locked_by = NULL,
                    locked_until = NULL,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (
                    str(TaskStatus.COMPLETED),
                    json.dumps(result or {}, ensure_ascii=False, default=str),
                    now_iso,
                    task_id,
                ),
            )
            if cursor.rowcount == 0:
                raise NotFoundError(
                    f"Task '{task_id}' not found",
                    code=ErrorCode.QUEUE_EMPTY,
                )
            cursor = await conn.execute(
                "SELECT * FROM agent_tasks WHERE task_id = ?",
                (task_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_task(row)

    async def fail(
        self,
        task_id: str,
        *,
        error_code: str,
        retry_delay_s: float = 5.0,
    ) -> AgentTask:
        now = self._clock.utc_now()
        now_iso = now.isoformat()

        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                "SELECT * FROM agent_tasks WHERE task_id = ?",
                (task_id,),
            )
            existing = await cursor.fetchone()
            if existing is None:
                raise NotFoundError(f"Task '{task_id}' not found", code=ErrorCode.QUEUE_EMPTY)

            attempts = int(existing["attempts"])
            max_attempts = int(existing["max_attempts"])
            if attempts < max_attempts:
                next_status = TaskStatus.PENDING
                backoff = retry_delay_s * (2 ** max(0, attempts - 1))
                available_iso = (now + timedelta(seconds=backoff)).isoformat()
            else:
                next_status = TaskStatus.DEAD_LETTER
                available_iso = existing["available_at"]

            await conn.execute(
                """
                UPDATE agent_tasks
                SET status = ?,
                    error_code = ?,
                    claimed_by = NULL,
                    claimed_at = NULL,
                    locked_by = NULL,
                    locked_until = NULL,
                    available_at = ?,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (str(next_status), error_code, available_iso, now_iso, task_id),
            )
            cursor = await conn.execute(
                "SELECT * FROM agent_tasks WHERE task_id = ?",
                (task_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_task(row)

    async def cancel_for_booking(self, booking_id: str) -> int:
        """Cancel pending/leased tasks and scheduled wakeups when a booking is cancelled."""
        now_iso = self._clock.utc_now_iso()
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                """
                UPDATE agent_tasks
                SET status = ?,
                    claimed_by = NULL,
                    claimed_at = NULL,
                    locked_by = NULL,
                    locked_until = NULL,
                    updated_at = ?
                WHERE booking_id = ? AND status IN (?, ?)
                """,
                (
                    str(TaskStatus.FAILED),
                    now_iso,
                    booking_id,
                    str(TaskStatus.PENDING),
                    str(TaskStatus.LEASED),
                ),
            )
            await conn.execute(
                """
                UPDATE agent_scheduled_wakeups
                SET status = ?, updated_at = ?
                WHERE booking_id = ? AND status = ?
                """,
                (
                    str(WakeupStatus.CANCELLED),
                    now_iso,
                    booking_id,
                    str(WakeupStatus.SCHEDULED),
                ),
            )
            return cursor.rowcount or 0

    async def schedule_wakeup(
        self,
        *,
        thread_id: str,
        booking_id: str,
        kind: str = "otp",
        timeout_seconds: int = OTP_MAX_TIMEOUT_SECONDS,
        task_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> ScheduledWakeup:
        now = self._clock.utc_now()
        bounded = max(1, min(int(timeout_seconds), OTP_MAX_TIMEOUT_SECONDS))
        wake_at = now + timedelta(seconds=bounded)
        wakeup_id = f"wk_{uuid.uuid4().hex[:20]}"

        async with self._db.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO agent_scheduled_wakeups (
                    wakeup_id, task_id, thread_id, booking_id, kind,
                    wake_at, status, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    wakeup_id,
                    task_id,
                    thread_id,
                    booking_id,
                    kind,
                    wake_at.isoformat(),
                    str(WakeupStatus.SCHEDULED),
                    json.dumps(payload or {}, ensure_ascii=False),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            cursor = await conn.execute(
                "SELECT * FROM agent_scheduled_wakeups WHERE wakeup_id = ?",
                (wakeup_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_wakeup(row)

    async def mark_wakeup_awoken(self, thread_id: str) -> None:
        now_iso = self._clock.utc_now_iso()
        async with self._db.transaction() as conn:
            await conn.execute(
                """
                UPDATE agent_scheduled_wakeups
                SET status = ?, updated_at = ?
                WHERE thread_id = ? AND status = ?
                """,
                (str(WakeupStatus.AWOKEN), now_iso, thread_id, str(WakeupStatus.SCHEDULED)),
            )

    async def expire_due_wakeups(self) -> list[ScheduledWakeup]:
        now_iso = self._clock.utc_now_iso()
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM agent_scheduled_wakeups
                WHERE status = ? AND wake_at <= ?
                ORDER BY wake_at ASC
                """,
                (str(WakeupStatus.SCHEDULED), now_iso),
            )
            rows = await cursor.fetchall()
            if not rows:
                return []
            await conn.execute(
                """
                UPDATE agent_scheduled_wakeups
                SET status = ?, updated_at = ?
                WHERE status = ? AND wake_at <= ?
                """,
                (str(WakeupStatus.EXPIRED), now_iso, str(WakeupStatus.SCHEDULED), now_iso),
            )
        return [
            self._row_to_wakeup(r).model_copy(update={"status": WakeupStatus.EXPIRED})
            for r in rows
        ]

    async def get_task(self, task_id: str) -> AgentTask | None:
        async with self._db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM agent_tasks WHERE task_id = ?",
                (task_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_task(row) if row is not None else None

    async def list_tasks(
        self,
        *,
        booking_id: str | None = None,
        status: TaskStatus | None = None,
    ) -> list[AgentTask]:
        clauses: list[str] = []
        params: list[Any] = []
        if booking_id is not None:
            clauses.append("booking_id = ?")
            params.append(booking_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(str(status))

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        async with self._db.connection() as conn:
            cursor = await conn.execute(
                f"SELECT * FROM agent_tasks {where_sql} ORDER BY created_at ASC",
                params,
            )
            rows = await cursor.fetchall()
        return [self._row_to_task(r) for r in rows]


class DurableBookingWrapper:
    """LongTaskRunner implementation enforcing web-only 15-minute OTP timeout (MVP-16)."""

    def __init__(
        self,
        *,
        queue: DurableQueue,
        booking_service: BookingService,
        hitl_manager: HitlManager,
        runner: BookingAgentRunner,
        otp_timeout_seconds: int = OTP_MAX_TIMEOUT_SECONDS,
        clock: Clock | None = None,
    ) -> None:
        if otp_timeout_seconds < 1 or otp_timeout_seconds > OTP_MAX_TIMEOUT_SECONDS:
            raise ValueError(
                f"otp_timeout_seconds must be within 1..{OTP_MAX_TIMEOUT_SECONDS}s (15 min max)"
            )
        self._queue = queue
        self._booking_service = booking_service
        self._hitl_manager = hitl_manager
        self._runner = runner
        self._otp_timeout_seconds = otp_timeout_seconds
        self._clock = clock or SystemClock()

    @property
    def otp_timeout_seconds(self) -> int:
        return self._otp_timeout_seconds

    async def start_task(
        self,
        request: BookingCreateRequest,
        *,
        requested_tier: int | None = None,
        priority: int = 0,
        trace_id: str | None = None,
    ) -> tuple[str, AgentTask | None]:
        """LongTaskRunner.start_task: persist booking and enqueue durable task."""
        return await self.enqueue_booking(
            request,
            requested_tier=requested_tier,
            priority=priority,
            trace_id=trace_id,
        )

    async def wait_event_with_timeout(
        self,
        *,
        thread_id: str,
        booking_id: str,
        kind: str = "otp",
        timeout_seconds: int = OTP_MAX_TIMEOUT_SECONDS,
        task_id: str | None = None,
    ) -> ScheduledWakeup:
        """LongTaskRunner.wait_event_with_timeout: register wakeup bounded at 15 min."""
        if timeout_seconds < 1 or timeout_seconds > OTP_MAX_TIMEOUT_SECONDS:
            raise ValueError(
                f"timeout_seconds must be within 1..{OTP_MAX_TIMEOUT_SECONDS}s (15 min max)"
            )
        return await self._queue.schedule_wakeup(
            thread_id=thread_id,
            booking_id=booking_id,
            kind=kind,
            timeout_seconds=timeout_seconds,
            task_id=task_id,
        )

    async def wake_task(
        self,
        thread_id: str,
        *,
        otp_code: str,
        submitted_by: str = "user",
    ) -> BookingRunResult:
        """LongTaskRunner.wake_task: wake hibernated LangGraph thread via OTP webhook."""
        return await self.resume_otp(
            thread_id,
            otp_code=otp_code,
            submitted_by=submitted_by,
        )

    async def enqueue_booking(
        self,
        request: BookingCreateRequest,
        *,
        requested_tier: int | None = None,
        priority: int = 0,
        trace_id: str | None = None,
    ) -> tuple[str, AgentTask | None]:
        """Persist booking and enqueue durable task (returns existing booking on replay)."""
        booking, is_replay = await self._booking_service.create_booking(request, trace_id=trace_id)
        if is_replay:
            return booking.booking_id, None

        await self._booking_service.transition_status(
            booking.booking_id,
            BookingStatus.QUEUED,
            reason="enqueued_durable",
            actor="agent.durable_wrapper",
            trace_id=booking.trace_id,
        )
        task = await self._queue.enqueue(
            booking_id=booking.booking_id,
            site_id=request.site_id,
            tier=requested_tier or 1,
            priority=priority,
            payload={
                "request": request.model_dump(mode="json"),
                "requested_tier": requested_tier,
            },
            trace_id=booking.trace_id,
        )
        return booking.booking_id, task

    async def process_next(
        self,
        worker_id: str,
        *,
        lease_seconds: int = 60,
    ) -> BookingRunResult | None:
        """Sweep expired OTP waits, claim next durable task, and execute it."""
        await self.sweep_expired_otp()
        task = await self._queue.claim_next(worker_id, lease_seconds=lease_seconds)
        if task is None:
            return None

        req = BookingCreateRequest.model_validate(task.payload["request"])
        requested_tier = task.payload.get("requested_tier")
        try:
            run_res = await self._runner.run_existing_booking(
                task.booking_id,
                req,
                requested_tier=requested_tier,
            )
            if run_res.interrupted:
                await self.wait_event_with_timeout(
                    thread_id=run_res.thread_id,
                    booking_id=task.booking_id,
                    kind=(run_res.hitl_payload or {}).get("wait_kind", "otp"),
                    timeout_seconds=self._otp_timeout_seconds,
                    task_id=task.task_id,
                )
            await self._queue.complete(
                task.task_id,
                {
                    "status": str(run_res.booking.status),
                    "interrupted": run_res.interrupted,
                },
            )
            return run_res
        except Exception as exc:
            await self._queue.fail(task.task_id, error_code=type(exc).__name__)
            raise

    async def sweep_expired_otp(self) -> int:
        """Expire OTP/HITL waits and scheduled wakeups older than 15 minutes."""
        await self._queue.expire_due_wakeups()
        expired_requests = await self._hitl_manager.expire_stale_requests()
        transitioned = 0
        for req in expired_requests:
            booking = await self._booking_service.get_booking(req.booking_id)
            if booking.status != BookingStatus.AWAITING_HITL:
                continue
            is_otp = req.reason.startswith("otp:")
            await self._booking_service.transition_status(
                booking.booking_id,
                BookingStatus.EXPIRED,
                reason="otp_timeout_15m" if is_otp else "hitl_timeout",
                actor="agent.durable_wrapper",
                trace_id=booking.trace_id,
                error_code=str(ErrorCode.OTP_TIMEOUT if is_otp else ErrorCode.HITL_EXPIRED),
                error_message="Verification window expired",
            )
            await self._runner.release_resources(booking.booking_id)
            await self._queue.cancel_for_booking(booking.booking_id)
            transitioned += 1
        return transitioned

    async def cancel_booking(
        self,
        booking_id: str,
        *,
        reason: str = "user_cancelled",
        actor: str = "user",
    ) -> BookingRecord:
        """MVP-39: idempotent cancel releasing queue tasks, wakeups, HITL, leases & checkpoints."""

        async def _durable_cleanup(bid: str) -> None:
            await self._queue.cancel_for_booking(bid)
            for req in await self._hitl_manager.list_pending(booking_id=bid):
                await self._hitl_manager.resolve(
                    req.hitl_id,
                    decision="rejected",
                    decided_by=actor,
                )

        return await self._runner.cancel_booking(
            booking_id,
            reason=reason,
            actor=actor,
            extra_cleanup=_durable_cleanup,
        )

    async def resume_otp(
        self,
        thread_id: str,
        *,
        otp_code: str,
        submitted_by: str = "user",
    ) -> BookingRunResult:
        """Resume a hibernated web OTP booking after checking the 15-minute ceiling."""
        await self.sweep_expired_otp()
        booking = await self._booking_service.get_booking(thread_id)
        if booking.status == BookingStatus.EXPIRED:
            raise BookingAgentError(
                f"Booking '{thread_id}' OTP hibernation expired after 15 minutes",
                code=ErrorCode.OTP_TIMEOUT,
                category=ErrorCategory.TIMEOUT,
            )
        await self._queue.mark_wakeup_awoken(thread_id)
        return await self._runner.resume_with_otp(
            thread_id,
            otp_code=otp_code,
            submitted_by=submitted_by,
        )
