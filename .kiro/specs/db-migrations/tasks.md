# Implementation Plan: Database Migrations with Alembic

## Overview

This plan migrates the project's schema management from inline DDL in `src/db/pool.py` to Alembic migration scripts. The implementation proceeds incrementally: dependencies first, then Alembic scaffolding, the initial migration script, refactoring `pool.py`, the test database fixture, and finally integration tests to validate the full workflow.

## Tasks

- [x] 1. Add dependencies to requirements.txt
  - Add `alembic` and `sqlalchemy` with pinned versions to `requirements.txt`
  - Install the updated dependencies in the virtual environment
  - _Requirements: 1.5_

- [x] 2. Scaffold Alembic project structure
  - [x] 2.1 Create `alembic.ini` at the project root
    - Reference `alembic/` as the script location
    - Do NOT include any hardcoded database credentials or connection strings
    - Include standard logging configuration (root, sqlalchemy, alembic loggers)
    - _Requirements: 1.2, 1.4_

  - [x] 2.2 Create `alembic/env.py`
    - Load `.env` via `python-dotenv` before resolving `DATABASE_URL`
    - Read `DATABASE_URL` from environment; raise `RuntimeError` if missing
    - Override `sqlalchemy.url` in Alembic config with the resolved URL
    - Implement `run_migrations_offline()` for `--sql` mode
    - Implement `run_migrations_online()` with a synchronous `create_engine` using `pool.NullPool`
    - Support optional database URL override via `x_argument` for test database usage
    - _Requirements: 1.1, 1.3, 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 2.3 Create `alembic/script.py.mako`
    - Use Alembic's default migration script template
    - _Requirements: 1.1_

  - [x] 2.4 Create `alembic/versions/` directory
    - Ensure the empty `versions/` subdirectory exists (add `.gitkeep` if needed)
    - _Requirements: 1.1_

- [ ] 3. Create the initial migration script
  - [ ] 3.1 Create `alembic/versions/<rev>_initial_schema.py`
    - Implement `upgrade()` that creates the `sessions` table with all columns, types, defaults, and constraints matching current inline DDL
    - Implement `upgrade()` that creates the `messages` table with all columns, FK constraint (`ON DELETE CASCADE`), and defaults
    - Create `idx_sessions_last_activity` index on `sessions(last_activity_at DESC)`
    - Create `idx_messages_session_id` index on `messages(session_id)`
    - Implement `downgrade()` that drops indexes first, then `messages` table, then `sessions` table (respecting FK order)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 4.1_

- [ ] 4. Checkpoint - Verify Alembic structure
  - Ensure all tests pass, ask the user if questions arise.
  - Verify `alembic upgrade head` and `alembic downgrade -1` work against a local database
  - Verify `alembic current` and `alembic history` produce expected output

- [ ] 5. Refactor `src/db/pool.py`
  - [ ] 5.1 Remove all inline DDL from `init_db()`
    - Remove all `CREATE TABLE`, `ALTER TABLE`, and `CREATE INDEX` statements
    - Keep pool creation via `get_pool()`
    - Preserve the `get_pool()`, `init_db()`, and `close_pool()` public interface without signature changes
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ] 5.2 Add `_check_schema()` function
    - Define `_EXPECTED_TABLES = ("sessions", "messages")` module-level tuple
    - Query `pg_tables` to verify expected application tables exist
    - Verify `alembic_version` table exists and contains at least one revision row
    - Raise `RuntimeError` with actionable message instructing to run `alembic upgrade head` on any failure
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ] 5.3 Wire `_check_schema()` into `init_db()`
    - Call `_check_schema(pool)` after pool creation but before returning the pool
    - Update docstring to reflect new behavior
    - _Requirements: 6.6_

- [ ] 6. Checkpoint - Verify refactored pool.py
  - Ensure all tests pass, ask the user if questions arise.
  - Verify `src/db/sessions.py` and `src/db/messages.py` remain unchanged
  - Verify `src/api/main.py` lifespan still calls `init_db()` without changes
  - _Requirements: 3.4, 3.5_

- [ ] 7. Create test database fixture
  - [ ] 7.1 Create `tests/integration/conftest.py` with session-scoped fixture
    - Implement `_derive_test_db_url()` to append `_test` to the database name from `DATABASE_URL`
    - Implement `_maintenance_url()` to point at the `postgres` maintenance database
    - Create session-scoped `test_db` fixture that: creates temp database, runs `alembic upgrade head`, yields asyncpg pool, drops database on teardown
    - Terminate other connections before dropping the test database
    - Mark integration tests to be skipped when no database is available
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 8. Write integration tests
  - [ ] 8.1 Write integration tests for migration upgrade
    - Verify `alembic upgrade head` creates `sessions` and `messages` tables with correct columns, types, and defaults
    - Verify both indexes are created (`idx_sessions_last_activity`, `idx_messages_session_id`)
    - _Requirements: 2.6, 5.1_

  - [ ] 8.2 Write integration tests for migration downgrade and round-trip
    - Verify `alembic downgrade -1` removes all application tables and indexes
    - Verify downgrade-then-upgrade round trip produces identical schema to upgrade alone
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ] 8.3 Write integration tests for schema drift detection
    - Verify `_check_schema()` passes against a fully migrated test database
    - Verify `_check_schema()` raises `RuntimeError` against an empty database (before migrations)
    - Verify error messages include instruction to run `alembic upgrade head`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ] 8.4 Write integration tests for Alembic CLI commands
    - Verify `alembic current`, `alembic history`, and `alembic revision` work correctly
    - _Requirements: 5.3, 5.4, 5.5_

- [ ] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - Run `python -m pytest` to verify no regressions
  - Run `ruff check .` to verify no lint issues

## Notes

- No property-based tests are included — the design explicitly assessed PBT as not applicable for this feature
- All integration tests run against an isolated temporary database (never the main application database)
- The project continues to use asyncpg directly for all runtime queries — SQLAlchemy is only an Alembic dependency
- Checkpoints ensure incremental validation at key milestones
- Each task references specific requirements for traceability
