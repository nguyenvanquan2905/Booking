"""LangGraph 6-node booking workflow, Anti-Loop & compact state (MVP-10/12/15/17 — owner: C)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from booking_agent.agent.guardrails.layer1_normalize import (
    NormalizedBookingInput,
    normalize_booking_input,
)
from booking_agent.agent.guardrails.layer2_policy import (
    PolicyConfig,
    evaluate_policy,
    parse_and_guard_a11y,
)
from booking_agent.agent.guardrails.layer3_hitl import (
    OTP_MAX_TIMEOUT_SECONDS,
    ActionType,
    HitlManager,
    HitlStatus,
    WaitKind,
    classify_action_risk,
)
from booking_agent.agent.router import LiveViewPort, MasterRouter, TaskStatusCode
from booking_agent.booking import TERMINAL_STATUSES
from booking_agent.booking.models import BookingCreateRequest, BookingRecord, BookingStatus
from booking_agent.booking.service import BookingService
from booking_agent.shared.clock import Clock, SystemClock
from booking_agent.shared.errors import BookingAgentError, ErrorCode
from booking_agent.shared.logging import get_logger
from booking_agent.shared.trace import trace_context
from booking_agent.telemetry.schema import EventStatus, TelemetryEvent, make_agent_event

_logger = get_logger("agent.graph")

MAX_CHECKPOINT_STATE_BYTES = 15 * 1024  # 15 KB ceiling per MVP-10


class AntiLoopDetector:
    """Detects repeated (url, a11y_hash, last_action) cycles and max_steps overflow (MVP-10)."""

    def __init__(self, *, max_steps: int = 12, max_repeats: int = 3) -> None:
        self.max_steps = max_steps
        self.max_repeats = max_repeats

    @staticmethod
    def hash_state(url: str, a11y_snapshot: str, last_action: str) -> str:
        a11y_digest = hashlib.sha256(a11y_snapshot.encode("utf-8")).hexdigest()[:16]
        raw = f"{url.strip().lower()}|{a11y_digest}|{last_action.strip().lower()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def check(self, history: list[str], state_hash: str, step_count: int) -> bool:
        """Return True if loop or step ceiling was exceeded."""
        if step_count >= self.max_steps:
            return True
        if not history:
            return False
        consecutive = 0
        for item in reversed(history):
            if item == state_hash:
                consecutive += 1
            else:
                break
        return consecutive + 1 >= self.max_repeats


class BookingGraphState(TypedDict, total=False):
    """Compact checkpointable AgentState (< 15 KB); stores artifact refs, never raw DOM/images."""

    booking_id: str
    trace_id: str
    raw_request: dict[str, Any]
    normalized_input: dict[str, Any]
    policy_decision: dict[str, Any]
    wait_kind: str | None
    otp_channel: str | None
    hitl_id: str | None
    hitl_reason: str | None
    hitl_approved: bool | None
    hitl_decided_by: str | None
    live_session_kept: bool | None
    live_session_ref: str | None
    execution_metadata: dict[str, Any]
    storage_state: dict[str, Any] | None
    artifact_refs: list[str]
    pending_a11y_ref: str | None
    a11y_hash: str | None
    step_history: list[str]
    step_count: int
    loop_count: int
    requested_tier: int | None
    tier_used: int | None
    confirmation_code: str | None
    status: str
    error_code: str | None
    error_message: str | None
    events: list[dict[str, Any]]


@dataclass(slots=True)
class BookingRunResult:
    booking: BookingRecord
    thread_id: str
    interrupted: bool = False
    hitl_payload: dict[str, Any] | None = None
    tier_used: int | None = None
    state_size_bytes: int = 0
    telemetry_events: list[TelemetryEvent] = field(default_factory=list)


def build_booking_graph(
    *,
    booking_service: BookingService,
    router: MasterRouter,
    hitl_manager: HitlManager,
    policy_config: PolicyConfig | None = None,
    otp_timeout_seconds: int = OTP_MAX_TIMEOUT_SECONDS,
    require_submit_approval: bool = True,
    max_steps: int = 12,
    max_loop_repeats: int = 3,
    clock: Clock | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
):
    """Compile the 6-node LangGraph web booking graph (MVP-10, MVP-12, MVP-15, MVP-17)."""
    active_clock = clock or SystemClock()
    active_policy = policy_config or PolicyConfig()
    bounded_otp_ttl = max(1, min(int(otp_timeout_seconds), OTP_MAX_TIMEOUT_SECONDS))
    loop_detector = AntiLoopDetector(max_steps=max_steps, max_repeats=max_loop_repeats)

    # Ephemeral off-checkpoint buffer for large A11y snapshots so AgentState stays <= 15 KB
    ephemeral_a11y_buffer: dict[str, str] = {}

    async def intake_and_normalize(state: BookingGraphState) -> dict[str, Any]:
        booking_id = state["booking_id"]
        trace_id = state["trace_id"]
        events = list(state.get("events", []))
        started_ms = active_clock.monotonic_ms()
        try:
            normalized = normalize_booking_input(state["raw_request"], clock=active_clock)
            await booking_service.transition_status(
                booking_id,
                BookingStatus.VALIDATED,
                reason="input_normalized",
                actor="agent.intake_and_normalize",
                trace_id=trace_id,
            )
            evt = make_agent_event(
                "intake_and_normalize",
                component="agent.guardrails.layer1",
                booking_id=booking_id,
                trace_id=trace_id,
                duration_ms=max(0.0, active_clock.monotonic_ms() - started_ms),
                site_id=normalized.site_id,
            )
            events.append(evt.model_dump(mode="json"))
            return {
                "normalized_input": normalized.model_dump(mode="json"),
                "status": str(BookingStatus.VALIDATED),
                "step_count": state.get("step_count", 0) + 1,
                "events": events,
            }
        except BookingAgentError as exc:
            await booking_service.transition_status(
                booking_id,
                BookingStatus.FAILED,
                reason="validation_failed",
                actor="agent.intake_and_normalize",
                trace_id=trace_id,
                error_code=str(exc.code),
                error_message=exc.message,
            )
            evt = make_agent_event(
                "input_validation_failed",
                component="agent.guardrails.layer1",
                status=EventStatus.FAILED,
                booking_id=booking_id,
                trace_id=trace_id,
                error_code=str(exc.code),
                error_class=type(exc).__name__,
                message=exc.message,
            )
            events.append(evt.model_dump(mode="json"))
            return {
                "status": str(BookingStatus.FAILED),
                "error_code": str(exc.code),
                "error_message": exc.message,
                "events": events,
            }

    async def acquire_context(state: BookingGraphState) -> dict[str, Any]:
        booking_id = state["booking_id"]
        trace_id = state["trace_id"]
        events = list(state.get("events", []))
        normalized = NormalizedBookingInput.model_validate(state["normalized_input"])
        decision = evaluate_policy(normalized, config=active_policy)

        if not decision.allowed:
            code = str(decision.blocked_code or ErrorCode.POLICY_BLOCKED)
            msg = "; ".join(decision.reasons) or "Blocked by policy guardrail"
            await booking_service.transition_status(
                booking_id,
                BookingStatus.FAILED,
                reason="policy_blocked",
                actor="agent.acquire_context",
                trace_id=trace_id,
                error_code=code,
                error_message=msg,
            )
            evt = make_agent_event(
                "policy_blocked",
                component="agent.guardrails.layer2",
                status=EventStatus.FAILED,
                booking_id=booking_id,
                trace_id=trace_id,
                error_code=code,
                message=msg,
            )
            events.append(evt.model_dump(mode="json"))
            return {
                "policy_decision": decision.model_dump(mode="json"),
                "status": str(BookingStatus.FAILED),
                "error_code": code,
                "error_message": msg,
                "events": events,
            }

        if decision.requires_hitl:
            reason = "; ".join(decision.reasons) or "Policy requires human approval"
            await booking_service.transition_status(
                booking_id,
                BookingStatus.AWAITING_HITL,
                reason=reason,
                actor="agent.acquire_context",
                trace_id=trace_id,
            )
            evt = make_agent_event(
                "policy_hitl_triggered",
                component="agent.guardrails.layer2",
                status=EventStatus.HITL_PAUSED,
                booking_id=booking_id,
                trace_id=trace_id,
                message=reason,
            )
            events.append(evt.model_dump(mode="json"))
            return {
                "policy_decision": decision.model_dump(mode="json"),
                "wait_kind": str(WaitKind.APPROVAL),
                "hitl_reason": reason,
                "status": str(BookingStatus.AWAITING_HITL),
                "step_count": state.get("step_count", 0) + 1,
                "events": events,
            }

        return {
            "policy_decision": decision.model_dump(mode="json"),
            "step_count": state.get("step_count", 0) + 1,
            "events": events,
        }

    async def route_strategy(state: BookingGraphState) -> dict[str, Any]:
        booking_id = state["booking_id"]
        trace_id = state["trace_id"]
        events = list(state.get("events", []))
        artifacts = list(state.get("artifact_refs", []))
        step_history = list(state.get("step_history", []))
        step_count = state.get("step_count", 0) + 1
        loop_count = state.get("loop_count", 0)

        if step_count >= loop_detector.max_steps:
            return {
                "status": str(BookingStatus.FAILED),
                "error_code": str(ErrorCode.LOOP_DETECTED),
                "error_message": f"Step limit ({loop_detector.max_steps}) exceeded",
                "step_count": step_count,
                "loop_count": loop_count + 1,
                "events": events,
            }

        normalized = NormalizedBookingInput.model_validate(state["normalized_input"])
        await booking_service.transition_status(
            booking_id,
            BookingStatus.RUNNING,
            reason="routing_started",
            actor="agent.route_strategy",
            trace_id=trace_id,
        )

        result = await router.execute(
            booking_id=booking_id,
            trace_id=trace_id,
            booking_input=normalized,
            requested_tier=state.get("requested_tier"),
            storage_state=state.get("storage_state"),
            execution_metadata=state.get("execution_metadata"),
        )
        tier_used = int(result.tier_used) if result.tier_used is not None else None
        if result.artifact_id and result.artifact_id not in artifacts:
            artifacts.append(result.artifact_id)

        updated_storage = result.latest_storage_state or state.get("storage_state")

        if result.success:
            evt = make_agent_event(
                "booking_executed",
                component="agent.route_strategy",
                booking_id=booking_id,
                trace_id=trace_id,
                tier=tier_used,
                artifact_id=result.artifact_id,
                token_count=result.token_usage,
                loop_count=loop_count,
                confirmation_code=result.confirmation_code,
                routing_reasons=result.routing_reasons,
            )
            events.append(evt.model_dump(mode="json"))
            return {
                "status": str(BookingStatus.CONFIRMED),
                "tier_used": tier_used,
                "confirmation_code": result.confirmation_code,
                "artifact_refs": artifacts,
                "storage_state": updated_storage,
                "step_count": step_count,
                "events": events,
            }

        if result.status_code == TaskStatusCode.NEED_REASONING:
            snapshot = result.a11y_tree_snapshot or ""
            ref_id = result.artifact_id or f"a11y_{booking_id}_{step_count}"
            if len(ephemeral_a11y_buffer) >= 64:
                oldest_key = next(iter(ephemeral_a11y_buffer))
                ephemeral_a11y_buffer.pop(oldest_key, None)
            ephemeral_a11y_buffer[ref_id] = snapshot
            a11y_hash = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()[:16]
            state_hash = loop_detector.hash_state(
                normalized.site_id,
                snapshot,
                "need_reasoning",
            )
            is_loop = loop_detector.check(step_history, state_hash, step_count)
            step_history.append(state_hash)

            if is_loop:
                ephemeral_a11y_buffer.pop(ref_id, None)
                evt = make_agent_event(
                    "anti_loop_triggered",
                    component="agent.route_strategy",
                    status=EventStatus.FAILED,
                    booking_id=booking_id,
                    trace_id=trace_id,
                    tier=tier_used,
                    loop_count=loop_count + 1,
                    error_code=str(ErrorCode.LOOP_DETECTED),
                )
                events.append(evt.model_dump(mode="json"))
                return {
                    "status": str(BookingStatus.FAILED),
                    "tier_used": tier_used,
                    "error_code": str(ErrorCode.LOOP_DETECTED),
                    "error_message": "Anti-Loop Detector halted repeated browser state cycle",
                    "step_history": step_history,
                    "step_count": step_count,
                    "loop_count": loop_count + 1,
                    "events": events,
                }

            evt = make_agent_event(
                "reasoning_requested",
                component="agent.route_strategy",
                booking_id=booking_id,
                trace_id=trace_id,
                tier=tier_used,
                artifact_id=ref_id,
                token_count=result.token_usage,
            )
            events.append(evt.model_dump(mode="json"))
            return {
                "status": "needs_parse_guard",
                "tier_used": tier_used,
                "artifact_refs": artifacts if ref_id in artifacts else [*artifacts, ref_id],
                "pending_a11y_ref": ref_id,
                "a11y_hash": a11y_hash,
                "storage_state": updated_storage,
                "step_history": step_history,
                "step_count": step_count,
                "loop_count": loop_count + 1,
                "events": events,
            }

        if result.requires_hitl:
            reason = result.hitl_reason or "Browser execution requested verification"
            is_otp = (
                result.status_code == TaskStatusCode.NEED_OTP
                or result.hitl_metadata.get("wait_type") == "otp"
                or "otp" in reason.lower()
            )
            wait_kind = WaitKind.OTP if is_otp else WaitKind.APPROVAL
            otp_channel = str(result.hitl_metadata.get("otp_channel", "sms"))
            evt = make_agent_event(
                "otp_hibernation_started" if is_otp else "execution_hitl_requested",
                component="agent.route_strategy",
                status=EventStatus.HITL_PAUSED,
                booking_id=booking_id,
                trace_id=trace_id,
                tier=tier_used,
                artifact_id=result.artifact_id,
                message=reason,
                routing_reasons=result.routing_reasons,
            )
            events.append(evt.model_dump(mode="json"))
            return {
                "status": str(BookingStatus.AWAITING_HITL),
                "tier_used": tier_used,
                "wait_kind": str(wait_kind),
                "otp_channel": otp_channel if is_otp else None,
                "hitl_reason": reason,
                "live_session_kept": result.session_kept,
                "live_session_ref": result.hitl_metadata.get("sandbox_session_id"),
                "artifact_refs": artifacts,
                "storage_state": updated_storage,
                "step_count": step_count,
                "events": events,
            }

        err_code = result.error_code or str(ErrorCode.TIER_EXHAUSTED)
        err_msg = result.error_message or "Booking execution failed"
        evt = make_agent_event(
            "booking_execution_failed",
            component="agent.route_strategy",
            status=EventStatus.FAILED,
            booking_id=booking_id,
            trace_id=trace_id,
            tier=tier_used,
            artifact_id=result.artifact_id,
            error_code=err_code,
            error_class=result.error_class,
            message=err_msg,
            routing_reasons=result.routing_reasons,
        )
        events.append(evt.model_dump(mode="json"))
        return {
            "status": str(BookingStatus.FAILED),
            "tier_used": tier_used,
            "artifact_refs": artifacts,
            "storage_state": updated_storage,
            "error_code": err_code,
            "error_message": err_msg,
            "step_count": step_count,
            "events": events,
        }

    async def parse_and_guard(state: BookingGraphState) -> dict[str, Any]:
        """MVP-15 BAML extraction + Data-Control Isolation + MVP-17 Safety Action Gate."""
        booking_id = state["booking_id"]
        trace_id = state["trace_id"]
        events = list(state.get("events", []))
        normalized = NormalizedBookingInput.model_validate(state["normalized_input"])
        ref_id = state.get("pending_a11y_ref") or ""
        a11y_snapshot = ephemeral_a11y_buffer.pop(ref_id, "")

        extracted, decision = parse_and_guard_a11y(a11y_snapshot, normalized)
        if not decision.allowed:
            code = str(decision.blocked_code or ErrorCode.PROMPT_INJECTION_DETECTED)
            msg = "; ".join(decision.reasons) or "Blocked by Layer 2 DOM guard"
            await booking_service.transition_status(
                booking_id,
                BookingStatus.FAILED,
                reason="dom_injection_blocked",
                actor="agent.parse_and_guard",
                trace_id=trace_id,
                error_code=code,
                error_message=msg,
            )
            evt = make_agent_event(
                "dom_injection_blocked",
                component="agent.guardrails.layer2",
                status=EventStatus.FAILED,
                booking_id=booking_id,
                trace_id=trace_id,
                artifact_id=ref_id or None,
                error_code=code,
                message=msg,
            )
            events.append(evt.model_dump(mode="json"))
            return {
                "pending_a11y_ref": None,
                "status": str(BookingStatus.FAILED),
                "error_code": code,
                "error_message": msg,
                "events": events,
            }

        exec_meta = dict(state.get("execution_metadata", {}))
        exec_meta["extracted_form"] = extracted.model_dump(mode="json")
        exec_meta["baml_guarded"] = True

        # MVP-17 Safety Gate: verify deposit limit and final submit approval
        deposit_risk = classify_action_risk(
            ActionType.CONFIRM_DEPOSIT,
            deposit_amount=extracted.deposit_amount,
            allow_deposit_max=normalized.allow_deposit_max,
            require_submit_approval=require_submit_approval,
        )
        submit_risk = classify_action_risk(
            ActionType.FINAL_SUBMIT,
            deposit_amount=extracted.deposit_amount,
            allow_deposit_max=normalized.allow_deposit_max,
            require_submit_approval=require_submit_approval,
        )

        if decision.requires_hitl or deposit_risk.requires_hitl or submit_risk.requires_hitl:
            reason = (
                deposit_risk.reason
                if deposit_risk.requires_hitl
                else ("; ".join(decision.reasons) or submit_risk.reason)
            )
            evt = make_agent_event(
                "safety_gate_triggered",
                component="agent.guardrails.layer3",
                status=EventStatus.HITL_PAUSED,
                booking_id=booking_id,
                trace_id=trace_id,
                artifact_id=ref_id or None,
                message=reason,
            )
            events.append(evt.model_dump(mode="json"))
            return {
                "pending_a11y_ref": None,
                "execution_metadata": exec_meta,
                "wait_kind": str(WaitKind.APPROVAL),
                "hitl_reason": reason,
                "status": str(BookingStatus.AWAITING_HITL),
                "events": events,
            }

        return {
            "pending_a11y_ref": None,
            "execution_metadata": exec_meta,
            "status": str(BookingStatus.RUNNING),
            "events": events,
        }

    async def safety_hitl_gate(state: BookingGraphState) -> dict[str, Any]:
        booking_id = state["booking_id"]
        trace_id = state["trace_id"]
        events = list(state.get("events", []))
        wait_kind = WaitKind(state.get("wait_kind") or WaitKind.APPROVAL)
        otp_channel = state.get("otp_channel") or "sms"
        reason = state.get("hitl_reason") or (
            f"Waiting for {otp_channel.upper()} OTP"
            if wait_kind == WaitKind.OTP
            else "Human approval required"
        )

        await booking_service.transition_status(
            booking_id,
            BookingStatus.AWAITING_HITL,
            reason=reason,
            actor="agent.safety_hitl_gate",
            trace_id=trace_id,
        )

        pending = await hitl_manager.list_pending(booking_id=booking_id)
        if pending:
            hitl_req = pending[0]
        elif wait_kind == WaitKind.OTP:
            hitl_req = await hitl_manager.create_otp_request(
                booking_id=booking_id,
                channel=otp_channel,
                prompt_text=reason,
                ttl_seconds=bounded_otp_ttl,
                trace_id=trace_id,
            )
        else:
            hitl_req = await hitl_manager.create_request(
                booking_id=booking_id,
                reason=reason,
                prompt_text=f"Approve booking {booking_id}: {reason}",
                trace_id=trace_id,
            )

        interrupt_data: dict[str, Any] = {
            "wait_kind": str(wait_kind),
            "hitl_id": hitl_req.hitl_id,
            "booking_id": booking_id,
            "reason": reason,
            "expires_at": hitl_req.expires_at.isoformat(),
        }
        if wait_kind == WaitKind.OTP:
            interrupt_data["otp_channel"] = otp_channel
            interrupt_data["timeout_seconds"] = bounded_otp_ttl
        # MVP-07 handshake payload for Browser Control Live View (D / MVP-27).
        session_kept = bool(state.get("live_session_kept"))
        interrupt_data["liveview"] = {
            "action": "open",
            "booking_id": booking_id,
            "trace_id": trace_id,
            "hitl_id": hitl_req.hitl_id,
            "wait_kind": str(wait_kind),
            "mode": "short_wait" if session_kept else "hibernate",
            "session_ref": state.get("live_session_ref"),
            "resume_on": "otp_submitted" if wait_kind == WaitKind.OTP else "user_approved",
        }

        resume_payload = interrupt(interrupt_data)
        payload = (
            resume_payload
            if isinstance(resume_payload, dict)
            else {"approved": bool(resume_payload)}
        )
        default_actor = "user" if wait_kind == WaitKind.OTP else "operator"
        decided_by = str(payload.get("decided_by", default_actor))
        exec_meta = dict(state.get("execution_metadata", {}))

        if wait_kind == WaitKind.OTP:
            otp_code = payload.get("otp_code")
            if not otp_code or payload.get("approved") is False:
                latest_hitl = await hitl_manager.get_request(hitl_req.hitl_id)
                if latest_hitl.status == HitlStatus.PENDING:
                    await hitl_manager.resolve(
                        hitl_req.hitl_id,
                        decision="rejected",
                        decided_by=decided_by,
                    )
                return {
                    "hitl_id": hitl_req.hitl_id,
                    "hitl_approved": False,
                    "hitl_decided_by": decided_by,
                    "status": str(BookingStatus.CANCELLED),
                    "error_code": str(ErrorCode.HITL_REJECTED),
                    "error_message": "OTP submission cancelled",
                    "events": events,
                }

            try:
                latest_hitl = await hitl_manager.get_request(hitl_req.hitl_id)
                if latest_hitl.status == HitlStatus.PENDING:
                    await hitl_manager.resolve_otp(
                        hitl_req.hitl_id,
                        otp_code=str(otp_code),
                        submitted_by=decided_by,
                    )
                elif latest_hitl.status == HitlStatus.EXPIRED:
                    raise BookingAgentError(
                        "OTP hibernation expired",
                        code=ErrorCode.OTP_TIMEOUT,
                    )
            except BookingAgentError as exc:
                is_timeout = exc.code in (ErrorCode.OTP_TIMEOUT, ErrorCode.HITL_EXPIRED)
                target_status = BookingStatus.EXPIRED if is_timeout else BookingStatus.FAILED
                await booking_service.transition_status(
                    booking_id,
                    target_status,
                    reason="otp_timeout" if is_timeout else "otp_invalid",
                    actor=decided_by,
                    trace_id=trace_id,
                    error_code=str(exc.code),
                    error_message=exc.message,
                )
                evt = make_agent_event(
                    "otp_expired" if is_timeout else "otp_rejected",
                    component="agent.guardrails.layer3",
                    status=EventStatus.FAILED,
                    booking_id=booking_id,
                    trace_id=trace_id,
                    error_code=str(exc.code),
                    message=exc.message,
                )
                events.append(evt.model_dump(mode="json"))
                return {
                    "hitl_id": hitl_req.hitl_id,
                    "hitl_approved": False,
                    "hitl_decided_by": decided_by,
                    "status": str(target_status),
                    "error_code": str(exc.code),
                    "error_message": exc.message,
                    "events": events,
                }

            exec_meta["otp_code"] = str(otp_code).strip()
            exec_meta["otp_verified"] = True
            evt = make_agent_event(
                "otp_resumed",
                component="agent.guardrails.layer3",
                booking_id=booking_id,
                trace_id=trace_id,
                hitl_id=hitl_req.hitl_id,
                otp_channel=otp_channel,
            )
            events.append(evt.model_dump(mode="json"))
            return {
                "hitl_id": hitl_req.hitl_id,
                "hitl_approved": True,
                "hitl_decided_by": decided_by,
                "execution_metadata": exec_meta,
                "events": events,
            }

        approved = bool(payload.get("approved", False))
        try:
            latest_hitl = await hitl_manager.get_request(hitl_req.hitl_id)
            if latest_hitl.status == HitlStatus.PENDING:
                await hitl_manager.resolve(
                    hitl_req.hitl_id,
                    decision="approved" if approved else "rejected",
                    decided_by=decided_by,
                )
            elif latest_hitl.status == HitlStatus.EXPIRED:
                raise BookingAgentError("HITL request expired", code=ErrorCode.HITL_EXPIRED)
        except BookingAgentError as exc:
            await booking_service.transition_status(
                booking_id,
                BookingStatus.EXPIRED,
                reason="hitl_expired",
                actor=decided_by,
                trace_id=trace_id,
                error_code=str(exc.code),
                error_message=exc.message,
            )
            return {
                "hitl_id": hitl_req.hitl_id,
                "hitl_approved": False,
                "hitl_decided_by": decided_by,
                "status": str(BookingStatus.EXPIRED),
                "error_code": str(exc.code),
                "error_message": exc.message,
                "events": events,
            }

        if approved:
            exec_meta["hitl_approved"] = True
            evt = make_agent_event(
                "hitl_approved",
                component="agent.guardrails.layer3",
                booking_id=booking_id,
                trace_id=trace_id,
                hitl_id=hitl_req.hitl_id,
                decided_by=decided_by,
            )
            events.append(evt.model_dump(mode="json"))
            return {
                "hitl_id": hitl_req.hitl_id,
                "hitl_approved": True,
                "hitl_decided_by": decided_by,
                "execution_metadata": exec_meta,
                "events": events,
            }

        await booking_service.transition_status(
            booking_id,
            BookingStatus.CANCELLED,
            reason="hitl_rejected",
            actor=decided_by,
            trace_id=trace_id,
            error_code=str(ErrorCode.HITL_REJECTED),
            error_message="Operator rejected HITL approval request",
        )
        evt = make_agent_event(
            "hitl_rejected",
            component="agent.guardrails.layer3",
            status=EventStatus.FAILED,
            booking_id=booking_id,
            trace_id=trace_id,
            error_code=str(ErrorCode.HITL_REJECTED),
            hitl_id=hitl_req.hitl_id,
            decided_by=decided_by,
        )
        events.append(evt.model_dump(mode="json"))
        return {
            "hitl_id": hitl_req.hitl_id,
            "hitl_approved": False,
            "hitl_decided_by": decided_by,
            "status": str(BookingStatus.CANCELLED),
            "error_code": str(ErrorCode.HITL_REJECTED),
            "error_message": "Operator rejected HITL approval request",
            "events": events,
        }

    async def finalize_and_release(state: BookingGraphState) -> dict[str, Any]:
        booking_id = state["booking_id"]
        trace_id = state["trace_id"]
        events = list(state.get("events", []))

        current = await booking_service.get_booking(booking_id)
        desired_raw = state.get("status", str(BookingStatus.FAILED))
        desired = BookingStatus(desired_raw)

        if current.status not in TERMINAL_STATUSES:
            await booking_service.transition_status(
                booking_id,
                desired,
                reason="graph_finalized",
                actor="agent.finalize_and_release",
                trace_id=trace_id,
                confirmation_code=state.get("confirmation_code"),
                error_code=state.get("error_code"),
                error_message=state.get("error_message"),
            )

        _logger.info(
            "Booking workflow finalized",
            extra={
                "booking_id": booking_id,
                "trace_id": trace_id,
                "status": str(desired),
                "tier_used": state.get("tier_used"),
            },
        )
        return {"events": events}

    def route_after_intake(
        state: BookingGraphState,
    ) -> Literal["acquire_context", "finalize_and_release"]:
        if state.get("status") == str(BookingStatus.FAILED):
            return "finalize_and_release"
        return "acquire_context"

    def route_after_acquire(
        state: BookingGraphState,
    ) -> Literal["safety_hitl_gate", "route_strategy", "finalize_and_release"]:
        status = state.get("status")
        if status == str(BookingStatus.FAILED):
            return "finalize_and_release"
        if status == str(BookingStatus.AWAITING_HITL):
            return "safety_hitl_gate"
        return "route_strategy"

    def route_after_strategy(
        state: BookingGraphState,
    ) -> Literal["parse_and_guard", "safety_hitl_gate", "finalize_and_release"]:
        status = state.get("status")
        if status == "needs_parse_guard":
            return "parse_and_guard"
        if status == str(BookingStatus.AWAITING_HITL):
            return "safety_hitl_gate"
        return "finalize_and_release"

    def route_after_parse(
        state: BookingGraphState,
    ) -> Literal["route_strategy", "safety_hitl_gate", "finalize_and_release"]:
        status = state.get("status")
        if status == str(BookingStatus.FAILED):
            return "finalize_and_release"
        if status == str(BookingStatus.AWAITING_HITL):
            return "safety_hitl_gate"
        return "route_strategy"

    def route_after_hitl(
        state: BookingGraphState,
    ) -> Literal["route_strategy", "finalize_and_release"]:
        if state.get("hitl_approved"):
            return "route_strategy"
        return "finalize_and_release"

    builder = StateGraph(BookingGraphState)
    builder.add_node("intake_and_normalize", intake_and_normalize)
    builder.add_node("acquire_context", acquire_context)
    builder.add_node("route_strategy", route_strategy)
    builder.add_node("parse_and_guard", parse_and_guard)
    builder.add_node("safety_hitl_gate", safety_hitl_gate)
    builder.add_node("finalize_and_release", finalize_and_release)

    builder.add_edge(START, "intake_and_normalize")
    builder.add_conditional_edges("intake_and_normalize", route_after_intake)
    builder.add_conditional_edges("acquire_context", route_after_acquire)
    builder.add_conditional_edges("route_strategy", route_after_strategy)
    builder.add_conditional_edges("parse_and_guard", route_after_parse)
    builder.add_conditional_edges("safety_hitl_gate", route_after_hitl)
    builder.add_edge("finalize_and_release", END)

    return builder.compile(checkpointer=checkpointer)


class BookingAgentRunner:
    """High-level async runner executing and resuming web bookings via LangGraph."""

    def __init__(
        self,
        *,
        booking_service: BookingService,
        router: MasterRouter,
        hitl_manager: HitlManager,
        policy_config: PolicyConfig | None = None,
        otp_timeout_seconds: int = OTP_MAX_TIMEOUT_SECONDS,
        require_submit_approval: bool = True,
        max_steps: int = 12,
        max_loop_repeats: int = 3,
        clock: Clock | None = None,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
        liveview: LiveViewPort | None = None,
    ) -> None:
        self._booking_service = booking_service
        self._router = router
        self._checkpointer = checkpointer
        self._liveview = liveview
        self._graph = build_booking_graph(
            booking_service=booking_service,
            router=router,
            hitl_manager=hitl_manager,
            policy_config=policy_config,
            otp_timeout_seconds=otp_timeout_seconds,
            require_submit_approval=require_submit_approval,
            max_steps=max_steps,
            max_loop_repeats=max_loop_repeats,
            clock=clock,
            checkpointer=checkpointer,
        )

    async def run_booking(
        self,
        request: BookingCreateRequest,
        *,
        requested_tier: int | None = None,
        trace_id: str | None = None,
    ) -> BookingRunResult:
        """Create a booking record and run the LangGraph workflow."""
        booking, is_replay = await self._booking_service.create_booking(request, trace_id=trace_id)
        thread_id = booking.booking_id
        if is_replay:
            return BookingRunResult(booking=booking, thread_id=thread_id)

        return await self.run_existing_booking(
            booking.booking_id,
            request,
            requested_tier=requested_tier,
        )

    async def run_existing_booking(
        self,
        booking_id: str,
        request: BookingCreateRequest,
        *,
        requested_tier: int | None = None,
    ) -> BookingRunResult:
        """Execute the LangGraph workflow for an already-created or queued booking."""
        booking = await self._booking_service.get_booking(booking_id)
        thread_id = booking.booking_id
        with trace_context(booking.trace_id, booking_id=booking.booking_id):
            config = {"configurable": {"thread_id": thread_id}}
            output = await self._graph.ainvoke(
                {
                    "booking_id": booking.booking_id,
                    "trace_id": booking.trace_id,
                    "raw_request": request.model_dump(mode="json"),
                    "requested_tier": requested_tier,
                    "execution_metadata": {},
                    "artifact_refs": [],
                    "step_history": [],
                    "step_count": 0,
                    "loop_count": 0,
                    "events": [],
                },
                config=config,
            )
            return await self._to_run_result(booking.booking_id, thread_id, output)

    async def resume_after_hitl(
        self,
        thread_id: str,
        *,
        approved: bool,
        decided_by: str = "operator",
    ) -> BookingRunResult:
        """Resume an interrupted booking workflow after operator HITL decision."""
        booking = await self._booking_service.get_booking(thread_id)
        with trace_context(booking.trace_id, booking_id=booking.booking_id):
            config = {"configurable": {"thread_id": thread_id}}
            output = await self._graph.ainvoke(
                Command(resume={"approved": approved, "decided_by": decided_by}),
                config=config,
            )
            return await self._to_run_result(booking.booking_id, thread_id, output)

    async def resume_with_otp(
        self,
        thread_id: str,
        *,
        otp_code: str,
        submitted_by: str = "user",
    ) -> BookingRunResult:
        """Resume a hibernated booking workflow by supplying a web OTP code."""
        booking = await self._booking_service.get_booking(thread_id)
        with trace_context(booking.trace_id, booking_id=booking.booking_id):
            config = {"configurable": {"thread_id": thread_id}}
            output = await self._graph.ainvoke(
                Command(
                    resume={
                        "wait_kind": str(WaitKind.OTP),
                        "otp_code": otp_code,
                        "approved": True,
                        "decided_by": submitted_by,
                    }
                ),
                config=config,
            )
            return await self._to_run_result(booking.booking_id, thread_id, output)

    async def delete_thread(self, thread_id: str) -> bool:
        """Delete every checkpoint of a LangGraph thread (used when a booking is cancelled)."""
        if self._checkpointer is None:
            return False
        deleter = getattr(self._checkpointer, "adelete_thread", None)
        if deleter is None:
            return False
        await deleter(thread_id)
        return True

    async def has_checkpoint(self, thread_id: str) -> bool:
        if self._checkpointer is None:
            return False
        tup = await self._checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})
        return tup is not None

    async def release_resources(self, booking_id: str) -> None:
        """Release any held router resources (sandbox/lease) and close Live View for a booking."""
        await self._router.release_booking_resources(booking_id)
        if self._liveview is not None:
            await self._liveview.close(booking_id)

    async def cancel_booking(
        self,
        booking_id: str,
        *,
        reason: str = "user_cancelled",
        actor: str = "user",
        extra_cleanup: Any = None,
    ) -> BookingRecord:
        """MVP-39: cancel a booking and release lease, sandbox, Live View and checkpoints."""

        async def _cleanup(bid: str) -> None:
            await self.release_resources(bid)
            await self.delete_thread(bid)
            if extra_cleanup is not None:
                await extra_cleanup(bid)

        return await self._booking_service.cancel_booking(
            booking_id,
            reason=reason,
            actor=actor,
            on_cancel=_cleanup,
        )

    async def _to_run_result(
        self,
        booking_id: str,
        thread_id: str,
        output: dict[str, Any],
    ) -> BookingRunResult:
        booking = await self._booking_service.get_booking(booking_id)
        interrupts = output.get("__interrupt__")
        interrupted = bool(interrupts)
        hitl_payload: dict[str, Any] | None = None
        if interrupts:
            first = interrupts[0]
            raw_payload = first.value if hasattr(first, "value") else first
            hitl_payload = dict(raw_payload) if isinstance(raw_payload, dict) else raw_payload
            if self._liveview is not None and isinstance(hitl_payload, dict):
                lv_req = dict(hitl_payload.get("liveview") or {})
                lv_req["url"] = await self._liveview.request_open(booking_id, lv_req)
                hitl_payload["liveview"] = lv_req
        elif self._liveview is not None:
            await self._liveview.close(booking_id)
        events = [TelemetryEvent.model_validate(e) for e in output.get("events", [])]
        state_bytes = len(json.dumps(output, default=str, ensure_ascii=False).encode("utf-8"))
        return BookingRunResult(
            booking=booking,
            thread_id=thread_id,
            interrupted=interrupted,
            hitl_payload=hitl_payload,
            tier_used=output.get("tier_used"),
            state_size_bytes=state_bytes,
            telemetry_events=events,
        )
