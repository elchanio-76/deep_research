# Bugfix Requirements Document

## Introduction

Every `POST /chat` request triggers two separate database round-trips to fetch the
same session row. The handler in `src/api/chat.py` calls
`db_sessions.load_session(pool, body.session_id)` to validate the session and check
for a report, then immediately calls `rm.load_session(str(body.session_id))` which
internally calls `db_sessions.load_session` a second time to hydrate
`ResearchManager` state. The row fetched by the guard check is discarded and the
identical query is re-issued, adding an unnecessary DB round-trip to every chat
message.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a valid `POST /chat` request is received THEN the system issues two
    sequential `SELECT` queries against the `sessions` table for the same
    `session_id` within a single request lifecycle.

1.2 WHEN `db_sessions.load_session` returns a non-`None` row in the guard check
    THEN the system discards that row and calls `db_sessions.load_session` again
    inside `rm.load_session`, fetching the identical data a second time.

1.3 WHEN the session does not exist THEN the system issues one `SELECT` query (the
    guard check returns `None` and the handler raises 404 before the second call),
    so the double-query defect only manifests for valid sessions.

### Expected Behavior (Correct)

2.1 WHEN a valid `POST /chat` request is received THEN the system SHALL issue
    exactly one `SELECT` query against the `sessions` table for the given
    `session_id` per request lifecycle.

2.2 WHEN `db_sessions.load_session` returns a non-`None` row THEN the system SHALL
    reuse that already-fetched row to hydrate `ResearchManager` state without
    issuing a second database query.

2.3 WHEN the session does not exist THEN the system SHALL return a 404 response
    after exactly one `SELECT` query, unchanged from current behavior.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the session is not found THEN the system SHALL CONTINUE TO return HTTP 404
    with the detail `"Session not found"`.

3.2 WHEN the session exists but has no `report_markdown` THEN the system SHALL
    CONTINUE TO return HTTP 404 with the detail
    `"No report available for this session"`.

3.3 WHEN the session is valid and has a report THEN the system SHALL CONTINUE TO
    hydrate `ResearchManager` state (including `current_session_id`, `last_query`,
    `search_mode`, `cost_effective_search`, `session_usage`, and `report`) from the
    session row.

3.4 WHEN the session is valid and has a report THEN the system SHALL CONTINUE TO
    stream the chat response as an SSE event source.

3.5 WHEN `rm.load_session` is called from other callers (e.g., the Gradio thin
    client) THEN the system SHALL CONTINUE TO fetch the session row from the
    database and hydrate state correctly.

---

## Bug Condition

```pascal
FUNCTION isBugCondition(request)
  INPUT: request of type ChatRequest with a valid session_id
  OUTPUT: boolean

  session_row ← db_sessions.load_session(pool, request.session_id)
  RETURN session_row IS NOT NULL
END FUNCTION
```

### Fix Checking Property

```pascal
// Property: Fix Checking — single DB round-trip per chat request
FOR ALL request WHERE isBugCondition(request) DO
  db_call_count ← count_db_calls_during(chat_handler'(request))
  ASSERT db_call_count = 1
END FOR
```

### Preservation Property

```pascal
// Property: Preservation Checking — observable HTTP behavior unchanged
FOR ALL request DO
  response_before ← chat_handler(request)   // F  — before fix
  response_after  ← chat_handler'(request)  // F' — after fix
  ASSERT http_status(response_before) = http_status(response_after)
  ASSERT response_body_equivalent(response_before, response_after)
END FOR
```
