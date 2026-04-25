# Implementation Plan: FastAPI Backend Refactor

## Overview

Refactor the monolithic Gradio-coupled research assistant into a layered FastAPI backend. Work proceeds in a git worktree on a `fastapi-refactor` branch. The flat repo layout is reorganized into a `src/` package tree with clear module boundaries: API routes, core orchestration, agents, models, database, streaming, and configuration. All existing agent logic, prompts, and model configurations are preserved unchanged.

## Tasks

- [ ] 1. Create git worktree and initialize package structure
  - [x] 1.1 Create git worktree on `fastapi-refactor` branch in a sibling directory
    - Run `git worktree add ../deep-research-fastapi fastapi-refactor` (creating the branch if needed)
    - All subsequent tasks are performed inside the worktree
    - _Requirements: 1.1, 1.2_

  - [x] 1.2 Create `src/` package skeleton with all `__init__.py` files
    - Create directories: `src/`, `src/api/`, `src/core/`, `src/agents/`, `src/models/`, `src/db/`, `src/streaming/`, `src/config/`
    - Create empty `__init__.py` in each package
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.9_

  - [x] 1.3 Install new dependencies
    - Add `fastapi`, `uvicorn`, `sse-starlette`, `hypothesis`, `httpx`, `pytest`, `pytest-asyncio` to `requirements.txt` (skip any already present)
    - Run `pip install -r requirements.txt`
    - _Requirements: 3.1_

- [ ] 2. Relocate configuration and domain models
  - [x] 2.1 Move `config.py` → `src/config/settings.py`
    - Copy all constants and env loading from `config.py` into `src/config/settings.py`
    - Re-export key names from `src/config/__init__.py` for convenience
    - _Requirements: 2.7_

  - [x] 2.2 Move `new_models.py` → `src/models/domain.py`
    - Copy all Pydantic models as-is from `new_models.py` into `src/models/domain.py`
    - Update the import of `FACT_CHECK_CONFIDENCE_THRESHOLD` to reference `src.config.settings`
    - _Requirements: 2.4_

  - [x] 2.3 Create `src/models/api.py` with Request/Response DTOs and SSE event models
    - Define `ResearchStartRequest`, `ChatRequest`, `ChatMessage` request DTOs
    - Define `SessionSummary`, `SessionDetail`, `CostSummary` response DTOs
    - Define `SSEEvent`, `ProgressEvent`, `ReportEvent`, `CostEvent`, `ChunkEvent`, `ErrorEvent`, `CompleteEvent` models
    - Apply Pydantic validation: `query` min_length=1, `search_mode` pattern constraint, `role` pattern constraint
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [x] 2.4 Write property test for Request DTO validation (Property 2)
    - **Property 2: Request DTO validation accepts valid inputs and rejects invalid inputs**
    - Use `hypothesis` to generate random valid and invalid `ResearchStartRequest` and `ChatRequest` payloads
    - Verify valid inputs are accepted without `ValidationError`, invalid inputs raise `ValidationError`
    - **Validates: Requirements 10.1, 10.2, 10.6**

- [x] 3. Relocate agent modules into `src/agents/`
  - [x] 3.1 Copy all agent files into `src/agents/`
    - Copy: `search_agent.py`, `brave_search_agent.py`, `brave_search_tool.py`, `planner_agent.py`, `writer_agent.py`, `editor_agent.py`, `qa_agent.py`, `quality_agent.py`, `claim_extraction_agent.py`, `fact_check_planner_agent.py`, `verification_tools.py`, `email_agent.py`, `session_title_agent.py`, `adaptive_search_planner.py`, `citation_agent.py`
    - Update all internal imports to use `src.config.settings` instead of `config`
    - Update all internal imports to use `src.models.domain` instead of `new_models`
    - Update cross-agent imports to use `src.agents.*` paths (e.g., `from src.agents.search_agent import search_agent`)
    - Update `src.core.usage_tracker` imports where agents reference `usage_tracker`
    - Preserve all agent logic, prompt text, and output types unchanged
    - _Requirements: 2.3, 11.1, 11.2, 11.3_

  - [x] 3.2 Move `usage_tracker.py` → `src/core/usage_tracker.py`
    - Copy as-is, update import of `SessionUsage` to `src.models.domain`
    - _Requirements: 2.8_

- [x] 4. Checkpoint
  - Verify all `src/` packages are importable: `python -c "import src; import src.agents; import src.models; import src.config; import src.core"`
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Extract database layer into `src/db/`
  - [x] 5.1 Create `src/db/pool.py` with connection pool management
    - Implement `init_db()`, `get_pool()`, `close_pool()` extracted from `db.py`
    - Include all `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE` DDL statements
    - Import pool config from `src.config.settings`
    - _Requirements: 2.5, 12.1_

  - [x] 5.2 Create `src/db/sessions.py` with session query functions
    - Implement `create_session()`, `update_session()`, `list_sessions()`, `load_session()`, `delete_session()`
    - All functions accept `pool: asyncpg.Pool` as first parameter
    - Extract SQL from `ResearchManager._create_session`, `_update_session`, `list_sessions`, `load_session`
    - _Requirements: 12.2, 12.4_

  - [x] 5.3 Create `src/db/messages.py` with message query functions
    - Implement `insert_message()`, `fetch_chat_messages()`
    - All functions accept `pool: asyncpg.Pool` as first parameter
    - Extract SQL from `ResearchManager._insert_message` and the chat message fetch in `load_session`
    - _Requirements: 12.3, 12.4_

- [x] 6. Refactor ResearchManager into `src/core/research_manager.py`
  - [x] 6.1 Create `src/core/research_manager.py` with pool-accepting constructor
    - Copy `ResearchManager` class, change `__init__` to accept `pool: asyncpg.Pool` parameter
    - Remove `_get_pool()` method that called `init_db()`
    - Replace all inline SQL in `_create_session`, `_update_session`, `_insert_message`, `list_sessions`, `load_session` with calls to `src.db.sessions` and `src.db.messages` functions, passing `self.pool`
    - Update all agent imports to `src.agents.*` paths
    - Update model imports to `src.models.domain`
    - Update config imports to `src.config.settings`
    - Ensure no `gradio` imports exist
    - Preserve `run()` and `chat()` as async generators yielding strings
    - _Requirements: 2.2, 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 7. Implement SSE streaming layer
  - [x] 7.1 Create `src/streaming/sse.py` with event formatting and stream adapters
    - Implement `format_event()`, `format_progress()`, `format_report()`, `format_cost()`, `format_chunk()`, `format_error()`, `format_complete()`
    - Each function returns a JSON string with `type` field and appropriate payload field
    - Implement `research_event_stream()` async generator that wraps `ResearchManager.run()` yields into SSE events
    - Implement `chat_event_stream()` async generator that wraps `ResearchManager.chat()` yields into SSE events
    - Implement `create_sse_response()` helper returning `EventSourceResponse` with ping=15
    - Handle client disconnect via `request.is_disconnected()`
    - Catch exceptions and emit error events before closing stream
    - _Requirements: 2.6, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_

  - [x] 7.2 Write property test for SSE event formatting round-trip (Property 1)
    - **Property 1: SSE event formatting round-trip**
    - Use `hypothesis` to generate random strings and dicts for each event type
    - Verify each `format_*()` output is valid JSON with correct `type` field and matching payload
    - Verify `format_complete()` produces JSON with only the `type` field
    - **Validates: Requirements 4.6, 8.5, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7**

  - [x] 7.3 Write unit tests for SSE event formatting
    - Test each `format_*()` function with known inputs and verify JSON structure
    - Test edge cases: empty strings, special characters, large payloads
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_

- [x] 8. Checkpoint
  - Verify SSE formatting functions work: `python -c "from src.streaming.sse import format_progress, format_complete; print(format_progress('test'))"`
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Build FastAPI application and route modules
  - [x] 9.1 Create `src/api/dependencies.py` with shared FastAPI dependencies
    - Implement `get_pool(request)` returning `request.app.state.pool`
    - Implement `get_research_manager(request)` returning `request.app.state.research_manager`
    - _Requirements: 8.4_

  - [x] 9.2 Create `src/api/main.py` with FastAPI app and lifespan
    - Define `lifespan` async context manager: load `.env`, call `init_db()`, create `ResearchManager(pool=pool)`, store both in `app.state`, close pool on shutdown
    - Create `FastAPI(title="Deep Research API", lifespan=lifespan)`
    - Register research, chat, and sessions routers with `/api` prefix
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 9.3 Create `src/api/research.py` with research endpoint
    - Implement `POST /research/start` accepting `ResearchStartRequest` body
    - Return `EventSourceResponse` wrapping `research_event_stream()`
    - Pydantic validation returns 422 for invalid input automatically
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 9.4 Create `src/api/chat.py` with chat endpoint
    - Implement `POST /chat` accepting `ChatRequest` body
    - Load session from DB, verify report exists (404 if not)
    - Return `EventSourceResponse` wrapping `chat_event_stream()`
    - Support quality/bias analysis routing via existing `is_quality_request()` logic
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 9.5 Create `src/api/sessions.py` with session management endpoints
    - Implement `GET /sessions` returning list of `SessionSummary`
    - Implement `GET /sessions/{session_id}` returning `SessionDetail` (404 if not found)
    - Implement `DELETE /sessions/{session_id}` returning 204 (404 if not found)
    - Implement `GET /sessions/{session_id}/cost` returning `CostSummary` (404 if not found)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2_

  - [x] 9.6 Write property test for invalid request rejection (Property 3)
    - **Property 3: Invalid request bodies produce HTTP 422**
    - Use `hypothesis` to generate invalid JSON bodies for `/api/research/start` and `/api/chat`
    - Use `httpx.AsyncClient` with FastAPI `TestClient` to POST invalid bodies
    - Verify HTTP 422 status with validation error details in response
    - **Validates: Requirements 4.7, 10.6**

  - [x] 9.7 Write integration tests for API endpoints
    - Test research endpoint with mocked `ResearchManager.run()` yielding known strings, verify SSE event sequence
    - Test chat endpoint with mocked `ResearchManager.chat()`, verify chunk events and complete event
    - Test session CRUD: list, get, delete against test fixtures
    - Test 404 responses for non-existent sessions
    - _Requirements: 4.1, 5.1, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2_

- [x] 10. Checkpoint
  - Verify the FastAPI app starts without import errors: `python -c "from src.api.main import app; print(app.title)"`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Wire Gradio thin client for re-integration
  - [x] 11.1 Create Gradio thin client that consumes FastAPI endpoints
    - Create `gradio_app.py` at repo root (or `src/ui/gradio_app.py`)
    - Use `httpx` to call REST endpoints and consume SSE streams
    - Preserve existing UI layout: query input, search mode dropdown, cost-effective toggle, report display, cost summary, session list, Q&A chatbot
    - No imports from `src/core/` or `src/agents/` — only HTTP calls to the API
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

- [x] 12. Final checkpoint
  - Verify `uvicorn src.api.main:app` starts without errors
  - Verify no `gradio` imports in `src/core/` or `src/db/`
  - Verify all agent modules importable from `src.agents.*`
  - Verify database functions don't import from `src.core` or `src.agents`
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 2.10, 8.1, 11.1, 12.4_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after major milestones
- Property tests validate the 3 correctness properties from the design document
- All agent logic, prompts, and model configurations are preserved unchanged — this is a purely structural refactoring
- The implementation language is Python (matching the existing codebase and design document)
