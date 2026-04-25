import os

import asyncpg

from src.config.settings import DEFAULT_DB_POOL_MIN, DEFAULT_DB_POOL_MAX

_pool: asyncpg.Pool | None = None


def _get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return database_url


async def get_pool() -> asyncpg.Pool:
    """Return the existing pool, creating it if necessary."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            _get_database_url(),
            min_size=DEFAULT_DB_POOL_MIN,
            max_size=DEFAULT_DB_POOL_MAX,
        )
    return _pool


async def init_db() -> asyncpg.Pool:
    """Create the connection pool, run all DDL statements, and return the pool."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id UUID PRIMARY KEY,
                header TEXT,
                initial_prompt TEXT NOT NULL,
                report_markdown TEXT,
                search_mode TEXT NOT NULL DEFAULT 'no_adaptive',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                usage_jsonb JSONB,
                cost_summary_jsonb JSONB
            );
            """
        )
        await connection.execute(
            """
            ALTER TABLE sessions
            ADD COLUMN IF NOT EXISTS search_mode TEXT NOT NULL DEFAULT 'no_adaptive';
            """
        )
        await connection.execute(
            """
            ALTER TABLE sessions
            ADD COLUMN IF NOT EXISTS cost_effective_search BOOLEAN NOT NULL DEFAULT FALSE;
            """
        )
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id UUID PRIMARY KEY,
                session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                message_type TEXT NOT NULL,
                agent_name TEXT,
                usage_jsonb JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        await connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sessions_last_activity
            ON sessions(last_activity_at DESC);
            """
        )
        await connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_session_id
            ON messages(session_id);
            """
        )
    return pool


async def close_pool() -> None:
    """Close the connection pool gracefully."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
