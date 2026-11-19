"""Unit tests for TierRegistry manual seeding, circuit breaker, and auto-demote (MVP-84/13)."""

from __future__ import annotations

from booking_agent.agent.registry import ExecutionTier, NoopLearningHook, TierRegistry
from booking_agent.shared.clock import FakeClock


async def test_registry_manual_seed_and_auto_demote(
    tier_registry: TierRegistry,
    fake_clock: FakeClock,
) -> None:
    cfg = await tier_registry.register_site(
        "saigon_princess",
        preferred_tier=ExecutionTier.TIER_2_PLAYWRIGHT,
        fallback_tiers=[ExecutionTier.TIER_3_STAGEHAND, ExecutionTier.TIER_4_VISION],
    )
    assert cfg.preferred_tier == ExecutionTier.TIER_2_PLAYWRIGHT
    assert await tier_registry.resolve_candidate_tiers("saigon_princess") == [
        ExecutionTier.TIER_2_PLAYWRIGHT,
        ExecutionTier.TIER_3_STAGEHAND,
        ExecutionTier.TIER_4_VISION,
    ]

    for _ in range(3):
        await tier_registry.record_failure(
            "saigon_princess",
            ExecutionTier.TIER_2_PLAYWRIGHT,
            failure_threshold=3,
            cooldown_seconds=30,
        )

    after_fail = await tier_registry.get_site_config("saigon_princess")
    assert after_fail.needs_review is True
    assert 2 in after_fail.demoted_tiers

    # Recovery resets failure count and clears demotion
    recovered = await tier_registry.record_success(
        "saigon_princess",
        ExecutionTier.TIER_2_PLAYWRIGHT,
    )
    assert recovered.needs_review is False
    assert recovered.demoted_tiers == []

    hook = NoopLearningHook()
    await hook.on_task_success("art_seed_1")
    assert hook.called_artifacts == ["art_seed_1"]
