"""Master Router, ControlPlaneClient & Port Contracts (MVP-01/04/06/07/13 — owner: C)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from booking_agent.agent.guardrails.layer1_normalize import NormalizedBookingInput
from booking_agent.agent.registry import (
    ExecutionTier,
    LearningHookPort,
    NoopLearningHook,
    ProfileHealthMonitor,
    TierRegistry,
)
from booking_agent.shared.clock import Clock, SystemClock
from booking_agent.shared.errors import ErrorCode
from booking_agent.shared.logging import get_logger

_logger = get_logger("agent.router")


class TaskStatusCode(StrEnum):
    """Canonical control-plane status codes returned by Browser Control (MVP-06)."""

    SUCCESS = "SUCCESS"
    NEED_OTP = "NEED_OTP"
    NEED_USER_CONFIRM = "NEED_USER_CONFIRM"
    NEED_REASONING = "NEED_REASONING"
    NO_ONLINE_FORM = "NO_ONLINE_FORM"
    FALLBACK_FAILED = "FALLBACK_FAILED"


class TaskSpec(BaseModel):
    """Pydantic control-plane input contract sent from Agent (C) to Browser Control (D)."""

    request_id: str
    trace_id: str
    site_id: str
    target_domain: str = ""
    channel: str = "web"
    restaurant_name: str
    party_size: int
    booking_time_iso: str
    customer_name: str
    customer_phone: str
    customer_email: str | None = None
    notes: str = ""
    allow_deposit_max: int = 0
    sandbox_session_id: str | None = None
    profile_lease_id: str | None = None
    storage_state: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskResult(BaseModel):
    """Pydantic control-plane output returned by Browser Control (D) to Agent (C)."""

    status_code: TaskStatusCode
    success: bool
    tier_used: int
    artifact_id: str | None = None
    confirmation_code: str | None = None
    a11y_tree_snapshot: str | None = None
    detected_channel: str = "web"
    hitl_trigger: str | None = None
    failure_code: str | None = None
    error_class: str | None = None
    error_message: str | None = None
    latest_storage_state: dict[str, Any] | None = None
    retryable: bool = False
    duration_ms: float = 0.0
    token_usage: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class BrowserExecutionRequest:
    """Dataclass execution payload passed from MasterRouter (C) to BrowserControlPort (D)."""

    booking_id: str
    trace_id: str
    site_id: str
    tier: int
    restaurant_name: str
    party_size: int
    booking_time_iso: str
    customer_name: str
    customer_phone: str
    customer_email: str | None = None
    notes: str = ""
    allow_deposit_max: int = 0
    sandbox_session_id: str | None = None
    profile_lease_id: str | None = None
    storage_state: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BrowserExecutionResult:
    """Normalized execution output returned by Browser Control (D)."""

    success: bool
    tier_used: int
    confirmation_code: str | None = None
    requires_hitl: bool = False
    hitl_reason: str | None = None
    retryable: bool = False
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: float = 0.0
    artifacts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    status_code: TaskStatusCode | None = None
    artifact_id: str | None = None
    a11y_tree_snapshot: str | None = None
    detected_channel: str = "web"
    hitl_trigger: str | None = None
    failure_code: str | None = None
    error_class: str | None = None
    latest_storage_state: dict[str, Any] | None = None
    token_usage: int = 0

    def to_task_result(self) -> TaskResult:
        """Convert to canonical MVP-06 TaskResult Pydantic contract."""
        code = self.status_code
        if code is None:
            if self.success:
                code = TaskStatusCode.SUCCESS
            elif self.requires_hitl:
                is_otp = (
                    self.metadata.get("wait_type") == "otp"
                    or (self.hitl_reason is not None and "otp" in self.hitl_reason.lower())
                )
                code = TaskStatusCode.NEED_OTP if is_otp else TaskStatusCode.NEED_USER_CONFIRM
            else:
                code = TaskStatusCode.FALLBACK_FAILED

        return TaskResult(
            status_code=code,
            success=self.success,
            tier_used=self.tier_used,
            artifact_id=self.artifact_id or (self.artifacts[0] if self.artifacts else None),
            confirmation_code=self.confirmation_code,
            a11y_tree_snapshot=self.a11y_tree_snapshot,
            detected_channel=self.detected_channel,
            hitl_trigger=self.hitl_trigger or self.hitl_reason,
            failure_code=self.failure_code or self.error_code,
            error_class=self.error_class,
            error_message=self.error_message,
            latest_storage_state=self.latest_storage_state,
            retryable=self.retryable,
            duration_ms=self.duration_ms,
            token_usage=self.token_usage,
            metadata=self.metadata,
        )


@runtime_checkable
class BrowserControlPort(Protocol):
    """Port interface implemented by D and consumed by C (MasterRouter / LangGraph)."""

    async def supports_tier(self, site_id: str, tier: int) -> bool: ...

    async def execute_booking(
        self,
        request: BrowserExecutionRequest,
    ) -> BrowserExecutionResult: ...


@runtime_checkable
class ControlPlanePort(Protocol):
    """MVP-06 RPC contract: execute_tier(tier, task_spec, session_id) -> TaskResult."""

    async def execute_tier(
        self,
        tier: int,
        task_spec: TaskSpec,
        session_id: str | None = None,
    ) -> TaskResult: ...


@runtime_checkable
class BrowserGatewayPort(Protocol):
    """MVP-01 / MVP-02 Unified Gateway primitives."""

    async def open_session(self, site_id: str, *, session_id: str | None = None) -> str: ...

    async def click(self, session_id: str, selector: str) -> None: ...

    async def screenshot(self, session_id: str) -> bytes: ...


@dataclass(slots=True)
class SandboxSpec:
    booking_id: str
    cpu_limit: float = 1.0
    mem_limit_mb: int = 1024
    zero_egress: bool = True


@dataclass(slots=True)
class SandboxSession:
    session_id: str
    booking_id: str
    status: str = "active"


SandboxHandle = SandboxSession


@runtime_checkable
class SandboxPort(Protocol):
    """Port interface implemented by B and consumed by Agent (C)."""

    async def acquire(self, booking_id: str) -> SandboxSession: ...

    async def release(self, session_id: str) -> None: ...

    async def is_healthy(self, session_id: str) -> bool: ...


@dataclass(slots=True)
class ContextLease:
    """Exclusive lease for a web browser profile & hydrated context."""

    lease_id: str
    profile_id: str
    site_id: str
    owner: str = ""
    proxy_url: str | None = None
    fingerprint_seed: str | None = None
    timezone: str = "Asia/Ho_Chi_Minh"
    storage_state: dict[str, Any] = field(default_factory=dict)
    expires_at: str | None = None


ProfileLease = ContextLease


@runtime_checkable
class ProfilePort(Protocol):
    """Port interface implemented by A and consumed by Agent (C) / Browser Control (D)."""

    async def acquire_lease(self, site_id: str, booking_id: str) -> ContextLease: ...

    async def release_lease(self, lease_id: str) -> None: ...


@runtime_checkable
class ContextLeasePort(ProfilePort, Protocol):
    """Extended MVP-01 ContextLease API supporting heartbeat and cookie/token write-back."""

    async def heartbeat(self, lease_id: str) -> bool: ...

    async def write_back(self, lease_id: str, storage_state: dict[str, Any]) -> None: ...


@runtime_checkable
class LiveViewPort(Protocol):
    """MVP-07 handshake: Agent (C) asks Browser Control (D, MVP-27) to open/close Live View."""

    async def request_open(self, booking_id: str, request: dict[str, Any]) -> str | None: ...

    async def close(self, booking_id: str) -> None: ...


@dataclass(slots=True)
class RoutingAttempt:
    tier: ExecutionTier
    success: bool
    retryable: bool
    status_code: TaskStatusCode = TaskStatusCode.FALLBACK_FAILED
    error_code: str | None = None
    error_class: str | None = None
    error_message: str | None = None
    duration_ms: float = 0.0
    token_usage: int = 0
    reason: str = ""


@dataclass(slots=True)
class RoutingResult:
    success: bool
    status_code: TaskStatusCode = TaskStatusCode.FALLBACK_FAILED
    tier_used: ExecutionTier | None = None
    confirmation_code: str | None = None
    artifact_id: str | None = None
    a11y_tree_snapshot: str | None = None
    latest_storage_state: dict[str, Any] | None = None
    requires_hitl: bool = False
    hitl_reason: str | None = None
    hitl_metadata: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_class: str | None = None
    error_message: str | None = None
    token_usage: int = 0
    attempts: list[RoutingAttempt] = field(default_factory=list)
    routing_reasons: list[str] = field(default_factory=list)
    session_kept: bool = False


@dataclass(slots=True)
class _ActiveResources:
    sandbox_session: SandboxSession | None = None
    profile_lease: ContextLease | None = None


class ControlPlaneClient:
    """Async RPC client implementing MVP-06 execute_tier(tier, task_spec, session_id)."""

    def __init__(self, port: BrowserControlPort | ControlPlanePort) -> None:
        self._port = port

    async def supports_tier(self, site_id: str, tier: int) -> bool:
        if hasattr(self._port, "supports_tier"):
            return await self._port.supports_tier(site_id, tier)  # type: ignore[union-attr]
        return True

    async def execute_tier(
        self,
        tier: int,
        task_spec: TaskSpec,
        session_id: str | None = None,
    ) -> TaskResult:
        """Invoke Browser Control either via native ControlPlanePort or BrowserControlPort."""
        if isinstance(self._port, ControlPlanePort):
            return await self._port.execute_tier(tier, task_spec, session_id)

        req = BrowserExecutionRequest(
            booking_id=task_spec.request_id,
            trace_id=task_spec.trace_id,
            site_id=task_spec.site_id,
            tier=tier,
            restaurant_name=task_spec.restaurant_name,
            party_size=task_spec.party_size,
            booking_time_iso=task_spec.booking_time_iso,
            customer_name=task_spec.customer_name,
            customer_phone=task_spec.customer_phone,
            customer_email=task_spec.customer_email,
            notes=task_spec.notes,
            allow_deposit_max=task_spec.allow_deposit_max,
            sandbox_session_id=session_id or task_spec.sandbox_session_id,
            profile_lease_id=task_spec.profile_lease_id,
            storage_state=task_spec.storage_state,
            metadata=dict(task_spec.metadata),
        )
        res: BrowserExecutionResult = await self._port.execute_booking(req)
        return res.to_task_result()


class MasterRouter:
    """Selects tiers via TierRegistry and cascades execution across ControlPlaneClient.

    * MVP-13: every decision (candidate order, capability skip, fallback) is logged with a reason.
    * MVP-07: ``keep_session_on_hitl=True`` keeps sandbox + lease alive on NEED_OTP /
      NEED_USER_CONFIRM (Short-Wait: same page, no new session on resume). Default ``False``
      releases everything (Long-Wait Hibernate: browser RAM -> 0 MB).
    * MVP-39: ``release_booking_resources()`` frees any sandbox/lease still held by a booking.
    """

    def __init__(
        self,
        registry: TierRegistry,
        browser_control: BrowserControlPort | ControlPlanePort | None = None,
        *,
        sandbox: SandboxPort | None = None,
        profile: ProfilePort | None = None,
        health_monitor: ProfileHealthMonitor | None = None,
        learning_hook: LearningHookPort | None = None,
        keep_session_on_hitl: bool = False,
        clock: Clock | None = None,
    ) -> None:
        self._registry = registry
        self._client = ControlPlaneClient(browser_control) if browser_control is not None else None
        self._sandbox = sandbox
        self._profile = profile
        self._health_monitor = health_monitor
        self._learning_hook = learning_hook or NoopLearningHook()
        self._keep_session_on_hitl = keep_session_on_hitl
        self._clock = clock or SystemClock()
        self._active: dict[str, _ActiveResources] = {}

    def active_bookings(self) -> list[str]:
        """Bookings currently holding sandbox sessions or profile leases."""
        return list(self._active)

    async def release_booking_resources(self, booking_id: str) -> bool:
        """Release sandbox session and profile lease still held by a booking (idempotent)."""
        res = self._active.pop(booking_id, None)
        if res is None:
            return False
        if res.profile_lease is not None and self._profile is not None:
            await self._profile.release_lease(res.profile_lease.lease_id)
        if res.sandbox_session is not None and self._sandbox is not None:
            await self._sandbox.release(res.sandbox_session.session_id)
        _logger.info("Booking resources released", extra={"booking_id": booking_id})
        return True

    async def _acquire(self, booking_id: str, site_id: str) -> _ActiveResources:
        existing = self._active.get(booking_id)
        if existing is not None:
            # Short-Wait resume: reuse the same sandbox/page instead of opening a new session.
            return existing
        res = _ActiveResources()
        self._active[booking_id] = res
        if self._sandbox is not None:
            res.sandbox_session = await self._sandbox.acquire(booking_id)
        if self._profile is not None:
            res.profile_lease = await self._profile.acquire_lease(site_id, booking_id)
        return res

    def _log_decision(self, booking_id: str, trace_id: str, reasons: list[str], msg: str) -> None:
        reasons.append(msg)
        _logger.info(
            "Routing decision",
            extra={"booking_id": booking_id, "trace_id": trace_id, "reason": msg},
        )

    async def execute(
        self,
        *,
        booking_id: str,
        trace_id: str,
        booking_input: NormalizedBookingInput,
        requested_tier: ExecutionTier | int | None = None,
        storage_state: dict[str, Any] | None = None,
        execution_metadata: dict[str, Any] | None = None,
    ) -> RoutingResult:
        """Attempt execution across candidate tiers with fallback and resource cleanup."""
        reasons: list[str] = []
        if self._client is None:
            self._log_decision(booking_id, trace_id, reasons, "BrowserControlPort chưa cấu hình")
            return RoutingResult(
                success=False,
                status_code=TaskStatusCode.FALLBACK_FAILED,
                error_code=ErrorCode.TIER_UNAVAILABLE,
                error_message="BrowserControlPort is not configured",
                routing_reasons=reasons,
            )

        site_id = booking_input.site_id
        for line in await self._registry.explain_routing(site_id, requested_tier=requested_tier):
            self._log_decision(booking_id, trace_id, reasons, line)
        candidates = await self._registry.resolve_candidate_tiers(
            site_id,
            requested_tier=requested_tier,
        )
        if not candidates:
            self._log_decision(booking_id, trace_id, reasons, "không còn cấp khả dụng")
            return RoutingResult(
                success=False,
                status_code=TaskStatusCode.FALLBACK_FAILED,
                error_code=ErrorCode.TIER_UNAVAILABLE,
                error_message=f"No enabled tiers available for site '{site_id}'",
                routing_reasons=reasons,
            )
        self._log_decision(
            booking_id,
            trace_id,
            reasons,
            f"thứ tự thử: {' → '.join(str(int(t)) for t in candidates)}",
        )

        attempts: list[RoutingAttempt] = []
        total_tokens = 0
        latest_state: dict[str, Any] | None = storage_state
        keep_session = False

        try:
            res = await self._acquire(booking_id, site_id)
            sandbox_session = res.sandbox_session
            profile_lease = res.profile_lease
            if profile_lease is not None:
                if (
                    self._health_monitor is not None
                    and not await self._health_monitor.is_eligible(profile_lease.profile_id)
                ):
                    self._log_decision(
                        booking_id,
                        trace_id,
                        reasons,
                        f"profile '{profile_lease.profile_id}' degraded/checkpointed -> dừng",
                    )
                    return RoutingResult(
                        success=False,
                        status_code=TaskStatusCode.FALLBACK_FAILED,
                        error_code=ErrorCode.PROFILE_DEGRADED,
                        error_message=(
                            f"Profile '{profile_lease.profile_id}' is degraded or checkpointed"
                        ),
                        routing_reasons=reasons,
                    )
                if not latest_state and profile_lease.storage_state:
                    latest_state = dict(profile_lease.storage_state)

            for tier in candidates:
                supported = await self._client.supports_tier(site_id, int(tier))
                if not supported:
                    self._log_decision(
                        booking_id,
                        trace_id,
                        reasons,
                        f"tier {int(tier)}: bỏ qua — capability không hỗ trợ (phát hiện lúc định "
                        "tuyến)",
                    )
                    continue

                started_ms = self._clock.monotonic_ms()
                spec = TaskSpec(
                    request_id=booking_id,
                    trace_id=trace_id,
                    site_id=site_id,
                    target_domain=site_id,
                    channel=booking_input.channel,
                    restaurant_name=booking_input.restaurant_name,
                    party_size=booking_input.party_size,
                    booking_time_iso=booking_input.booking_time.isoformat(),
                    customer_name=booking_input.customer_name,
                    customer_phone=booking_input.customer_phone,
                    customer_email=booking_input.customer_email,
                    notes=booking_input.notes,
                    allow_deposit_max=booking_input.allow_deposit_max,
                    sandbox_session_id=sandbox_session.session_id if sandbox_session else None,
                    profile_lease_id=profile_lease.lease_id if profile_lease else None,
                    storage_state=latest_state,
                    metadata=dict(execution_metadata or {}),
                )
                cp_res: TaskResult = await self._client.execute_tier(
                    int(tier),
                    spec,
                    sandbox_session.session_id if sandbox_session else None,
                )
                elapsed_ms = cp_res.duration_ms or max(
                    0.0, self._clock.monotonic_ms() - started_ms
                )
                total_tokens += cp_res.token_usage
                if cp_res.latest_storage_state:
                    latest_state = cp_res.latest_storage_state
                    if (
                        profile_lease is not None
                        and isinstance(self._profile, ContextLeasePort)
                    ):
                        await self._profile.write_back(
                            profile_lease.lease_id,
                            latest_state,
                        )

                attempt_reason = (
                    f"tier {int(tier)}: {cp_res.status_code}"
                    + (f" ({cp_res.failure_code})" if cp_res.failure_code else "")
                    + (" retryable" if cp_res.retryable and not cp_res.success else "")
                )
                self._log_decision(booking_id, trace_id, reasons, attempt_reason)
                attempts.append(
                    RoutingAttempt(
                        tier=tier,
                        success=cp_res.success,
                        retryable=cp_res.retryable,
                        status_code=cp_res.status_code,
                        error_code=cp_res.failure_code,
                        error_class=cp_res.error_class,
                        error_message=cp_res.error_message,
                        duration_ms=elapsed_ms,
                        token_usage=cp_res.token_usage,
                        reason=attempt_reason,
                    )
                )

                if cp_res.success or cp_res.status_code == TaskStatusCode.SUCCESS:
                    await self._registry.record_success(site_id, tier)
                    if self._health_monitor is not None and profile_lease is not None:
                        await self._health_monitor.record_session_outcome(
                            profile_id=profile_lease.profile_id,
                            site_id=site_id,
                            success=True,
                        )
                    await self._learning_hook.on_task_success(cp_res.artifact_id)
                    return RoutingResult(
                        success=True,
                        status_code=TaskStatusCode.SUCCESS,
                        tier_used=tier,
                        confirmation_code=cp_res.confirmation_code,
                        artifact_id=cp_res.artifact_id,
                        latest_storage_state=latest_state,
                        token_usage=total_tokens,
                        attempts=attempts,
                        routing_reasons=reasons,
                    )

                if cp_res.status_code == TaskStatusCode.NEED_REASONING:
                    return RoutingResult(
                        success=False,
                        status_code=TaskStatusCode.NEED_REASONING,
                        tier_used=tier,
                        artifact_id=cp_res.artifact_id,
                        a11y_tree_snapshot=cp_res.a11y_tree_snapshot,
                        latest_storage_state=latest_state,
                        token_usage=total_tokens,
                        attempts=attempts,
                        routing_reasons=reasons,
                    )

                if cp_res.status_code in (
                    TaskStatusCode.NEED_OTP,
                    TaskStatusCode.NEED_USER_CONFIRM,
                ):
                    hitl_meta = dict(cp_res.metadata)
                    if cp_res.status_code == TaskStatusCode.NEED_OTP:
                        hitl_meta.setdefault("wait_type", "otp")
                    keep_session = self._keep_session_on_hitl
                    hitl_meta["session_kept"] = keep_session
                    if keep_session and sandbox_session is not None:
                        hitl_meta["sandbox_session_id"] = sandbox_session.session_id
                    return RoutingResult(
                        success=False,
                        status_code=cp_res.status_code,
                        tier_used=tier,
                        artifact_id=cp_res.artifact_id,
                        latest_storage_state=latest_state,
                        requires_hitl=True,
                        hitl_reason=cp_res.hitl_trigger
                        or "Browser execution requested verification",
                        hitl_metadata=hitl_meta,
                        token_usage=total_tokens,
                        attempts=attempts,
                        routing_reasons=reasons,
                        session_kept=keep_session,
                    )

                await self._registry.record_failure(site_id, tier)
                if not cp_res.retryable:
                    if self._health_monitor is not None and profile_lease is not None:
                        await self._health_monitor.record_session_outcome(
                            profile_id=profile_lease.profile_id,
                            site_id=site_id,
                            success=False,
                            checkpoint_detected=(cp_res.failure_code == "CHECKPOINT"),
                            error=cp_res.error_message,
                        )
                    self._log_decision(
                        booking_id,
                        trace_id,
                        reasons,
                        f"tier {int(tier)}: lỗi không retry được -> dừng thác đổ",
                    )
                    return RoutingResult(
                        success=False,
                        status_code=cp_res.status_code,
                        tier_used=tier,
                        artifact_id=cp_res.artifact_id,
                        latest_storage_state=latest_state,
                        error_code=cp_res.failure_code or ErrorCode.TIER_EXHAUSTED,
                        error_class=cp_res.error_class,
                        error_message=cp_res.error_message or "Non-retryable execution failure",
                        token_usage=total_tokens,
                        attempts=attempts,
                        routing_reasons=reasons,
                    )
                self._log_decision(
                    booking_id, trace_id, reasons, f"tier {int(tier)}: trượt xuống cấp kế tiếp"
                )

            last_attempt = attempts[-1] if attempts else None
            self._log_decision(booking_id, trace_id, reasons, "đã thử hết các cấp")
            return RoutingResult(
                success=False,
                status_code=TaskStatusCode.FALLBACK_FAILED,
                tier_used=last_attempt.tier if last_attempt else None,
                latest_storage_state=latest_state,
                error_code=ErrorCode.TIER_EXHAUSTED,
                error_class=last_attempt.error_class if last_attempt else None,
                error_message=(
                    last_attempt.error_message
                    if last_attempt and last_attempt.error_message
                    else "All candidate tiers exhausted or unsupported"
                ),
                token_usage=total_tokens,
                attempts=attempts,
                routing_reasons=reasons,
            )
        finally:
            if not keep_session:
                await self.release_booking_resources(booking_id)
