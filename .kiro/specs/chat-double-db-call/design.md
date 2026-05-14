# chat-double-db-call Bugfix Design

## Overview

Every `POST /chat` request issues two identical `SELECT` queries against the
`sessions` table for the same `session_id`. The handler in `src/api/chat.py`
calls `db_sessions.load_session(pool, body.session_id)` to validate the session
and check for a report, then discards the returned row and immediately calls
`rm.load_session(str(body.session_id))`, which internally calls
`db_sessions.load_session` a second time to hydrate `ResearchManager` state.

The fix passes the already-fetched row into `ResearchManager` hydration so the
second DB round-trip is eliminated. This requires adding an optional
`prefetched_row` parameter to `rm.load_session` (or a new companion method) so
that the Gradio thin-client call path — which has no pre-fetched row — continues
to work unchanged.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — a `POST /chat`
  request arrives with a `session_id` that resolves to an existing session row,
  causing the handler to issue two `SELECT` queries for the same row.
- **Property (P)**: The desired behavior when the bug condition holds — the
  handler issues exactly one `SELECT` query against `sessions` per request
  lifecycle.
- **Preservation**: All observable HTTP behavior (status codes, response bodies,
  SSE streaming) and `ResearchManager` hydration state that must remain
  identical before and after the fix.
- **`db_sessions.load_session(pool, session_id)`**: The async function in
  `src/db/sessions.py` that executes `SELECT … FROM sessions WHERE id = $1` and
  returns a `dict | None`.
- **`rm.load_session(session_id_str)`**: The async method on `ResearchManager`
  in `src/core/research_manager.py` that calls `db_sessions.load_session`
  internally and hydrates instance state (`current_session_id`, `last_query`,
  `search_mode`, `cost_effective_search`, `session_usage`, `report`).
- **`chat` handler**: The FastAPI route function in `src/api/chat.py` that
  handles `POST /chat` requests.
- **prefetched row**: The `dict` returned by the first call to
  `db_sessions.load_session` inside the `chat` handler, which is currently
  discarded before `rm.load_session` is called.

## Bug Details

### Bug Condition

The bug manifests when a `POST /chat` request is received for a session that
exists in the database. The `chat` handler fetches the session row to perform
guard checks (existence and `report_markdown` presence), then discards the row
and calls `rm.load_session`, which re-fetches the identical row from the
database.

**Formal Specification:**
```
FUNCTION isBugCondition(request)
  INPUT: request of type ChatRequest with a session_id field
  OUTPUT: boolean

  session_row ← db_sessions.load_session(pool, request.session_id)
  RETURN session_row IS NOT NULL
END FUNCTION
```

The bug condition holds for every valid (existing) session. It does **not** hold
when the session is missing, because the handler raises HTTP 404 before
`rm.load_session` is reached.

### Examples

- **Valid session with report** — `session_id` maps to a row with
  `report_markdown` set. Current code: two `SELECT` queries issued. Expected:
  one `SELECT` query, same HTTP 200 + SSE stream.
- **Valid session without report** — `session_id` maps to a row but
  `report_markdown` is `NULL`. Current code: one `SELECT` query (guard raises
  404 before `rm.load_session`). Expected: unchanged — one `SELECT` query,
  HTTP 404 `"No report available for this session"`.
- **Missing session** — `session_id` not found. Current code: one `SELECT`
  query (guard raises 404 immediately). Expected: unchanged — one `SELECT`
  query, HTTP 404 `"Session not found"`.
- **Gradio thin-client call** — `rm.load_session(session_id_str)` called
  directly without a pre-fetched row. Expected: unchanged — one `SELECT` query,
  full hydration of `ResearchManager` state.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- HTTP 404 with detail `"Session not found"` when the session does not exist
  (requirement 3.1).
- HTTP 404 with detail `"No report available for this session"` when the session
  exists but has no `report_markdown` (requirement 3.2).
- `ResearchManager` hydration of all six fields — `current_session_id`,
  `last_query`, `search_mode`, `cost_effective_search`, `session_usage`, and
  `report` — from the session row (requirement 3.3).
- SSE streaming response returned to the caller after successful hydration
  (requirement 3.4).
- `rm.load_session(session_id_str)` called from the Gradio thin client (or any
  other caller without a pre-fetched row) continues to fetch the session row
  from the database and hydrate state correctly (requirement 3.5).

**Scope:**
All request paths that do NOT involve a valid existing session (missing session,
session without report) are completely unaffected by this fix. The Gradio
thin-client call path to `rm.load_session` is also unaffected.

## Hypothesized Root Cause

Based on reading `src/api/chat.py` and `src/core/research_manager.py`:

1. **No row-passing interface on `rm.load_session`**: `ResearchManager.load_session`
   accepts only a `session_id: str` parameter and always calls
   `db_sessions.load_session` internally. There is no way for the `chat` handler
   to pass the already-fetched row into it, so the second query is structurally
   unavoidable with the current API.

2. **Guard check discards the row**: The `chat` handler assigns the result of
   `db_sessions.load_session` to `session` for guard checks, but `session` is
   never passed to `rm.load_session`. The row is simply abandoned after the
   guards pass.

3. **No shared hydration path**: The guard check and `rm.load_session` both
   independently call `db_sessions.load_session` rather than sharing a single
   fetch. Combining them requires either (a) adding an optional `prefetched_row`
   parameter to `rm.load_session`, or (b) extracting the hydration logic into a
   separate method that accepts a row dict directly.

## Correctness Properties

Property 1: Bug Condition - Single DB Round-Trip per Valid Chat Request

_For any_ `POST /chat` request where `isBugCondition` holds (i.e., the
`session_id` resolves to an existing session row), the fixed `chat` handler
SHALL issue exactly one `SELECT` query against the `sessions` table during the
request lifecycle.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - Observable HTTP Behavior Unchanged

_For any_ `POST /chat` request (whether the session exists or not), the fixed
`chat` handler SHALL produce the same HTTP status code and equivalent response
body as the original handler, preserving all guard-check behavior and SSE
streaming for valid sessions.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

## Fix Implementation

### Changes Required

Assuming the root cause analysis is correct:

**File**: `src/core/research_manager.py`

**Method**: `load_session`

**Specific Changes**:

1. **Add optional `prefetched_row` parameter**: Change the signature to
   `async def load_session(self, session_id: str, prefetched_row: dict | None = None)`.
   When `prefetched_row` is not `None`, skip the `db_sessions.load_session` call
   and use the supplied dict directly. When it is `None` (the default), retain
   the existing behavior of fetching from the database — this preserves the
   Gradio thin-client call path.

2. **Guard the DB fetch behind the parameter check**: Inside `load_session`,
   replace the unconditional `session_row = await db_sessions.load_session(...)`
   with:
   ```python
   if prefetched_row is not None:
       session_row = prefetched_row
   else:
       session_row = await db_sessions.load_session(self.pool, session_uuid)
   ```

---

**File**: `src/api/chat.py`

**Function**: `chat`

**Specific Changes**:

3. **Pass the prefetched row to `rm.load_session`**: Replace the call
   `await rm.load_session(str(body.session_id))` with
   `await rm.load_session(str(body.session_id), prefetched_row=session)`.
   The `session` variable already holds the dict returned by the guard-check
   fetch.

4. **Remove the now-redundant standalone `db_sessions.load_session` call** (if
   the guard check is folded into `rm.load_session`): This is an alternative
   approach — move the guard checks into `rm.load_session` or keep them in the
   handler. The preferred approach keeps the guard checks in the handler (for
   clarity) and passes the row through, so no removal is needed; the guard-check
   call becomes the single DB fetch.

5. **No change to the `pool` dependency**: The `pool` parameter is still needed
   by `rm.load_session` for the Gradio path and for other `ResearchManager`
   methods; no dependency injection changes are required.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples
that demonstrate the double-query bug on unfixed code, then verify the fix
eliminates the extra query while preserving all observable behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing
the fix. Confirm the root cause (two calls to `db_sessions.load_session` per
valid chat request).

**Test Plan**: Mock `db_sessions.load_session` with a `MagicMock` / `AsyncMock`
and invoke the `chat` handler with a valid session. Assert that the mock was
called twice. Run these tests on the UNFIXED code to observe the double-call
failure.

**Test Cases**:
1. **Valid session with report** — mock returns a row with `report_markdown`
   set; assert `db_sessions.load_session` call count == 2 (will pass on unfixed
   code, confirming the bug).
2. **Call count after fix** — same setup; assert call count == 1 (will fail on
   unfixed code, confirming the fix is needed).
3. **Missing session** — mock returns `None`; assert call count == 1 (should
   pass on both unfixed and fixed code — boundary condition).

**Expected Counterexamples**:
- `db_sessions.load_session` is called twice for every valid session request.
- Root cause confirmed: `rm.load_session` issues its own independent DB fetch
  regardless of what the handler already fetched.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed
handler issues exactly one DB query.

**Pseudocode:**
```
FOR ALL request WHERE isBugCondition(request) DO
  call_count ← count_calls_to(db_sessions.load_session, during=chat_handler_fixed(request))
  ASSERT call_count = 1
END FOR
```

### Preservation Checking

**Goal**: Verify that for all requests, the fixed handler produces the same
observable HTTP behavior as the original handler.

**Pseudocode:**
```
FOR ALL request DO
  response_before ← chat_handler_original(request)   // F  — before fix
  response_after  ← chat_handler_fixed(request)      // F' — after fix
  ASSERT http_status(response_before) = http_status(response_after)
  ASSERT response_body_equivalent(response_before, response_after)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation
checking because:
- It generates many combinations of session state (various `search_mode` values,
  `cost_effective_search` flags, `usage_jsonb` shapes) automatically.
- It catches edge cases in `ResearchManager` hydration that manual unit tests
  might miss.
- It provides strong guarantees that hydrated state is identical for all valid
  session rows.

**Test Plan**: Observe `ResearchManager` state after calling the original
`rm.load_session(session_id_str)` on unfixed code, then write property-based
tests asserting the same state is produced by the fixed
`rm.load_session(session_id_str, prefetched_row=row)`.

**Test Cases**:
1. **Hydration state preservation** — for any valid session row dict, assert
   that `rm.load_session(id, prefetched_row=row)` sets the same six fields as
   `rm.load_session(id)` (with a DB mock returning the same row).
2. **Gradio path preservation** — call `rm.load_session(session_id_str)` without
   `prefetched_row`; assert the DB is still queried and state is hydrated
   correctly.
3. **404 guard preservation** — for missing sessions, assert HTTP 404 with
   `"Session not found"` is unchanged.
4. **No-report guard preservation** — for sessions with `report_markdown=None`,
   assert HTTP 404 with `"No report available for this session"` is unchanged.

### Unit Tests

- Test `rm.load_session` with `prefetched_row` supplied: assert no DB call is
  made and all six fields are hydrated from the supplied dict.
- Test `rm.load_session` without `prefetched_row`: assert one DB call is made
  (existing behavior preserved).
- Test the `chat` handler with a valid session: assert `db_sessions.load_session`
  is called exactly once after the fix.
- Test edge cases: `prefetched_row` with missing optional fields (e.g., no
  `usage_jsonb`), malformed JSON in `usage_jsonb`.

### Property-Based Tests

- Generate random valid session row dicts (varying `search_mode`, `cost_effective_search`,
  `usage_jsonb`, `report_markdown`) and verify that `rm.load_session` with
  `prefetched_row` produces identical hydration state to `rm.load_session`
  backed by a DB mock returning the same row.
- Generate random `ChatRequest` inputs with valid session IDs and verify that
  the fixed handler always calls `db_sessions.load_session` exactly once.
- Generate random session row dicts and verify that the six hydrated fields
  (`current_session_id`, `last_query`, `search_mode`, `cost_effective_search`,
  `session_usage`, `report`) are set consistently regardless of whether the row
  was pre-fetched or fetched inside `load_session`.

### Integration Tests

- End-to-end `POST /chat` with a real (test) database: assert exactly one DB
  round-trip occurs (use query logging or a spy on `asyncpg`).
- Verify the Gradio thin-client flow: call `rm.load_session(session_id_str)`
  directly against the test DB and assert correct hydration.
- Verify context switching: load one session, then load another, and assert
  state is fully replaced (no bleed-over from the first session).
