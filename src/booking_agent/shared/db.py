"""Async SQLite connection pool/helper with WAL + busy_timeout PRAGMAs (MVP-01)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from booking_agent.shared.schema import apply_schema


class DatabasePool:
    """Lightweight async SQLite manager applying WAL, foreign_keys, and busy_timeout."""

    def __init__(self, db_path: Path | str, *, busy_timeout_ms: int = 5000) -> None:
        self._db_path_str = str(db_path)
        self._is_memory = self._db_path_str == ":memory:" or self._db_path_str.startswith(
            "file::memory:"
        )
        self._busy_timeout_ms = busy_timeout_ms
        self._shared_memory_conn: aiosqlite.Connection | None = None
        self._write_lock = asyncio.Lock()

    @property
    def db_path(self) -> str:
        return self._db_path_str

    async def _configure_connection(self, conn: aiosqlite.Connection) -> aiosqlite.Connection:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON;")
        await conn.execute(f"PRAGMA busy_timeout = {int(self._busy_timeout_ms)};")
        if not self._is_memory:
            await conn.execute("PRAGMA journal_mode = WAL;")
            await conn.execute("PRAGMA synchronous = NORMAL;")
            await conn.execute("PRAGMA wal_autocheckpoint = 1000;")
        return conn

    async def init(self) -> None:
        """Create parent directories if needed and apply the SQLite DDL schema."""
        if not self._is_memory:
            Path(self._db_path_str).parent.mkdir(parents=True, exist_ok=True)
        async with self.connection() as conn:
            await apply_schema(conn)

    async def close(self) -> None:
        """Close any kept-alive in-memory connection."""
        if self._shared_memory_conn is not None:
            await self._shared_memory_conn.close()
            self._shared_memory_conn = None

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Yield a configured aiosqlite connection."""
        if self._is_memory:
            if self._shared_memory_conn is None:
                conn = await aiosqlite.connect(self._db_path_str)
                self._shared_memory_conn = await self._configure_connection(conn)
            yield self._shared_memory_conn
            return

        conn = await aiosqlite.connect(self._db_path_str)
        try:
            await self._configure_connection(conn)
            yield conn
        finally:
            await conn.close()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        """Yield a connection wrapped in a serialized COMMIT/ROLLBACK transaction."""
        async with self._write_lock, self.connection() as conn:
            await conn.execute("BEGIN IMMEDIATE;")
            try:
                yield conn
            except Exception:
                await conn.rollback()
                raise
            else:
                await conn.commit()

    async def backup_to(self, backup_path: Path | str) -> Path:
        """Create an atomic hot snapshot via SQLite VACUUM INTO (System Design v2.1 §0, §6)."""
        target = Path(backup_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        escaped = target.as_posix().replace("'", "''")
        async with self._write_lock, self.connection() as conn:
            await conn.commit()
            await conn.execute(f"VACUUM INTO '{escaped}';")
        return target

    async def check_integrity(self) -> bool:
        """Run PRAGMA integrity_check and return True if database is healthy (§11)."""
        async with self.connection() as conn:
            cursor = await conn.execute("PRAGMA integrity_check;")
            row = await cursor.fetchone()
        return row is not None and str(row[0]).lower() == "ok"
