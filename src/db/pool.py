import os

import asyncpg

from src.config.settings import DEFAULT_DB_POOL_MIN, DEFAULT_DB_POOL_MAX

_pool: asyncpg.Pool | None = None

_EXPECTED_TABLES = ("sessions", "messages")


def _get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return database_url


async def _check_schema(pool: asyncpg.Pool) -> None:
    """Verify that expected tables and Alembic version exist.

    Raises RuntimeError with actionable instructions if the schema
    is missing or migrations have not been applied.
    """
    async with pool.acquire() as conn:
        # Check for expected application tables
        rows = await conn.fetch(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public' AND tablename = ANY($1::text[])
            """,
            list(_EXPECTED_TABLES),
        )
        found = {row["tablename"] for row in rows}
        missing = set(_EXPECTED_TABLES) - found
        if missing:
            raise RuntimeError(
                f"Schema drift detected: missing tables {sorted(missing)}. "
                "Run `alembic upgrade head` before starting the application."
            )

        # Check that alembic_version exists and has a revision
        version_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'public' AND tablename = 'alembic_version'
            )
            """
        )
        if not version_exists:
            raise RuntimeError(
                "Schema drift detected: alembic_version table not found. "
                "Run `alembic upgrade head` before starting the application."
            )

        revision = await conn.fetchval(
            "SELECT version_num FROM alembic_version LIMIT 1"
        )
        if not revision:
            raise RuntimeError(
                "Schema drift detected: alembic_version table is empty (no applied revisions). "
                "Run `alembic upgrade head` before starting the application."
            )


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
    """Create the connection pool, verify schema, and return the pool.

    Schema management is handled by Alembic migrations.
    Run `alembic upgrade head` before starting the application.

    Raises RuntimeError if expected tables or Alembic version are missing.
    """
    pool = await get_pool()
    await _check_schema(pool)
    return pool


async def close_pool() -> None:
    """Close the connection pool gracefully."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
