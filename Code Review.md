# Code Review — Deep Research Assistant

Review Date: 2026-04-30

## Summary

The project has matured significantly since the last review. A proper FastAPI REST backend replaces the former single-file Gradio server, a PostgreSQL persistence layer has been added, and a comprehensive test suite now exists. The old critical-severity issue (API keys committed to version control) is resolved — `.env` is gitignored. The new issues below are architectural and maintainability concerns appropriate to the project's current state.

---

## Strengths

1. **Clean layered architecture** — `src/api/`, `src/core/`, `src/agents/`, `src/models/`, `src/db/`, `src/export/`, `src/streaming/` each own a clear slice of responsibility.
2. **Strong Pydantic v2 modeling** — domain models in `domain.py` use `Field` constraints, `field_validator`, `ConfigDict`, and cross-field validation. API DTOs in `api.py` add pattern-validated enums and `min_length` guards at the boundary.
3. **Substantial test suite** — 9 files, ~2 500 lines, covering API integration, export integration, SSE formatting, property-based (Hypothesis) renderer tests, and DTO validation. Significant improvement over the previous review.
4. **Stateless export pipeline** — `src/export/service.py` receives the pool as a parameter and invokes no LLM. Renderers are pure functions. Error hierarchy (`SessionNotFoundError`, `ReportNotReadyError`, `RenderError`) maps cleanly to HTTP status codes in the router.
5. **Safe SQL** — all DB queries in `src/db/` use asyncpg parameterized statements (`$1`, `$2`, …). No string interpolation into SQL.
6. **ContextVar usage tracking** — `src/core/usage_tracker.py` uses a `ContextVar` so per-request token tracking is coroutine-safe across concurrent async tasks.
7. **SSE disconnect detection** — `research_event_stream` and `chat_event_stream` check `request.is_disconnected()` on each iteration, preventing runaway agent chains after the client drops.
8. **AGENTS.md** — thorough project documentation for context, conventions, and commands.

---

## Issues

### High Priority

#### 1. Shared mutable `ResearchManager` is not concurrency-safe *(known single-user limitation)*

**File:** `src/api/main.py:22`, `src/api/dependencies.py:11`

A single `ResearchManager` instance is stored in `app.state`. The class has mutable instance state: `self.report`, `self.search_results`, `self.last_query`, `self.current_session_id`, `self.session_usage`, etc. Two concurrent `/api/research/start` requests (e.g. two browser tabs) would corrupt each other's state — `reset_session_state()` at the start of `run()` wipes the other in-flight request's counters, and both coroutines then race on `self.current_session_id`, causing A's report to be persisted under B's session.

This does not affect the current single-user sequential use case. It is a pre-requisite to address before adding multi-user support.

**Fix:** Move the mutable fields out of instance state and into local variables scoped to each `run()` / `chat()` invocation, leaving `ResearchManager` holding only the `pool`.

#### 2. `citation_agent.py` is dead code [FIXED]

**File:** `src/agents/citation_agent.py`

The file defines `citation_agent` and `citation_agent_tool` but is not imported anywhere in `src/` or `tests/`. Its functionality was superseded by `verification_tools.py`. It adds ~140 lines of confusion and maintenance burden.

**Fix:** Delete the file.

#### 3. Hardcoded email config in `settings.py` [FIXED]

**File:** `src/config/settings.py:29-30`

```python
RECIPIENT = "lchanio@echyperion.com"
SENDER = "proklos+ses@gmail.com"
```

These are production values committed to source control. Any other deployment of this project will send email to/from the original developer's addresses unless the code is edited.

**Fix:** Read from env vars: `RECIPIENT = os.getenv("EMAIL_RECIPIENT", "")` and `SENDER = os.getenv("EMAIL_SENDER", "")`.

#### 4. Inline DDL migrations in `pool.py` [FIXED]

**File:** `src/db/pool.py:28-75`

`init_db()` runs `CREATE TABLE IF NOT EXISTS` plus several `ALTER TABLE ADD COLUMN IF NOT EXISTS` statements on every application start. This works for early-stage development but is not a migration system: there is no ordering, no rollback, no record of what has been applied, and adding a new column requires inserting another `ALTER TABLE` block into this function. If two server instances start simultaneously, the DDL race is benign now (IF NOT EXISTS) but will break if a future migration is not idempotent.

**Recommendation:** Introduce Alembic (or a lightweight SQL migration runner like `yoyo`) even at low complexity. This is not an immediate blocker, but the current approach does not scale beyond a few more schema changes.

---

### Medium Priority

#### 5. No upper bound on query length [FIXED]

**File:** `src/models/api.py:11`

```python
query: str = Field(..., min_length=1, description="Research query")
```

There is no `max_length`. An adversarial client can submit a multi-megabyte string that propagates through the entire agent pipeline, consuming tokens and potentially causing OOM or timeout issues. `message` in `ChatRequest` has the same gap.

**Fix:** Add `max_length=2000` (or similar reasonable cap) to both fields.

#### 6. Double database fetch in the chat endpoint [FIXED]

**File:** `src/api/chat.py:25-36`

The handler calls `db_sessions.load_session(pool, body.session_id)` to validate the session exists, then immediately calls `rm.load_session(str(body.session_id))` which calls `db_sessions.load_session` a second time internally. This is an unnecessary round-trip on every chat message.

**Fix:** Pass the already-fetched row to `load_session`, or combine the guard and hydration into a single DB call.

#### 7. Unused public method `search()` [FIXED]

**File:** `src/core/research_manager.py` (near line 470)

The standalone `search(item)` method is never called — all search routing now goes through `_search_with_routing()` and `perform_searches()`. It is a public method on the class, so it creates a false impression of the API surface.

**Fix:** Delete the method.

#### 8. `print()` used for all pipeline logging

**File:** `src/core/research_manager.py` (31 occurrences), `src/agents/` (18 more)

Progress, cost summaries, and error context are emitted via `print()`. In production, these go to stdout with no level, no timestamp, and no structured format. There is no way to suppress debug noise or filter by severity.

**Recommendation:** Replace with `import logging; logger = logging.getLogger(__name__)`. Use `logger.info` for progress and `logger.warning`/`logger.error` for failures. This is noted in AGENTS.md as intentional ("existing style") but worth revisiting before any production deployment.

#### 9. `MODEL_COSTS` and model names are not env-overridable

**File:** `src/config/settings.py:17-26, 58-63`

Model identifiers (e.g. `PLANNER_MODEL = "gpt-5"`) and cost rates are compile-time constants. When OpenAI renames or retires a model, every model constant requires a code change and redeploy. Cost rates go stale immediately when pricing changes.

**Recommendation:** Read model names from env vars with sensible defaults. Model costs are harder — consider either accepting staleness and noting it in a comment, or fetching from a pricing API at startup.

---

### Low Priority

#### 10. One failing property-based test [FIXED]

**File:** `tests/test_property_export_renderers.py:270`

`test_property_6_output_filename_pattern` asserts that filenames end with `.md` or `.pdf`, but `ExportFormat` now has three values (`markdown`, `pdf`, `docx`). Hypothesis generates `docx` inputs and the test assertion fails with `expected "report-<id>.pdf", got "report-<id>.docx"`.

**Fix:** Update the `expected_ext` logic to cover all three formats.

#### 11. Ruff linting errors (3 sources) [FIXED]

**Files:** `src/db/sessions.py:1`, `tests/test_api_integration.py:189`, `tests/test_property_export_renderers.py:260-363`

- `src/db/sessions.py` — unused `import json` (F401, auto-fixable)
- `tests/test_api_integration.py:189` — f-string with no placeholders (F541, auto-fixable)
- `tests/test_property_export_renderers.py` — 10 E402 errors (module-level imports not at top of file, likely from late-binding to avoid import side effects, but can be restructured)

Run `ruff check . --fix` to resolve the two auto-fixable issues.

#### 12. No test coverage for core orchestration [FIXED]

`research_manager.py` (~500 lines), the individual agents, and the DB layer (`src/db/`) have no direct test coverage. The integration tests mock `ResearchManager` at the boundary, which is appropriate for API tests but means the orchestration logic itself is untested. This is acceptable for now given the LLM dependency, but unit-testable methods like `_normalize_json_payload`, `calculate_total_cost`, `_compute_brave_flags`, and `_build_qa_pairs` in the export service could have tests without any mocking.

---

## Test Suite Results

```
1 failed, 120 passed  (test_property_6_output_filename_pattern)
```

All failures are in the test code, not the production code.

---

## Security Posture

| Item | Status |
|---|---|
| `.env` in `.gitignore` | ✓ Resolved |
| Parameterized SQL queries | ✓ Clean |
| API input validation (type, min_length, pattern) | ✓ Present |
| No query `max_length` cap | ✗ Missing |
| Hardcoded email addresses in source | ✗ Present |
| No rate limiting on research endpoint | ✗ Missing |

The previous critical issue (credentials in VCS) is resolved. The remaining security items are medium-severity.
