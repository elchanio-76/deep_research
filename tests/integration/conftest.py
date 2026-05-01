"""Session-scoped pytest fixtures for integration tests.

Manages the lifecycle of a temporary PostgreSQL test database:
  1. Derives the test database name by appending ``_test`` to the main DB name.
  2. Creates the test database against the ``postgres`` maintenance database.
  3. Runs ``alembic upgrade head`` against the test database.
  4. Yields an asyncpg connection pool to the test database.
  5. Terminates any remaining connections and drops the test database on teardown.

Integration tests that require a live database should request the ``test_db``
fixture.  Tests are automatically skipped when the database is unavailable
(e.g. in CI environments without PostgreSQL).

_Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
"""

import asyncio
import os
import subprocess
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _derive_test_db_url(database_url: str) -> tuple[str, str]:
    """Return ``(test_database_url, test_db_name)`` by appending ``_test`` to the DB name.

    Example::

        _derive_test_db_url("postgresql://user:pass@localhost/myapp")
        # → ("postgresql://user:pass@localhost/myapp_test", "myapp_test")
    """
    parsed = urlparse(database_url)
    db_name = parsed.path.lstrip("/")
    test_db_name = f"{db_name}_test"
    test_url = urlunparse(parsed._replace(path=f"/{test_db_name}"))
    return test_url, test_db_name


def _maintenance_url(database_url: str) -> str:
    """Return a URL pointing at the ``postgres`` maintenance database.

    Used to create/drop the test database without connecting to it directly.
    """
    parsed = urlparse(database_url)
    return urlunparse(parsed._replace(path="/postgres"))


# ---------------------------------------------------------------------------
# Session-scoped test database fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_db():
    """Create a temporary test database, run migrations, yield pool, then drop.

    Lifecycle:
      - setup: CREATE DATABASE <name>_test → alembic upgrade head → create pool
      - yield: asyncpg.Pool connected to the test database
      - teardown: close pool → terminate connections → DROP DATABASE

    Skips automatically when DATABASE_URL is not set or the database server
    is unreachable.

    _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
    """
    load_dotenv()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is not set — skipping integration tests")

    test_url, test_db_name = _derive_test_db_url(database_url)
    maint_url = _maintenance_url(database_url)

    async def _setup() -> asyncpg.Pool:
        # Connect to the maintenance database to create the test database.
        try:
            conn = await asyncpg.connect(maint_url)
        except (asyncpg.PostgresError, OSError) as exc:
            pytest.skip(
                f"Cannot connect to PostgreSQL ({exc}) — skipping integration tests"
            )

        try:
            # Drop any leftover test database from a previous interrupted run.
            await conn.execute(f'DROP DATABASE IF EXISTS "{test_db_name}"')
            await conn.execute(f'CREATE DATABASE "{test_db_name}"')
        finally:
            await conn.close()

        # Run Alembic migrations against the freshly created test database.
        env = {**os.environ, "DATABASE_URL": test_url}
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"alembic upgrade head failed for test database '{test_db_name}':\n"
                f"{result.stderr}"
            )

        # Create and return an asyncpg pool connected to the test database.
        pool = await asyncpg.create_pool(test_url, min_size=1, max_size=3)
        return pool

    async def _teardown(pool: asyncpg.Pool) -> None:
        await pool.close()

        # Connect to the maintenance database to drop the test database.
        conn = await asyncpg.connect(maint_url)
        try:
            # Terminate any remaining connections so DROP DATABASE succeeds.
            await conn.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = $1
                  AND pid <> pg_backend_pid()
                """,
                test_db_name,
            )
            await conn.execute(f'DROP DATABASE IF EXISTS "{test_db_name}"')
        finally:
            await conn.close()

    try:
        prev_loop = asyncio.get_event_loop()
    except RuntimeError:
        prev_loop = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        pool = loop.run_until_complete(_setup())
        yield pool, loop
        loop.run_until_complete(_teardown(pool))
    finally:
        loop.close()
        asyncio.set_event_loop(prev_loop)
