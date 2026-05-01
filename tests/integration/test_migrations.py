"""Integration tests for Alembic database migrations.

These tests run against an isolated temporary PostgreSQL database managed by
the ``test_db`` session-scoped fixture in ``conftest.py``.  They are skipped
automatically when DATABASE_URL is not set or the database server is
unreachable.

Test groups
-----------
- **Upgrade** (8.1): ``alembic upgrade head`` creates the correct tables,
  columns, types, defaults, and indexes.
- **Downgrade / round-trip** (8.2): ``alembic downgrade -1`` removes all
  application tables and indexes; a downgrade-then-upgrade round trip
  produces a schema identical to upgrade alone.
- **Schema drift detection** (8.3): ``_check_schema()`` passes on a fully
  migrated database and raises ``RuntimeError`` on an empty database.
- **Alembic CLI** (8.4): ``alembic current``, ``alembic history``, and
  ``alembic revision`` behave correctly.

_Requirements: 2.6, 4.1, 4.2, 4.3, 5.1, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5_
"""

import asyncio
import os
import shutil
import subprocess
import tempfile
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest
from dotenv import load_dotenv

from src.db.pool import _check_schema  # noqa: PLC2701 (testing internal helper)

# Revision ID of the initial migration script.
INITIAL_REVISION = "a1b2c3d4e5f6"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_alembic(args: list[str], database_url: str) -> subprocess.CompletedProcess:
    """Run an Alembic CLI command against *database_url* and return the result."""
    env = {**os.environ, "DATABASE_URL": database_url}
    return subprocess.run(  # noqa: S603
        ["alembic", *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _derive_test_db_url(database_url: str, suffix: str = "_test") -> tuple[str, str]:
    """Return ``(url, db_name)`` by appending *suffix* to the database name."""
    parsed = urlparse(database_url)
    db_name = parsed.path.lstrip("/") + suffix
    url = urlunparse(parsed._replace(path=f"/{db_name}"))
    return url, db_name


def _maintenance_url(database_url: str) -> str:
    """Return a URL pointing at the ``postgres`` maintenance database."""
    parsed = urlparse(database_url)
    return urlunparse(parsed._replace(path="/postgres"))


def _new_loop() -> asyncio.AbstractEventLoop:
    """Create and return a fresh event loop."""
    return asyncio.new_event_loop()


def _run(coro, loop: asyncio.AbstractEventLoop | None = None):
    """Run *coro* on *loop* (or a new loop) and return the result."""
    own_loop = loop is None
    if own_loop:
        loop = _new_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        if own_loop:
            loop.close()


async def _create_db(maint_url: str, db_name: str) -> None:
    """Create a fresh database, dropping any pre-existing one first."""
    conn = await asyncpg.connect(maint_url)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()


async def _drop_db(maint_url: str, db_name: str) -> None:
    """Terminate connections to *db_name* and drop it."""
    conn = await asyncpg.connect(maint_url)
    try:
        await conn.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = $1 AND pid <> pg_backend_pid()
            """,
            db_name,
        )
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Module-level fixture: resolved test database URL
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def test_db_url() -> str:
    """Return the URL of the test database, skipping if DATABASE_URL is unset."""
    load_dotenv()
    base = os.environ.get("DATABASE_URL")
    if not base:
        pytest.skip("DATABASE_URL is not set — skipping integration tests")
    url, _ = _derive_test_db_url(base)
    return url


# ---------------------------------------------------------------------------
# 8.1  Migration upgrade — tables, columns, types, defaults, indexes
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMigrationUpgrade:
    """Verify that ``alembic upgrade head`` produces the expected schema.

    _Requirements: 2.6, 5.1_
    """

    def test_sessions_table_exists(self, test_db) -> None:
        """sessions table is present after upgrade head."""
        pool, loop = test_db

        async def _check():
            async with pool.acquire() as conn:
                return await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM pg_tables
                        WHERE schemaname = 'public' AND tablename = 'sessions'
                    )
                    """
                )

        assert _run(_check(), loop) is True

    def test_messages_table_exists(self, test_db) -> None:
        """messages table is present after upgrade head."""
        pool, loop = test_db

        async def _check():
            async with pool.acquire() as conn:
                return await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM pg_tables
                        WHERE schemaname = 'public' AND tablename = 'messages'
                    )
                    """
                )

        assert _run(_check(), loop) is True

    def test_sessions_columns(self, test_db) -> None:
        """sessions table has all expected columns with correct types and nullability."""
        pool, loop = test_db

        async def _check():
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'sessions'
                    ORDER BY ordinal_position
                    """
                )
            return {r["column_name"]: r for r in rows}

        cols = _run(_check(), loop)

        expected_columns = {
            "id",
            "header",
            "initial_prompt",
            "report_markdown",
            "search_mode",
            "cost_effective_search",
            "created_at",
            "updated_at",
            "last_activity_at",
            "usage_jsonb",
            "cost_summary_jsonb",
        }
        assert expected_columns == set(cols.keys())

        # Nullability
        assert cols["id"]["is_nullable"] == "NO"
        assert cols["initial_prompt"]["is_nullable"] == "NO"
        assert cols["search_mode"]["is_nullable"] == "NO"
        assert cols["cost_effective_search"]["is_nullable"] == "NO"
        assert cols["created_at"]["is_nullable"] == "NO"
        assert cols["updated_at"]["is_nullable"] == "NO"
        assert cols["last_activity_at"]["is_nullable"] == "NO"
        assert cols["header"]["is_nullable"] == "YES"
        assert cols["report_markdown"]["is_nullable"] == "YES"
        assert cols["usage_jsonb"]["is_nullable"] == "YES"
        assert cols["cost_summary_jsonb"]["is_nullable"] == "YES"

        # Types (PostgreSQL information_schema names)
        assert cols["id"]["data_type"] == "uuid"
        assert cols["header"]["data_type"] == "text"
        assert cols["initial_prompt"]["data_type"] == "text"
        assert cols["search_mode"]["data_type"] == "text"
        assert cols["cost_effective_search"]["data_type"] == "boolean"
        assert cols["created_at"]["data_type"] == "timestamp with time zone"
        assert cols["updated_at"]["data_type"] == "timestamp with time zone"
        assert cols["last_activity_at"]["data_type"] == "timestamp with time zone"
        assert cols["usage_jsonb"]["data_type"] == "jsonb"
        assert cols["cost_summary_jsonb"]["data_type"] == "jsonb"

        # Server defaults
        assert "no_adaptive" in (cols["search_mode"]["column_default"] or "")
        assert cols["cost_effective_search"]["column_default"] is not None
        assert cols["created_at"]["column_default"] is not None
        assert cols["updated_at"]["column_default"] is not None
        assert cols["last_activity_at"]["column_default"] is not None

    def test_messages_columns(self, test_db) -> None:
        """messages table has all expected columns with correct types and nullability."""
        pool, loop = test_db

        async def _check():
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'messages'
                    ORDER BY ordinal_position
                    """
                )
            return {r["column_name"]: r for r in rows}

        cols = _run(_check(), loop)

        expected_columns = {
            "id",
            "session_id",
            "role",
            "content",
            "message_type",
            "agent_name",
            "usage_jsonb",
            "created_at",
        }
        assert expected_columns == set(cols.keys())

        # Nullability
        assert cols["id"]["is_nullable"] == "NO"
        assert cols["session_id"]["is_nullable"] == "NO"
        assert cols["role"]["is_nullable"] == "NO"
        assert cols["content"]["is_nullable"] == "NO"
        assert cols["message_type"]["is_nullable"] == "NO"
        assert cols["created_at"]["is_nullable"] == "NO"
        assert cols["agent_name"]["is_nullable"] == "YES"
        assert cols["usage_jsonb"]["is_nullable"] == "YES"

        # Types
        assert cols["id"]["data_type"] == "uuid"
        assert cols["session_id"]["data_type"] == "uuid"
        assert cols["role"]["data_type"] == "text"
        assert cols["content"]["data_type"] == "text"
        assert cols["message_type"]["data_type"] == "text"
        assert cols["created_at"]["data_type"] == "timestamp with time zone"
        assert cols["usage_jsonb"]["data_type"] == "jsonb"

        # created_at has a server default
        assert cols["created_at"]["column_default"] is not None

    def test_messages_foreign_key_on_delete_cascade(self, test_db) -> None:
        """messages.session_id has a FK to sessions.id with ON DELETE CASCADE."""
        pool, loop = test_db

        async def _check():
            async with pool.acquire() as conn:
                return await conn.fetchrow(
                    """
                    SELECT rc.delete_rule
                    FROM information_schema.referential_constraints rc
                    JOIN information_schema.key_column_usage kcu
                      ON kcu.constraint_name = rc.constraint_name
                     AND kcu.constraint_schema = rc.constraint_schema
                    WHERE kcu.table_name = 'messages'
                      AND kcu.column_name = 'session_id'
                    """
                )

        row = _run(_check(), loop)
        assert (
            row is not None
        ), "Foreign key constraint on messages.session_id not found"
        assert row["delete_rule"] == "CASCADE"

    def test_idx_sessions_last_activity_exists(self, test_db) -> None:
        """idx_sessions_last_activity index exists on the sessions table."""
        pool, loop = test_db

        async def _check():
            async with pool.acquire() as conn:
                return await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM pg_indexes
                        WHERE schemaname = 'public'
                          AND tablename = 'sessions'
                          AND indexname = 'idx_sessions_last_activity'
                    )
                    """
                )

        assert _run(_check(), loop) is True

    def test_idx_messages_session_id_exists(self, test_db) -> None:
        """idx_messages_session_id index exists on the messages table."""
        pool, loop = test_db

        async def _check():
            async with pool.acquire() as conn:
                return await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM pg_indexes
                        WHERE schemaname = 'public'
                          AND tablename = 'messages'
                          AND indexname = 'idx_messages_session_id'
                    )
                    """
                )

        assert _run(_check(), loop) is True

    def test_alembic_version_table_populated(self, test_db) -> None:
        """alembic_version table exists and contains the initial revision."""
        pool, loop = test_db

        async def _check():
            async with pool.acquire() as conn:
                return await conn.fetchval(
                    "SELECT version_num FROM alembic_version LIMIT 1"
                )

        revision = _run(_check(), loop)
        assert revision is not None
        assert revision == INITIAL_REVISION


# ---------------------------------------------------------------------------
# 8.2  Downgrade and round-trip
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMigrationDowngradeAndRoundTrip:
    """Verify downgrade removes all application objects and round-trip is idempotent.

    A dedicated temporary database is created for this class so that downgrade
    operations do not affect the ``test_db`` fixture used by other tests.

    _Requirements: 4.1, 4.2, 4.3_
    """

    @pytest.fixture(scope="class")
    def roundtrip_url(self):
        """Provide a URL for a fresh database pre-loaded with migrations."""
        load_dotenv()
        base = os.environ.get("DATABASE_URL")
        if not base:
            pytest.skip("DATABASE_URL is not set — skipping integration tests")

        rt_url, db_name = _derive_test_db_url(base, suffix="_roundtrip_test")
        maint_url = _maintenance_url(base)

        loop = _new_loop()
        try:
            loop.run_until_complete(_create_db(maint_url, db_name))
            result = _run_alembic(["upgrade", "head"], rt_url)
            if result.returncode != 0:
                raise RuntimeError(
                    f"alembic upgrade head failed for roundtrip db:\n{result.stderr}"
                )
            yield rt_url
        finally:
            loop.run_until_complete(_drop_db(maint_url, db_name))
            loop.close()

    def test_downgrade_exits_zero(self, roundtrip_url: str) -> None:
        """``alembic downgrade -1`` exits with code 0."""
        result = _run_alembic(["downgrade", "-1"], roundtrip_url)
        assert result.returncode == 0, f"downgrade failed:\n{result.stderr}"

    def test_downgrade_removes_sessions_table(self, roundtrip_url: str) -> None:
        """After downgrade -1, the sessions table no longer exists."""

        async def _check():
            conn = await asyncpg.connect(roundtrip_url)
            try:
                return await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM pg_tables
                        WHERE schemaname = 'public' AND tablename = 'sessions'
                    )
                    """
                )
            finally:
                await conn.close()

        assert _run(_check()) is False

    def test_downgrade_removes_messages_table(self, roundtrip_url: str) -> None:
        """After downgrade -1, the messages table no longer exists."""

        async def _check():
            conn = await asyncpg.connect(roundtrip_url)
            try:
                return await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM pg_tables
                        WHERE schemaname = 'public' AND tablename = 'messages'
                    )
                    """
                )
            finally:
                await conn.close()

        assert _run(_check()) is False

    def test_downgrade_removes_indexes(self, roundtrip_url: str) -> None:
        """After downgrade -1, both application indexes no longer exist."""

        async def _check():
            conn = await asyncpg.connect(roundtrip_url)
            try:
                rows = await conn.fetch(
                    """
                    SELECT indexname FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND indexname IN (
                          'idx_sessions_last_activity',
                          'idx_messages_session_id'
                      )
                    """
                )
            finally:
                await conn.close()
            return [r["indexname"] for r in rows]

        assert _run(_check()) == []

    def test_roundtrip_produces_same_tables(self, roundtrip_url: str) -> None:
        """Downgrade then upgrade produces the same tables as upgrade alone."""
        result = _run_alembic(["upgrade", "head"], roundtrip_url)
        assert (
            result.returncode == 0
        ), f"upgrade after downgrade failed:\n{result.stderr}"

        async def _check():
            conn = await asyncpg.connect(roundtrip_url)
            try:
                rows = await conn.fetch(
                    """
                    SELECT tablename FROM pg_tables
                    WHERE schemaname = 'public'
                      AND tablename IN ('sessions', 'messages')
                    ORDER BY tablename
                    """
                )
            finally:
                await conn.close()
            return [r["tablename"] for r in rows]

        assert _run(_check()) == ["messages", "sessions"]

    def test_roundtrip_produces_same_indexes(self, roundtrip_url: str) -> None:
        """Downgrade then upgrade produces the same indexes as upgrade alone."""

        async def _check():
            conn = await asyncpg.connect(roundtrip_url)
            try:
                rows = await conn.fetch(
                    """
                    SELECT indexname FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND indexname IN (
                          'idx_sessions_last_activity',
                          'idx_messages_session_id'
                      )
                    ORDER BY indexname
                    """
                )
            finally:
                await conn.close()
            return [r["indexname"] for r in rows]

        assert _run(_check()) == [
            "idx_messages_session_id",
            "idx_sessions_last_activity",
        ]

    def test_roundtrip_alembic_version_restored(self, roundtrip_url: str) -> None:
        """After round-trip, alembic_version contains the initial revision."""

        async def _check():
            conn = await asyncpg.connect(roundtrip_url)
            try:
                return await conn.fetchval(
                    "SELECT version_num FROM alembic_version LIMIT 1"
                )
            finally:
                await conn.close()

        assert _run(_check()) == INITIAL_REVISION


# ---------------------------------------------------------------------------
# 8.3  Schema drift detection
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSchemaDriftDetection:
    """Verify _check_schema() behaviour on migrated and empty databases.

    _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
    """

    @pytest.fixture(scope="class")
    def empty_pool(self):
        """Provide an asyncpg pool connected to a fresh, unmigrated database."""
        load_dotenv()
        base = os.environ.get("DATABASE_URL")
        if not base:
            pytest.skip("DATABASE_URL is not set — skipping integration tests")

        empty_url, db_name = _derive_test_db_url(base, suffix="_empty_test")
        maint_url = _maintenance_url(base)

        loop = _new_loop()
        try:
            prev_loop = asyncio.get_event_loop()
        except RuntimeError:
            prev_loop = None
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_create_db(maint_url, db_name))
            pool = loop.run_until_complete(
                asyncpg.create_pool(empty_url, min_size=1, max_size=2)
            )
            yield pool, loop
        finally:
            if "pool" in dir():
                loop.run_until_complete(pool.close())
            loop.run_until_complete(_drop_db(maint_url, db_name))
            loop.close()
            asyncio.set_event_loop(prev_loop)

    # --- passes on a fully migrated database ---

    def test_check_schema_passes_on_migrated_db(self, test_db) -> None:
        """_check_schema() does not raise on a fully migrated database."""
        pool, loop = test_db
        _run(_check_schema(pool), loop)  # must not raise

    # --- raises on an empty (unmigrated) database ---

    def test_check_schema_raises_on_empty_db(self, empty_pool) -> None:
        """_check_schema() raises RuntimeError when no tables exist."""
        pool, loop = empty_pool
        with pytest.raises(RuntimeError):
            loop.run_until_complete(_check_schema(pool))

    def test_check_schema_error_mentions_upgrade_head(self, empty_pool) -> None:
        """RuntimeError message instructs developer to run alembic upgrade head."""
        pool, loop = empty_pool
        with pytest.raises(RuntimeError, match="alembic upgrade head"):
            loop.run_until_complete(_check_schema(pool))

    def test_check_schema_error_mentions_schema_drift(self, empty_pool) -> None:
        """RuntimeError message includes 'Schema drift detected'."""
        pool, loop = empty_pool
        with pytest.raises(RuntimeError, match="Schema drift detected"):
            loop.run_until_complete(_check_schema(pool))

    # --- raises when individual tables are missing ---

    def test_check_schema_raises_when_sessions_missing(self, test_db) -> None:
        """_check_schema() raises RuntimeError when sessions table is absent."""
        pool, loop = test_db

        async def _rename_and_check():
            async with pool.acquire() as conn:
                await conn.execute("ALTER TABLE sessions RENAME TO sessions_hidden")
            try:
                await _check_schema(pool)
            finally:
                async with pool.acquire() as conn:
                    await conn.execute("ALTER TABLE sessions_hidden RENAME TO sessions")

        with pytest.raises(RuntimeError, match="sessions"):
            _run(_rename_and_check(), loop)

    def test_check_schema_raises_when_messages_missing(self, test_db) -> None:
        """_check_schema() raises RuntimeError when messages table is absent."""
        pool, loop = test_db

        async def _rename_and_check():
            async with pool.acquire() as conn:
                await conn.execute("ALTER TABLE messages RENAME TO messages_hidden")
            try:
                await _check_schema(pool)
            finally:
                async with pool.acquire() as conn:
                    await conn.execute("ALTER TABLE messages_hidden RENAME TO messages")

        with pytest.raises(RuntimeError, match="messages"):
            _run(_rename_and_check(), loop)

    def test_check_schema_raises_when_alembic_version_missing(self, test_db) -> None:
        """_check_schema() raises RuntimeError when alembic_version table is absent."""
        pool, loop = test_db

        async def _rename_and_check():
            async with pool.acquire() as conn:
                await conn.execute(
                    "ALTER TABLE alembic_version RENAME TO alembic_version_hidden"
                )
            try:
                await _check_schema(pool)
            finally:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "ALTER TABLE alembic_version_hidden RENAME TO alembic_version"
                    )

        with pytest.raises(RuntimeError, match="alembic upgrade head"):
            _run(_rename_and_check(), loop)

    def test_check_schema_raises_when_alembic_version_empty(self, test_db) -> None:
        """_check_schema() raises RuntimeError when alembic_version has no rows."""
        pool, loop = test_db

        async def _clear_and_check():
            async with pool.acquire() as conn:
                saved = await conn.fetchval(
                    "SELECT version_num FROM alembic_version LIMIT 1"
                )
                await conn.execute("DELETE FROM alembic_version")
            try:
                await _check_schema(pool)
            finally:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO alembic_version (version_num) VALUES ($1)",
                        saved,
                    )

        with pytest.raises(RuntimeError, match="alembic upgrade head"):
            _run(_clear_and_check(), loop)


# ---------------------------------------------------------------------------
# 8.4  Alembic CLI commands
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAlembicCLICommands:
    """Verify standard Alembic CLI commands work correctly.

    _Requirements: 5.3, 5.4, 5.5_
    """

    def test_alembic_current_exits_zero(self, test_db_url: str) -> None:
        """``alembic current`` exits with code 0."""
        result = _run_alembic(["current"], test_db_url)
        assert result.returncode == 0, f"alembic current failed:\n{result.stderr}"

    def test_alembic_current_shows_revision(self, test_db_url: str) -> None:
        """``alembic current`` output contains the applied revision hash."""
        result = _run_alembic(["current"], test_db_url)
        assert (
            INITIAL_REVISION in result.stdout
        ), f"Expected revision '{INITIAL_REVISION}' in output:\n{result.stdout}"

    def test_alembic_history_exits_zero(self, test_db_url: str) -> None:
        """``alembic history`` exits with code 0."""
        result = _run_alembic(["history"], test_db_url)
        assert result.returncode == 0, f"alembic history failed:\n{result.stderr}"

    def test_alembic_history_shows_initial_migration(self, test_db_url: str) -> None:
        """``alembic history`` output lists the initial schema migration."""
        result = _run_alembic(["history"], test_db_url)
        assert (
            INITIAL_REVISION in result.stdout
        ), f"Expected revision '{INITIAL_REVISION}' in history output:\n{result.stdout}"

    def test_alembic_history_shows_migration_description(
        self, test_db_url: str
    ) -> None:
        """``alembic history`` output includes the migration description."""
        result = _run_alembic(["history"], test_db_url)
        assert (
            "initial" in result.stdout.lower()
        ), f"Expected 'initial' in history output:\n{result.stdout}"

    def test_alembic_revision_generates_file(self, test_db_url: str) -> None:
        """``alembic revision`` generates a new migration script file.

        The generated file is created in a temporary directory to avoid
        polluting the real ``versions/`` directory.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Copy the alembic directory to a temp location.
            tmp_alembic = os.path.join(tmpdir, "alembic")
            shutil.copytree("alembic", tmp_alembic)

            # Copy and patch alembic.ini to point at the temp alembic dir.
            tmp_ini = os.path.join(tmpdir, "alembic.ini")
            shutil.copy("alembic.ini", tmp_ini)
            with open(tmp_ini, encoding="utf-8") as fh:
                ini_content = fh.read()
            ini_content = ini_content.replace(
                "script_location = alembic",
                f"script_location = {tmp_alembic}",
            )
            with open(tmp_ini, "w", encoding="utf-8") as fh:
                fh.write(ini_content)

            env = {**os.environ, "DATABASE_URL": test_db_url}
            result = subprocess.run(  # noqa: S603
                ["alembic", "-c", tmp_ini, "revision", "-m", "test_revision"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
                cwd=tmpdir,
            )
            assert result.returncode == 0, f"alembic revision failed:\n{result.stderr}"

            # A new file should have been created in the temp versions/ dir.
            versions_dir = os.path.join(tmp_alembic, "versions")
            new_files = [
                f
                for f in os.listdir(versions_dir)
                if f.endswith(".py") and "test_revision" in f
            ]
            assert (
                len(new_files) == 1
            ), f"Expected one new revision file, found: {new_files}"
