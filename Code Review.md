# Code Review — Deep Research Assistant

Review Date: 2026-05-14

## Summary

The fixes from the previous review are mostly verified. The repository now has Alembic migrations, the old `citation_agent.py` file is gone, request DTOs cap research/chat input length, the chat endpoint avoids the double session fetch, Ruff is clean, and the full test suite passes when the virtual environment is activated.

The remaining concerns are mostly production-readiness issues: request-scoped state is still stored on a shared `ResearchManager`, email delivery is still enabled by default with real address fallbacks, and expensive research requests have no admission control. A few cleanup items remain in docs/config and test configuration.

---

## Strengths

1. **Layered architecture remains clear** — API routes, orchestration, DB access, agents, streaming, export, and models are separated into focused packages.
2. **Alembic migration flow is now in place** — startup no longer executes DDL; `init_db()` verifies expected tables and `alembic_version` before serving requests.
3. **API validation improved** — `ResearchStartRequest.query` and `ChatRequest.message` now use `max_length=2000`.
4. **Chat endpoint DB fix is verified** — `src/api/chat.py` loads the session once and passes the prefetched row into `ResearchManager.load_session()`.
5. **Export coverage is strong** — Markdown, PDF, DOCX, router, service, and renderer behavior are covered by unit, integration, and property-based tests.
6. **Lint and tests are in good shape** — `ruff check .` passes and the activated-venv pytest run reports `371 passed`.
7. **Safe SQL is preserved** — runtime DB queries continue to use asyncpg parameters rather than SQL string interpolation.
8. **`.env` is gitignored** — the earlier committed-secret class of issue remains resolved.

---

## Issues

### High Priority

#### 1. Shared mutable `ResearchManager` is still not concurrency-safe

**Files:** `src/api/main.py:22`, `src/core/research_manager.py:49-61`, `src/core/research_manager.py:281-303`, `src/core/research_manager.py:358-392`

The application still stores one `ResearchManager` instance in `app.state`, and that instance still owns mutable request/session fields: `report`, `search_results`, `last_query`, `session_usage`, `current_session_id`, `search_mode`, and `cost_effective_search`.

Two concurrent research or chat streams can overwrite each other's state. For example, one `/api/research/start` request can reset or replace `current_session_id` while another request is still writing messages or updating cost summaries. The chat endpoint also hydrates that same shared object before streaming, so concurrent chats against different sessions can race on `self.report`, `self.last_query`, and `self.session_usage`.

This is still acceptable only for a single-user, one-request-at-a-time workflow. It is the main blocker for multi-user or multi-tab use.

**Fix:** Make `ResearchManager` request-scoped or move mutable session state into a per-run context object passed through `run()`, `chat()`, `_insert_message()`, `_update_session()`, search, writing, and cost tracking. Keep the shared object, if any, limited to immutable dependencies such as the DB pool.

#### 2. Email delivery is still enabled by default with real address fallbacks [FIXED]

**Files:** `src/config/settings.py:29-30`, `src/core/research_manager.py:450-451`, `src/agents/email_agent.py:16-32`

The previous review marked hardcoded email config as fixed, but the current code only made the values env-overridable:

```python
RECIPIENT = os.getenv("EMAIL_RECIPIENT", "lchanio@echyperion.com")
SENDER = os.getenv("EMAIL_SENDER", "proklos+ses@gmail.com")
```

If a deployment forgets to set `EMAIL_RECIPIENT` or `EMAIL_SENDER`, research completion still invokes `send_email()` unconditionally and attempts SES delivery using those real fallback addresses. That is surprising behavior for any environment other than the original developer's.

There is also no explicit `EMAIL_ENABLED` gate, and `ResearchManager.send_email()` prints "Email sent" after the agent run regardless of whether the underlying SES tool returned `{"status": "error"}`.

**Fix:** Default `RECIPIENT` and `SENDER` to empty strings, add an explicit `EMAIL_ENABLED=false` default, skip email delivery unless enabled and fully configured, and surface failed delivery as a warning/progress event rather than an unconditional success message.

---

### Medium Priority

#### 3. Expensive research endpoint has no rate limit or admission control

**File:** `src/api/research.py:12-23`

`POST /api/research/start` immediately starts a streaming research pipeline. Each accepted request can trigger planning, multiple searches, report writing, fact checking, report editing, title generation, email generation, and external tool calls. The endpoint has input length validation, but no per-client throttling, queueing, authentication, maximum concurrent job count, or cancellation cleanup beyond disconnect checks in the stream adapter.

This is a cost and availability risk if the API is exposed beyond trusted local use.

**Fix:** Add at least a simple concurrency limit for active research jobs, and use authentication plus per-client rate limiting before public or team deployment. Return `429` or `503` when capacity is exhausted.

#### 4. Pipeline logging still uses `print()` throughout long-running workflows

**Files:** `src/core/research_manager.py:369-374`, `src/core/research_manager.py:510-515`, `src/agents/verification_tools.py`, `src/agents/email_agent.py:29-32`

The codebase still emits progress, trace URLs, errors, and cost summaries through `print()`. This matches the current project style, but it limits production observability: there are no log levels, no structured context, no request/session correlation, and no easy way to suppress verbose output while keeping warnings and errors.

**Fix:** Introduce module-level `logging.getLogger(__name__)` loggers. Keep user-facing SSE progress yields separate from operational logs.

#### 5. Model names and cost rates remain compile-time constants

**File:** `src/config/settings.py:14-26`, `src/config/settings.py:64-79`

All model names and token/tool cost assumptions are hardcoded in `settings.py`. That makes model rollout, emergency fallback, and pricing updates require a code change. Cost summaries can also silently become stale when provider pricing changes.

**Fix:** Read model names from env vars with current values as defaults. For costs, either move rates into env/config with a "last reviewed" comment or clearly label cost summaries as estimates.

---

### Low Priority

#### 6. Stale citation references remain after deleting `citation_agent.py` [FIXED]

**Files:** `README.md:65`, `src/config/settings.py:22`

The dead `src/agents/citation_agent.py` file was removed, but the README tree still lists it and `CITATION_MODEL` remains as an unused setting. This is small, but it makes the documented module map and config surface less trustworthy.

**Fix:** Remove the README entry and delete `CITATION_MODEL` unless a new citation module is planned.

#### 7. Markdown export reports PDF rendering failures [FIXED]

**File:** `src/export/router.py:104-105`

The Markdown export endpoint catches `RenderError` and returns `"PDF rendering failed"`. This is a copy/paste error from the PDF route. It only affects an error response path, but it would mislead API clients and debugging.

**Fix:** Change the Markdown route message to `"Markdown rendering failed"` or a generic `"Export rendering failed"`.

#### 8. Pytest integration marker is not registered [FIXED]

**File:** `tests/integration/test_migrations.py:136`, `tests/integration/test_migrations.py:376`, `tests/integration/test_migrations.py:545`, `tests/integration/test_migrations.py:691`

The full test run passes, but pytest emits `PytestUnknownMarkWarning` for `@pytest.mark.integration` because there is no pytest config registering the marker. This adds warning noise and can break stricter CI configurations that treat warnings as errors.

**Fix:** Add a minimal `pytest.ini` or equivalent config with:

```ini
[pytest]
markers =
    integration: tests that require PostgreSQL/Alembic integration resources
```

---

## Verified Previous Issues

| Previous issue | Current status |
|---|---|
| Shared mutable `ResearchManager` | Still open |
| `citation_agent.py` dead code | Fixed, with stale README/config cleanup remaining |
| Hardcoded email config | Partially fixed; env overrides added, unsafe real fallbacks remain |
| Inline DDL migrations in `pool.py` | Fixed with Alembic and schema drift checks |
| No upper bound on query/message length | Fixed |
| Double database fetch in chat endpoint | Fixed |
| Unused public `search()` method | Fixed |
| `print()` pipeline logging | Still open |
| Model names/costs not env-overridable | Still open |
| DOCX property test failure | Fixed |
| Ruff linting errors | Fixed |
| No direct core orchestration coverage | Fixed for pure `ResearchManager` helpers; LLM-heavy orchestration remains mostly integration/manual territory |

---

## Test Suite Results

Commands run:

```bash
.venv/bin/ruff check .
source .venv/bin/activate && python -m pytest
```

Results:

```text
Ruff: All checks passed
Pytest: 371 passed, 5 warnings in 14.31s
```

Notes:

- Running `.venv/bin/python -m pytest` without activating the virtualenv caused migration tests to fail because subprocess calls to `alembic` could not find `.venv/bin/alembic` on `PATH`.
- Activating the virtualenv first resolved that issue.
- The remaining warnings are `PytestUnknownMarkWarning` for the unregistered `integration` marker plus one asyncio event-loop deprecation warning in the migration fixture.

---

## Security Posture

| Item | Status |
|---|---|
| `.env` in `.gitignore` | ✓ Resolved |
| Parameterized SQL queries | ✓ Clean |
| Alembic-managed schema | ✓ Present |
| API input validation with max length caps | ✓ Present |
| Hardcoded committed secrets | ✓ No tracked `.env` found |
| Hardcoded email fallback addresses | ✗ Present |
| Email delivery opt-in gate | ✗ Present |
| Rate limiting / admission control on research endpoint | ✗ Missing |
| Shared request/session state isolation | ✗ Missing |
