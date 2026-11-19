"""TierRegistry, auto-demote, learning seam & ProfileHealthMonitor (MVP-04/13/29/84)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from enum import IntEnum, StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from booking_agent.shared.clock import Clock, SystemClock
from booking_agent.shared.db import DatabasePool
from booking_agent.shared.pii import PiiCipher


class ExecutionTier(IntEnum):
    """4 execution tiers ordered from cheapest/fastest to most general."""

    TIER_1_API_REPLAY = 1
    TIER_2_PLAYWRIGHT = 2
    TIER_3_STAGEHAND = 3
    TIER_4_VISION = 4


DEFAULT_TIER_ORDER: tuple[int, ...] = (
    int(ExecutionTier.TIER_1_API_REPLAY),
    int(ExecutionTier.TIER_2_PLAYWRIGHT),
    int(ExecutionTier.TIER_3_STAGEHAND),
    int(ExecutionTier.TIER_4_VISION),
)


@runtime_checkable
class LearningHookPort(Protocol):
    """MVP-04 Seam 3: adapter hook invoked on task success (no-op in MVP)."""

    async def on_task_success(self, artifact_id: str | None) -> None: ...


class NoopLearningHook:
    """Default no-op self-learning seam implementation (MVP-04)."""

    def __init__(self) -> None:
        self.called_artifacts: list[str | None] = []

    async def on_task_success(self, artifact_id: str | None) -> None:
        self.called_artifacts.append(artifact_id)


class SiteTierConfig(BaseModel):
    site_id: str
    preferred_tier: ExecutionTier = ExecutionTier.TIER_1_API_REPLAY
    fallback_tiers: list[ExecutionTier] = Field(
        default_factory=lambda: [
            ExecutionTier.TIER_2_PLAYWRIGHT,
            ExecutionTier.TIER_3_STAGEHAND,
            ExecutionTier.TIER_4_VISION,
        ]
    )
    enabled: bool = True
    circuit_open_until: dict[int, datetime] = Field(default_factory=dict)
    failure_counts: dict[int, int] = Field(default_factory=dict)
    demoted_tiers: list[int] = Field(default_factory=list)
    needs_review: bool = False


class TierRegistry:
    """Persists per-site routing preferences, circuit breakers & auto-demote flags."""

    def __init__(self, db: DatabasePool, *, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    @staticmethod
    def _row_to_config(row: object) -> SiteTierConfig:
        fallback_raw: list[int] = json.loads(row["fallback_tiers_json"])  # type: ignore[index]
        circuit_raw: dict[str, str] = json.loads(row["circuit_open_json"])  # type: ignore[index]
        failures_raw: dict[str, int] = json.loads(row["failure_counts_json"])  # type: ignore[index]
        demoted_raw: list[int] = json.loads(row["demoted_tiers_json"])  # type: ignore[index]
        return SiteTierConfig(
            site_id=row["site_id"],  # type: ignore[index]
            preferred_tier=ExecutionTier(int(row["preferred_tier"])),  # type: ignore[index]
            fallback_tiers=[ExecutionTier(t) for t in fallback_raw],
            enabled=bool(row["enabled"]),  # type: ignore[index]
            circuit_open_until={
                int(k): datetime.fromisoformat(v) for k, v in circuit_raw.items()
            },
            failure_counts={int(k): int(v) for k, v in failures_raw.items()},
            demoted_tiers=[int(t) for t in demoted_raw],
            needs_review=bool(row["needs_review"]),  # type: ignore[index]
        )

    async def register_site(
        self,
        site_id: str,
        *,
        preferred_tier: ExecutionTier | int = ExecutionTier.TIER_1_API_REPLAY,
        fallback_tiers: tuple[ExecutionTier | int, ...] | list[ExecutionTier | int] | None = None,
        enabled: bool = True,
    ) -> SiteTierConfig:
        """Manually seed or update routing tiers for a site (MVP-04 seam 2)."""
        site_key = site_id.strip().lower()
        pref = ExecutionTier(int(preferred_tier))
        if fallback_tiers is None:
            fallbacks = [ExecutionTier(t) for t in DEFAULT_TIER_ORDER if t != int(pref)]
        else:
            fallbacks = [ExecutionTier(int(t)) for t in fallback_tiers if int(t) != int(pref)]

        now_iso = self._clock.utc_now_iso()
        async with self._db.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO agent_tier_registry (
                    site_id, preferred_tier, fallback_tiers_json,
                    enabled, circuit_open_json, failure_counts_json,
                    demoted_tiers_json, needs_review, updated_at
                ) VALUES (?, ?, ?, ?, '{}', '{}', '[]', 0, ?)
                ON CONFLICT(site_id) DO UPDATE SET
                    preferred_tier = excluded.preferred_tier,
                    fallback_tiers_json = excluded.fallback_tiers_json,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (
                    site_key,
                    int(pref),
                    json.dumps([int(t) for t in fallbacks]),
                    1 if enabled else 0,
                    now_iso,
                ),
            )
            cursor = await conn.execute(
                "SELECT * FROM agent_tier_registry WHERE site_id = ?",
                (site_key,),
            )
            row = await cursor.fetchone()
        return self._row_to_config(row)

    async def get_site_config(self, site_id: str) -> SiteTierConfig:
        site_key = site_id.strip().lower()
        async with self._db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM agent_tier_registry WHERE site_id = ?",
                (site_key,),
            )
            row = await cursor.fetchone()
        if row is None:
            return SiteTierConfig(site_id=site_key)
        return self._row_to_config(row)

    async def resolve_candidate_tiers(
        self,
        site_id: str,
        *,
        requested_tier: ExecutionTier | int | None = None,
    ) -> list[ExecutionTier]:
        """Return ordered candidate tiers excluding open-circuit & auto-demoted tiers."""
        cfg = await self.get_site_config(site_id)
        if not cfg.enabled:
            return []

        if requested_tier is not None:
            ordered = [ExecutionTier(int(requested_tier))]
        else:
            ordered = [cfg.preferred_tier]
            for tier in cfg.fallback_tiers:
                if tier not in ordered:
                    ordered.append(tier)
            non_demoted = [t for t in ordered if int(t) not in cfg.demoted_tiers]
            demoted = [t for t in ordered if int(t) in cfg.demoted_tiers]
            ordered = non_demoted + demoted

        now = self._clock.utc_now()
        available: list[ExecutionTier] = []
        for tier in ordered:
            open_until = cfg.circuit_open_until.get(int(tier))
            if open_until is not None and open_until > now:
                continue
            available.append(tier)
        return available

    async def explain_routing(
        self,
        site_id: str,
        *,
        requested_tier: ExecutionTier | int | None = None,
    ) -> list[str]:
        """Return human-readable reasons for the tier order chosen for a site (MVP-13 AC)."""
        site_key = site_id.strip().lower()
        async with self._db.connection() as conn:
            cursor = await conn.execute(
                "SELECT 1 FROM agent_tier_registry WHERE site_id = ?",
                (site_key,),
            )
            registered = await cursor.fetchone() is not None
        cfg = await self.get_site_config(site_key)
        if not cfg.enabled:
            return [f"site '{site_key}' bị tắt trong registry -> không có cấp nào"]
        if requested_tier is not None:
            return [f"tier {int(requested_tier)}: được chỉ định tường minh (requested_tier)"]

        source = (
            "registry đã seed"
            if registered
            else "site chưa có trong registry -> thác đổ mặc định 1→4, lọc theo capability D"
        )
        reasons = [f"site '{site_key}': {source}"]
        ordered = [cfg.preferred_tier] + [t for t in cfg.fallback_tiers if t != cfg.preferred_tier]
        now = self._clock.utc_now()
        for tier in ordered:
            role = "ưu tiên (preferred)" if tier == cfg.preferred_tier else "dự phòng (fallback)"
            notes: list[str] = []
            if int(tier) in cfg.demoted_tiers:
                notes.append(
                    f"auto-demote sau {cfg.failure_counts.get(int(tier), 0)} lỗi liên tiếp"
                    " -> đẩy xuống cuối"
                )
            open_until = cfg.circuit_open_until.get(int(tier))
            if open_until is not None and open_until > now:
                notes.append(f"circuit mở tới {open_until.isoformat()} -> loại")
            suffix = f"; {'; '.join(notes)}" if notes else ""
            reasons.append(f"tier {int(tier)}: {role}{suffix}")
        return reasons

    async def _get_site_config_on_conn(
        self,
        conn: object,
        site_key: str,
    ) -> SiteTierConfig:
        cursor = await conn.execute(  # type: ignore[attr-defined]
            "SELECT * FROM agent_tier_registry WHERE site_id = ?",
            (site_key,),
        )
        row = await cursor.fetchone()
        if row is None:
            return SiteTierConfig(site_id=site_key)
        return self._row_to_config(row)

    async def record_failure(
        self,
        site_id: str,
        tier: ExecutionTier | int,
        *,
        failure_threshold: int = 3,
        cooldown_seconds: int = 120,
    ) -> SiteTierConfig:
        site_key = site_id.strip().lower()
        tier_num = int(tier)
        now = self._clock.utc_now()

        async with self._db.transaction() as conn:
            cfg = await self._get_site_config_on_conn(conn, site_key)
            failures = dict(cfg.failure_counts)
            circuits = dict(cfg.circuit_open_until)
            demoted = set(cfg.demoted_tiers)
            needs_review = cfg.needs_review

            new_count = failures.get(tier_num, 0) + 1
            failures[tier_num] = new_count
            if new_count >= failure_threshold:
                circuits[tier_num] = now + timedelta(seconds=cooldown_seconds)
                if tier_num in (
                    int(ExecutionTier.TIER_1_API_REPLAY),
                    int(ExecutionTier.TIER_2_PLAYWRIGHT),
                ):
                    demoted.add(tier_num)
                    needs_review = True

            await self._persist_health_on_conn(
                conn,
                site_key,
                cfg,
                failures,
                circuits,
                sorted(demoted),
                needs_review,
                now.isoformat(),
            )
            return await self._get_site_config_on_conn(conn, site_key)

    async def record_success(
        self,
        site_id: str,
        tier: ExecutionTier | int,
    ) -> SiteTierConfig:
        site_key = site_id.strip().lower()
        tier_num = int(tier)
        now_iso = self._clock.utc_now_iso()

        async with self._db.transaction() as conn:
            cfg = await self._get_site_config_on_conn(conn, site_key)
            failures = dict(cfg.failure_counts)
            circuits = dict(cfg.circuit_open_until)
            demoted = [t for t in cfg.demoted_tiers if t != tier_num]
            failures[tier_num] = 0
            circuits.pop(tier_num, None)

            await self._persist_health_on_conn(
                conn,
                site_key,
                cfg,
                failures,
                circuits,
                demoted,
                bool(demoted),
                now_iso,
            )
            return await self._get_site_config_on_conn(conn, site_key)

    async def _persist_health_on_conn(
        self,
        conn: object,
        site_key: str,
        cfg: SiteTierConfig,
        failures: dict[int, int],
        circuits: dict[int, datetime],
        demoted: list[int],
        needs_review: bool,
        now_iso: str,
    ) -> None:
        failures_json = json.dumps({str(k): v for k, v in failures.items()})
        circuits_json = json.dumps({str(k): v.isoformat() for k, v in circuits.items()})
        fallbacks_json = json.dumps([int(t) for t in cfg.fallback_tiers])
        demoted_json = json.dumps(demoted)

        await conn.execute(  # type: ignore[attr-defined]
            """
            INSERT INTO agent_tier_registry (
                site_id, preferred_tier, fallback_tiers_json,
                enabled, circuit_open_json, failure_counts_json,
                demoted_tiers_json, needs_review, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(site_id) DO UPDATE SET
                circuit_open_json = excluded.circuit_open_json,
                failure_counts_json = excluded.failure_counts_json,
                demoted_tiers_json = excluded.demoted_tiers_json,
                needs_review = excluded.needs_review,
                updated_at = excluded.updated_at
            """,
            (
                site_key,
                int(cfg.preferred_tier),
                fallbacks_json,
                1 if cfg.enabled else 0,
                circuits_json,
                failures_json,
                demoted_json,
                1 if needs_review else 0,
                now_iso,
            ),
        )


class ProfileHealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CHECKPOINTED = "checkpointed"


class ProfileHealthRecord(BaseModel):
    profile_id: str
    site_id: str
    health_score: float
    status: ProfileHealthStatus
    checkpoint_flagged: bool = False
    token_expires_at: datetime | None = None
    last_error: str | None = None
    updated_at: datetime


@runtime_checkable
class TokenRefresher(Protocol):
    """Callback interface to rotate an expiring OAuth/session refresh_token (MVP-29)."""

    async def refresh(
        self,
        profile_id: str,
        refresh_token: str,
    ) -> tuple[str, str | None, datetime]:
        """Return (new_access_token, optional_new_refresh_token, new_expires_at)."""
        ...


class ProfileHealthMonitor:
    """Tracks profile health_score, checkpoint flags, and encrypted tokens (MVP-29)."""

    def __init__(
        self,
        db: DatabasePool,
        cipher: PiiCipher,
        *,
        clock: Clock | None = None,
        min_eligible_score: float = 0.5,
    ) -> None:
        self._db = db
        self._cipher = cipher
        self._clock = clock or SystemClock()
        self._min_eligible_score = min_eligible_score

    @staticmethod
    def _row_to_record(row: object) -> ProfileHealthRecord:
        exp_raw = row["token_expires_at"]  # type: ignore[index]
        return ProfileHealthRecord(
            profile_id=row["profile_id"],  # type: ignore[index]
            site_id=row["site_id"],  # type: ignore[index]
            health_score=float(row["health_score"]),  # type: ignore[index]
            status=ProfileHealthStatus(row["status"]),  # type: ignore[index]
            checkpoint_flagged=bool(row["checkpoint_flagged"]),  # type: ignore[index]
            token_expires_at=datetime.fromisoformat(exp_raw) if exp_raw else None,
            last_error=row["last_error"],  # type: ignore[index]
            updated_at=datetime.fromisoformat(row["updated_at"]),  # type: ignore[index]
        )

    async def register_tokens(
        self,
        *,
        profile_id: str,
        site_id: str,
        access_token: str,
        refresh_token: str,
        expires_at: datetime,
    ) -> ProfileHealthRecord:
        """Persist encrypted access & refresh tokens for a web profile."""
        now_iso = self._clock.utc_now_iso()
        acc_enc = self._cipher.encrypt(access_token)
        ref_enc = self._cipher.encrypt(refresh_token)
        async with self._db.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO agent_profile_health (
                    profile_id, site_id, health_score, status, checkpoint_flagged,
                    access_token_encrypted, refresh_token_encrypted,
                    token_expires_at, last_error, updated_at
                ) VALUES (?, ?, 1.0, ?, 0, ?, ?, ?, NULL, ?)
                ON CONFLICT(profile_id) DO UPDATE SET
                    site_id = excluded.site_id,
                    access_token_encrypted = excluded.access_token_encrypted,
                    refresh_token_encrypted = excluded.refresh_token_encrypted,
                    token_expires_at = excluded.token_expires_at,
                    updated_at = excluded.updated_at
                """,
                (
                    profile_id,
                    site_id.strip().lower(),
                    str(ProfileHealthStatus.HEALTHY),
                    acc_enc,
                    ref_enc,
                    expires_at.isoformat(),
                    now_iso,
                ),
            )
            cursor = await conn.execute(
                "SELECT * FROM agent_profile_health WHERE profile_id = ?",
                (profile_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_record(row)

    async def get_health(self, profile_id: str) -> ProfileHealthRecord | None:
        async with self._db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM agent_profile_health WHERE profile_id = ?",
                (profile_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_record(row) if row is not None else None

    async def get_decrypted_access_token(self, profile_id: str) -> str | None:
        async with self._db.connection() as conn:
            cursor = await conn.execute(
                "SELECT access_token_encrypted FROM agent_profile_health WHERE profile_id = ?",
                (profile_id,),
            )
            row = await cursor.fetchone()
        if row is None or not row["access_token_encrypted"]:
            return None
        return self._cipher.decrypt(row["access_token_encrypted"])

    async def is_eligible(self, profile_id: str) -> bool:
        """Return False if profile is degraded, checkpointed, or below health_score threshold."""
        rec = await self.get_health(profile_id)
        if rec is None:
            return True
        if rec.checkpoint_flagged or rec.status != ProfileHealthStatus.HEALTHY:
            return False
        return rec.health_score >= self._min_eligible_score

    async def record_session_outcome(
        self,
        *,
        profile_id: str,
        site_id: str,
        success: bool,
        checkpoint_detected: bool = False,
        error: str | None = None,
    ) -> ProfileHealthRecord:
        """Adjust health_score after a booking session and quarantine checkpointed profiles."""
        now_iso = self._clock.utc_now_iso()
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                "SELECT * FROM agent_profile_health WHERE profile_id = ?",
                (profile_id,),
            )
            existing_row = await cursor.fetchone()
            existing = self._row_to_record(existing_row) if existing_row is not None else None
            current_score = existing.health_score if existing else 1.0

            if checkpoint_detected:
                new_score = 0.0
                new_status = ProfileHealthStatus.CHECKPOINTED
                flagged = 1
            elif success:
                new_score = min(1.0, round(current_score + 0.05, 4))
                new_status = ProfileHealthStatus.HEALTHY
                flagged = 0
            else:
                new_score = max(0.0, round(current_score - 0.35, 4))
                new_status = (
                    ProfileHealthStatus.DEGRADED
                    if new_score < self._min_eligible_score
                    else ProfileHealthStatus.HEALTHY
                )
                flagged = 1 if existing and existing.checkpoint_flagged else 0

            await conn.execute(
                """
                INSERT INTO agent_profile_health (
                    profile_id, site_id, health_score, status, checkpoint_flagged,
                    access_token_encrypted, refresh_token_encrypted,
                    token_expires_at, last_error, updated_at
                ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET
                    site_id = excluded.site_id,
                    health_score = excluded.health_score,
                    status = excluded.status,
                    checkpoint_flagged = excluded.checkpoint_flagged,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (
                    profile_id,
                    site_id.strip().lower(),
                    new_score,
                    str(new_status),
                    flagged,
                    error,
                    now_iso,
                ),
            )
            cursor = await conn.execute(
                "SELECT * FROM agent_profile_health WHERE profile_id = ?",
                (profile_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_record(row)

    async def rotate_expiring_tokens(
        self,
        refresher: TokenRefresher,
        *,
        refresh_window_seconds: int = 300,
    ) -> tuple[list[str], list[str]]:
        """Rotate tokens expiring soon; return (refreshed_ids, degraded_ids)."""
        now = self._clock.utc_now()
        cutoff_iso = (now + timedelta(seconds=refresh_window_seconds)).isoformat()

        async with self._db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT profile_id, refresh_token_encrypted
                FROM agent_profile_health
                WHERE status = ?
                  AND checkpoint_flagged = 0
                  AND refresh_token_encrypted IS NOT NULL
                  AND token_expires_at IS NOT NULL
                  AND token_expires_at <= ?
                """,
                (str(ProfileHealthStatus.HEALTHY), cutoff_iso),
            )
            candidates = await cursor.fetchall()

        refreshed: list[str] = []
        degraded: list[str] = []

        for row in candidates:
            profile_id = row["profile_id"]
            refresh_tok = self._cipher.decrypt(row["refresh_token_encrypted"])
            try:
                new_access, new_refresh, new_expires = await refresher.refresh(
                    profile_id,
                    refresh_tok,
                )
                acc_enc = self._cipher.encrypt(new_access)
                ref_enc = self._cipher.encrypt(new_refresh or refresh_tok)
                async with self._db.transaction() as conn:
                    await conn.execute(
                        """
                        UPDATE agent_profile_health
                        SET access_token_encrypted = ?,
                            refresh_token_encrypted = ?,
                            token_expires_at = ?,
                            last_error = NULL,
                            updated_at = ?
                        WHERE profile_id = ?
                        """,
                        (
                            acc_enc,
                            ref_enc,
                            new_expires.isoformat(),
                            self._clock.utc_now_iso(),
                            profile_id,
                        ),
                    )
                refreshed.append(profile_id)
            except Exception as exc:
                async with self._db.transaction() as conn:
                    await conn.execute(
                        """
                        UPDATE agent_profile_health
                        SET status = ?,
                            health_score = 0.2,
                            last_error = ?,
                            updated_at = ?
                        WHERE profile_id = ?
                        """,
                        (
                            str(ProfileHealthStatus.DEGRADED),
                            str(exc),
                            self._clock.utc_now_iso(),
                            profile_id,
                        ),
                    )
                degraded.append(profile_id)

        return refreshed, degraded
