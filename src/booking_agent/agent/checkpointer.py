"""LangGraph AsyncSqliteSaver checkpointer factory (MVP-12 — owner: C)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


@asynccontextmanager
async def create_checkpointer(
    db_path: Path | str,
    *,
    busy_timeout_ms: int = 5000,
) -> AsyncIterator[AsyncSqliteSaver]:
    """Open and initialize an AsyncSqliteSaver bound to a SQLite database path."""
    path_str = str(db_path)
    is_memory = path_str == ":memory:" or path_str.startswith("file::memory:")
    if not is_memory:
        Path(path_str).parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(path_str) as conn:
        await conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)};")
        if not is_memory:
            await conn.execute("PRAGMA journal_mode = WAL;")
            await conn.execute("PRAGMA synchronous = NORMAL;")
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        yield saver
