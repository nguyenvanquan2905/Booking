"""Unit tests for TierRegistry, ControlPlaneClient, MasterRouter, Queue & MVP-29 Health."""

from __future__ import annotations

from datetime import datetime, timedelta

from booking_agent.agent.guardrails.layer1_normalize import normalize_booking_input
from booking_agent.agent.queue import DurableQueue, TaskStatus
from booking_agent.agent.registry import (
    ExecutionTier,
    NoopLearningHook,
    ProfileHealthMonitor,
    ProfileHealthStatus,
    TierRegistry,
)
from booking_agent.agent.router import (
    BrowserExecutionRequest,
    BrowserExecutionResult,
    ContextLease,
    ControlPlaneClient,
    MasterRouter,
    SandboxSession,
    TaskSpec,
    TaskStatusCode,
)
from booking_agent.booking.models import BookingCreateRequest
from booking_agent.shared.clock import FakeClock
from booking_agent.shared.db import DatabasePool
from booking_agent.shared.pii import PiiCipher


class FakeBrowserControl:
    def __init__(self, outcomes: dict[int, BrowserExecutionResult]) -> None:
        self.outcomes = outcomes
        self.calls: list[int] = []

    async def supports_tier(self, site_id: str, tier: int) -> bool:
        return tier in self.outcomes

    async def execute_booking(self, request: BrowserExecutionRequest) -> BrowserExecutionResult:
        self.calls.append(request.tier)
        return self.outcomes[request.tier]


class FakeSandbox:
    def __init__(self) -> None:
        self.acquired: list[str] = []
        self.released: list[str] = []

    async def acquire(self, booking_id: str) -> SandboxSession:
        sid = f"sb_{booking_id}"
        self.acquired.append(sid)
        return SandboxSession(session_id=sid, booking_id=booking_id)

    async def release(self, session_id: str) -> None:
        self.released.append(session_id)

    async def is_healthy(self, session_id: str) -> bool:
        return True


class FakeProfile:
    def __init__(self) -> None:
        self.acquired: list[str] = []
        self.released: list[str] = []
        self.written_back: dict[str, dict[str, object]] = {}

    async def acquire_lease(self, site_id: str, booking_id: str) -> ContextLease:
        lid = f"lease_{booking_id}"
        self.acquired.append(lid)
        return ContextLease(lease_id=lid, profile_id="prof_1", site_id=site_id)

    async def release_lease(self, lease_id: str) -> None:
        self.released.append(lease_id)

    async def heartbeat(self, lease_id: str) -> bool:
        return True

    async def write_back(self, lease_id: str, storage_state: dict[str, object]) -> None:
        self.written_back[lease_id] = dict(storage_state)


async def test_tier_registry_circuit_breaker_and_auto_demote(
    tier_registry: TierRegistry,
    fake_clock: FakeClock,
) -> None:
    await tier_registry.register_site(
        "pasgo",
        preferred_tier=ExecutionTier.TIER_1_API_REPLAY,
        fallback_tiers=[ExecutionTier.TIER_2_PLAYWRIGHT, ExecutionTier.TIER_4_VISION],
    )
    assert await tier_registry.resolve_candidate_tiers("pasgo") == [
        ExecutionTier.TIER_1_API_REPLAY,
        ExecutionTier.TIER_2_PLAYWRIGHT,
        ExecutionTier.TIER_4_VISION,
    ]

    for _ in range(3):
        await tier_registry.record_failure(
            "pasgo",
            ExecutionTier.TIER_1_API_REPLAY,
            failure_threshold=3,
            cooldown_seconds=60,
        )

    # Circuit is open and Tier 1 is flagged as auto-demoted
    cfg = await tier_registry.get_site_config("pasgo")
    assert cfg.needs_review is True
    assert 1 in cfg.demoted_tiers
    assert await tier_registry.resolve_candidate_tiers("pasgo") == [
        ExecutionTier.TIER_2_PLAYWRIGHT,
        ExecutionTier.TIER_4_VISION,
    ]

    # After cooldown, Tier 2 goes first while demoted Tier 1 moves to back
    fake_clock.advance(61)
    assert await tier_registry.resolve_candidate_tiers("pasgo") == [
        ExecutionTier.TIER_2_PLAYWRIGHT,
        ExecutionTier.TIER_4_VISION,
        ExecutionTier.TIER_1_API_REPLAY,
    ]


async def test_control_plane_client_router_and_learning_seam(
    tier_registry: TierRegistry,
    fake_clock: FakeClock,
) -> None:
    browser = FakeBrowserControl(
        {
            1: BrowserExecutionResult(
                success=False,
                tier_used=1,
                retryable=True,
                error_code="API_CHANGED",
                error_message="Endpoint returned 404",
            ),
            2: BrowserExecutionResult(
                success=True,
                tier_used=2,
                confirmation_code="OK-T2-777",
                artifact_id="art_t2_777",
                latest_storage_state={"cookies": [{"name": "sid", "value": "xyz"}]},
            ),
        }
    )
    # Direct MVP-06 RPC check
    cp = ControlPlaneClient(browser)
    rpc_res = await cp.execute_tier(
        2,
        TaskSpec(
            request_id="bk_cp",
            trace_id="tr_cp",
            site_id="pasgo",
            restaurant_name="Test",
            party_size=2,
            booking_time_iso=fake_clock.utc_now_iso(),
            customer_name="User",
            customer_phone="+84901234567",
        ),
        "sb_cp",
    )
    assert rpc_res.status_code == TaskStatusCode.SUCCESS
    assert rpc_res.confirmation_code == "OK-T2-777"

    sandbox = FakeSandbox()
    profile = FakeProfile()
    hook = NoopLearningHook()
    router = MasterRouter(
        tier_registry,
        browser,
        sandbox=sandbox,
        profile=profile,
        learning_hook=hook,
        clock=fake_clock,
    )

    norm = normalize_booking_input(
        BookingCreateRequest(
            site_id="pasgo",
            restaurant_name="Quan An Ngon",
            customer_name="Hoang E",
            customer_phone="0901234567",
            party_size=3,
            booking_time=fake_clock.utc_now() + timedelta(hours=5),
        ),
        clock=fake_clock,
    )
    result = await router.execute(booking_id="bk_r1", trace_id="tr_r1", booking_input=norm)
    assert result.success
    assert result.tier_used == ExecutionTier.TIER_2_PLAYWRIGHT
    assert any("thứ tự thử" in r for r in result.routing_reasons)
    assert any("tier 1: FALLBACK_FAILED" in r for r in result.routing_reasons)
    assert any("tier 2: SUCCESS" in r for r in result.routing_reasons)
    assert hook.called_artifacts == ["art_t2_777"]
    assert profile.written_back["lease_bk_r1"] == {"cookies": [{"name": "sid", "value": "xyz"}]}
    assert sandbox.released == ["sb_bk_r1"]
    assert profile.released == ["lease_bk_r1"]


async def test_short_wait_session_reuse_and_mvp39_cancel_releases_all(
    tmp_path,
    tmp_db: DatabasePool,
    booking_service,
    tier_registry: TierRegistry,
    hitl_manager,
    durable_queue: DurableQueue,
    fake_clock: FakeClock,
) -> None:
    from booking_agent.agent.checkpointer import create_checkpointer
    from booking_agent.agent.graph import BookingAgentRunner
    from booking_agent.agent.queue import DurableBookingWrapper

    otp_browser = FakeBrowserControl(
        {
            1: BrowserExecutionResult(
                success=False,
                tier_used=1,
                status_code=TaskStatusCode.NEED_OTP,
                requires_hitl=True,
                hitl_reason="Short-wait OTP on same page",
                metadata={"wait_type": "otp", "otp_channel": "sms"},
            ),
        }
    )
    sandbox = FakeSandbox()
    profile = FakeProfile()
    router = MasterRouter(
        tier_registry,
        otp_browser,
        sandbox=sandbox,
        profile=profile,
        keep_session_on_hitl=True,
        clock=fake_clock,
    )

    async with create_checkpointer(tmp_path / "cancel_ckpt.db") as checkpointer:
        runner = BookingAgentRunner(
            booking_service=booking_service,
            router=router,
            hitl_manager=hitl_manager,
            clock=fake_clock,
            checkpointer=checkpointer,
        )
        wrapper = DurableBookingWrapper(
            queue=durable_queue,
            booking_service=booking_service,
            hitl_manager=hitl_manager,
            runner=runner,
            clock=fake_clock,
        )
        req = BookingCreateRequest(
            site_id="pasgo",
            restaurant_name="Quan Ngon",
            customer_name="Le Cancel",
            customer_phone="0905556666",
            party_size=2,
            booking_time=fake_clock.utc_now() + timedelta(hours=4),
        )
        booking_id, _ = await wrapper.start_task(req)
        paused = await wrapper.process_next("worker-cancel")
        assert paused is not None and paused.interrupted
        # Short-wait keeps sandbox & lease alive instead of releasing
        assert router.active_bookings() == [booking_id]
        assert sandbox.released == []
        assert profile.released == []
        assert await runner.has_checkpoint(booking_id) is True

        # Cancel booking -> releases sandbox, profile lease, pending HITL, wakeups & checkpoints
        cancelled = await wrapper.cancel_booking(booking_id, reason="guest_changed_mind")
        assert str(cancelled.status) == "cancelled"
        assert router.active_bookings() == []
        assert sandbox.released == [f"sb_{booking_id}"]
        assert profile.released == [f"lease_{booking_id}"]
        assert await hitl_manager.list_pending(booking_id=booking_id) == []
        assert await runner.has_checkpoint(booking_id) is False


async def test_durable_queue_priority_retry_and_lease_reclaim(
    durable_queue: DurableQueue,
    fake_clock: FakeClock,
) -> None:
    t_low = await durable_queue.enqueue(
        booking_id="bk_low",
        site_id="pasgo",
        payload={"step": "low"},
        priority=1,
        max_attempts=2,
    )
    t_high = await durable_queue.enqueue(
        booking_id="bk_high",
        site_id="pasgo",
        payload={"step": "high"},
        priority=10,
        max_attempts=2,
    )

    claimed1 = await durable_queue.claim_next("worker-1", lease_seconds=30)
    assert claimed1 is not None
    assert claimed1.task_id == t_high.task_id
    assert claimed1.claimed_by == "worker-1"
    assert claimed1.attempts == 1
    assert claimed1.status == TaskStatus.LEASED

    await durable_queue.complete(claimed1.task_id, {"ok": True})
    done = await durable_queue.get_task(t_high.task_id)
    assert done is not None and done.status == TaskStatus.COMPLETED

    claimed2 = await durable_queue.claim_next("worker-1", lease_seconds=30)
    assert claimed2 is not None and claimed2.task_id == t_low.task_id
    requeued = await durable_queue.fail(claimed2.task_id, error_code="TIMEOUT", retry_delay_s=10.0)
    assert requeued.status == TaskStatus.PENDING
    assert await durable_queue.claim_next("worker-2", lease_seconds=30) is None

    fake_clock.advance(11.0)
    claimed3 = await durable_queue.claim_next("worker-2", lease_seconds=30)
    assert claimed3 is not None and claimed3.attempts == 2
    dead = await durable_queue.fail(claimed3.task_id, error_code="TIMEOUT", retry_delay_s=10.0)
    assert dead.status == TaskStatus.DEAD_LETTER


async def test_profile_health_token_rotation_and_checkpoint_quarantine(
    tmp_db: DatabasePool,
    pii_cipher: PiiCipher,
    fake_clock: FakeClock,
) -> None:
    monitor = ProfileHealthMonitor(tmp_db, pii_cipher, clock=fake_clock)

    await monitor.register_tokens(
        profile_id="web_prof_1",
        site_id="pasgo",
        access_token="acc_old_1",
        refresh_token="ref_1",
        expires_at=fake_clock.utc_now() + timedelta(minutes=2),
    )
    await monitor.register_tokens(
        profile_id="web_prof_fail",
        site_id="white_place",
        access_token="acc_old_2",
        refresh_token="ref_bad",
        expires_at=fake_clock.utc_now() + timedelta(minutes=2),
    )

    class MockRefresher:
        async def refresh(
            self, profile_id: str, refresh_token: str
        ) -> tuple[str, str | None, datetime]:
            if profile_id == "web_prof_fail":
                raise RuntimeError("refresh token revoked")
            return (
                "acc_new_1",
                "ref_new_1",
                fake_clock.utc_now() + timedelta(hours=2),
            )

    refreshed, degraded = await monitor.rotate_expiring_tokens(
        MockRefresher(),
        refresh_window_seconds=300,
    )
    assert refreshed == ["web_prof_1"]
    assert degraded == ["web_prof_fail"]
    assert await monitor.get_decrypted_access_token("web_prof_1") == "acc_new_1"
    assert await monitor.is_eligible("web_prof_1") is True
    assert await monitor.is_eligible("web_prof_fail") is False

    # Checkpoint detected -> flagged & excluded from pool
    rec = await monitor.record_session_outcome(
        profile_id="web_prof_1",
        site_id="pasgo",
        success=False,
        checkpoint_detected=True,
        error="account checkpoint",
    )
    assert rec.checkpoint_flagged is True
    assert rec.status == ProfileHealthStatus.CHECKPOINTED
    assert await monitor.is_eligible("web_prof_1") is False
