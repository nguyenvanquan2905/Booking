"""Single source of truth for all SQLite DDL across modules (MVP-01, MVP-80)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite

DDL_STATEMENTS: tuple[str, ...] = (
    # --- booking_* (owner: C) ---
    """
    CREATE TABLE IF NOT EXISTS booking_customers (
        customer_id TEXT PRIMARY KEY,
        phone_hash TEXT NOT NULL UNIQUE,
        phone_encrypted TEXT NOT NULL,
        name_encrypted TEXT NOT NULL,
        email_encrypted TEXT,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        deleted_at TEXT
    )
    """.strip(),
    """
    CREATE INDEX IF NOT EXISTS idx_booking_customers_expires_at
    ON booking_customers (expires_at)
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS booking_requests (
        booking_id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL,
        idempotency_key TEXT,
        site_id TEXT NOT NULL,
        restaurant_name TEXT NOT NULL,
        party_size INTEGER NOT NULL,
        booking_time TEXT NOT NULL,
        allow_deposit_max INTEGER NOT NULL DEFAULT 0,
        notes TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL,
        confirmation_code TEXT,
        error_code TEXT,
        error_message TEXT,
        trace_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES booking_customers (customer_id)
    )
    """.strip(),
    """
    CREATE INDEX IF NOT EXISTS idx_booking_requests_status
    ON booking_requests (status, created_at)
    """.strip(),
    """
    CREATE INDEX IF NOT EXISTS idx_booking_requests_natural_key
    ON booking_requests (site_id, booking_time, customer_id)
    """.strip(),
    """
    CREATE INDEX IF NOT EXISTS idx_booking_requests_trace_id
    ON booking_requests (trace_id)
    """.strip(),
    """
    CREATE INDEX IF NOT EXISTS idx_booking_requests_site_id
    ON booking_requests (site_id)
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS booking_events (
        event_id TEXT PRIMARY KEY,
        booking_id TEXT NOT NULL,
        from_status TEXT,
        to_status TEXT NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        actor TEXT NOT NULL DEFAULT 'system',
        trace_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (booking_id) REFERENCES booking_requests (booking_id)
    )
    """.strip(),
    """
    CREATE INDEX IF NOT EXISTS idx_booking_events_booking_id
    ON booking_events (booking_id, created_at)
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS booking_idempotency (
        idempotency_key TEXT PRIMARY KEY,
        request_hash TEXT NOT NULL,
        booking_id TEXT NOT NULL,
        response_json TEXT,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )
    """.strip(),
    # --- agent_* (owner: C) ---
    """
    CREATE TABLE IF NOT EXISTS agent_tasks (
        task_id TEXT PRIMARY KEY,
        booking_id TEXT NOT NULL,
        site_id TEXT NOT NULL,
        tier INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL,
        priority INTEGER NOT NULL DEFAULT 0,
        attempts INTEGER NOT NULL DEFAULT 0,
        max_attempts INTEGER NOT NULL DEFAULT 3,
        payload_json TEXT NOT NULL,
        result_json TEXT,
        error_code TEXT,
        claimed_by TEXT,
        claimed_at TEXT,
        locked_by TEXT,
        locked_until TEXT,
        available_at TEXT NOT NULL,
        trace_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """.strip(),
    """
    CREATE INDEX IF NOT EXISTS idx_agent_tasks_claim
    ON agent_tasks (status, priority DESC, available_at ASC)
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS agent_scheduled_wakeups (
        wakeup_id TEXT PRIMARY KEY,
        task_id TEXT,
        thread_id TEXT NOT NULL,
        booking_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        wake_at TEXT NOT NULL,
        status TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """.strip(),
    """
    CREATE INDEX IF NOT EXISTS idx_agent_wakeups_due
    ON agent_scheduled_wakeups (status, wake_at)
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS agent_checkpoints (
        thread_id TEXT NOT NULL,
        checkpoint_ns TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL,
        parent_checkpoint_id TEXT,
        type TEXT,
        checkpoint BLOB,
        metadata BLOB,
        created_at TEXT NOT NULL,
        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
    )
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS agent_hitl_requests (
        hitl_id TEXT PRIMARY KEY,
        booking_id TEXT NOT NULL,
        task_id TEXT,
        reason TEXT NOT NULL,
        prompt_text TEXT NOT NULL,
        status TEXT NOT NULL,
        decision TEXT,
        decided_by TEXT,
        decided_at TEXT,
        expires_at TEXT NOT NULL,
        trace_id TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """.strip(),
    """
    CREATE INDEX IF NOT EXISTS idx_agent_hitl_booking_status
    ON agent_hitl_requests (booking_id, status)
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS agent_tier_registry (
        site_id TEXT PRIMARY KEY,
        preferred_tier INTEGER NOT NULL DEFAULT 1,
        fallback_tiers_json TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        circuit_open_json TEXT NOT NULL DEFAULT '{}',
        failure_counts_json TEXT NOT NULL DEFAULT '{}',
        demoted_tiers_json TEXT NOT NULL DEFAULT '[]',
        needs_review INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
    )
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS agent_profile_health (
        profile_id TEXT PRIMARY KEY,
        site_id TEXT NOT NULL,
        health_score REAL NOT NULL DEFAULT 1.0,
        status TEXT NOT NULL DEFAULT 'healthy',
        checkpoint_flagged INTEGER NOT NULL DEFAULT 0,
        access_token_encrypted TEXT,
        refresh_token_encrypted TEXT,
        token_expires_at TEXT,
        last_error TEXT,
        updated_at TEXT NOT NULL
    )
    """.strip(),
    # --- bc_* (owner: D) ---
    """
    CREATE TABLE IF NOT EXISTS bc_api_template (
        template_id TEXT PRIMARY KEY,
        site_id TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        definition_json TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL
    )
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS bc_playwright_workflow (
        workflow_id TEXT PRIMARY KEY,
        site_id TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        definition_json TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL
    )
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS bc_workflows (
        workflow_id TEXT PRIMARY KEY,
        site_id TEXT NOT NULL,
        tier INTEGER NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        definition_json TEXT NOT NULL,
        success_count INTEGER NOT NULL DEFAULT 0,
        failure_count INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
    )
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS bc_executions (
        exec_id TEXT PRIMARY KEY,
        booking_id TEXT NOT NULL,
        site_id TEXT NOT NULL,
        tier INTEGER NOT NULL,
        status TEXT NOT NULL,
        duration_ms REAL NOT NULL DEFAULT 0.0,
        error_code TEXT,
        created_at TEXT NOT NULL
    )
    """.strip(),
    # --- sandbox_* (owner: B) ---
    """
    CREATE TABLE IF NOT EXISTS sandbox_sessions (
        session_id TEXT PRIMARY KEY,
        booking_id TEXT NOT NULL,
        status TEXT NOT NULL,
        cpu_limit REAL NOT NULL DEFAULT 1.0,
        mem_limit_mb INTEGER NOT NULL DEFAULT 1024,
        created_at TEXT NOT NULL,
        closed_at TEXT
    )
    """.strip(),
    # --- profile_* (owner: A) ---
    """
    CREATE TABLE IF NOT EXISTS profile_records (
        profile_id TEXT PRIMARY KEY,
        site_id TEXT NOT NULL,
        proxy_url TEXT,
        fingerprint_seed TEXT,
        encrypted_storage_state TEXT,
        status TEXT NOT NULL DEFAULT 'ready',
        updated_at TEXT NOT NULL
    )
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS profile_lease (
        lease_id TEXT PRIMARY KEY,
        profile_id TEXT NOT NULL,
        booking_id TEXT NOT NULL,
        acquired_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        released_at TEXT,
        FOREIGN KEY (profile_id) REFERENCES profile_records (profile_id)
    )
    """.strip(),
    # --- artifact_* (owner: E) ---
    """
    CREATE TABLE IF NOT EXISTS artifact_index (
        artifact_id TEXT PRIMARY KEY,
        booking_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        file_path TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """.strip(),
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS artifact_fts USING fts5(
        artifact_id UNINDEXED,
        booking_id UNINDEXED,
        kind,
        metadata_text
    )
    """.strip(),
    # --- telemetry_* (owner: C schema + E metrics/benchmark) ---
    """
    CREATE TABLE IF NOT EXISTS telemetry_events (
        event_id TEXT PRIMARY KEY,
        trace_id TEXT NOT NULL,
        booking_id TEXT,
        layer TEXT NOT NULL,
        component TEXT NOT NULL,
        event_name TEXT NOT NULL,
        status TEXT NOT NULL,
        tier INTEGER,
        duration_ms REAL,
        cost_usd REAL,
        error_code TEXT,
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """.strip(),
    """
    CREATE INDEX IF NOT EXISTS idx_telemetry_events_trace_id
    ON telemetry_events (trace_id, created_at)
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS telemetry_benchmark_runs (
        run_id TEXT PRIMARY KEY,
        scenario_id TEXT NOT NULL,
        site_id TEXT NOT NULL,
        tier INTEGER NOT NULL,
        success INTEGER NOT NULL,
        latency_ms REAL NOT NULL,
        cost_usd REAL NOT NULL DEFAULT 0.0,
        created_at TEXT NOT NULL
    )
    """.strip(),
    """
    CREATE INDEX IF NOT EXISTS idx_telemetry_benchmark_runs_site_id
    ON telemetry_benchmark_runs (site_id, created_at)
    """.strip(),
)


def get_schema_sql() -> str:
    """Return the complete SQLite DDL script as a single SQL string."""
    return ";\n\n".join(DDL_STATEMENTS) + ";\n"


async def apply_schema(conn: aiosqlite.Connection) -> None:
    """Apply all DDL statements idempotently onto an open aiosqlite connection."""
    for statement in DDL_STATEMENTS:
        await conn.execute(statement)
    await conn.commit()
