# Requirements Document

## Introduction

This specification covers the refactoring of a Python deep research assistant application to decouple the Gradio presentation layer from the agentic analysis layer. The primary deliverable is a FastAPI REST API backend that exposes all current capabilities — research pipeline, Q&A chat, quality/bias analysis, email sending, session management, and cost tracking — via well-defined HTTP endpoints. Long-running research tasks stream real-time progress to clients via Server-Sent Events (SSE). The flat repository layout is reorganized into a proper Python package structure under `src/`. A git worktree is used to isolate refactoring work. Gradio re-integration as a thin client over the new API is a follow-up task.

## Glossary

- **API_Server**: The FastAPI application that serves REST endpoints and SSE streams.
- **Research_Pipeline**: The orchestration flow that plans searches, executes them, writes a report, fact-checks it, optionally edits it, and persists the final result.
- **SSE_Stream**: A Server-Sent Events connection that delivers real-time progress events from a long-running operation to the client.
- **Session**: A persisted research run stored in PostgreSQL, including the report, chat history, usage data, and cost summary.
- **Research_Manager**: The core orchestrator class that coordinates agents, tracks usage, and manages session state.
- **Agent_Module**: A stateless Python module that defines one or more AI agents (e.g., planner, writer, QA) using the OpenAI Agents SDK.
- **Request_DTO**: A Pydantic model representing an inbound API request body.
- **Response_DTO**: A Pydantic model representing an outbound API response body.
- **SSE_Event**: A JSON-formatted event sent over an SSE connection, with a `type` field indicating the event kind (progress, report, cost, error, complete).
- **Connection_Pool**: The asyncpg connection pool used for PostgreSQL access.
- **Usage_Tracker**: The context-variable-based system that records per-agent token usage and tool calls within an async task.

## Requirements

### Requirement 1: Git Worktree Isolation

**User Story:** As a developer, I want to perform the refactoring in a git worktree, so that the main branch remains stable while restructuring is in progress.

#### Acceptance Criteria

1. WHEN the refactoring begins, THE Developer SHALL create a git worktree on a new branch named `fastapi-refactor` in a sibling directory.
2. THE Developer SHALL perform all package restructuring and code changes within the worktree, leaving the original working tree unchanged.

### Requirement 2: Package Structure Reorganization

**User Story:** As a developer, I want the flat repository root reorganized into a proper Python package structure, so that modules have clear boundaries and the codebase scales cleanly.

#### Acceptance Criteria

1. THE API_Server source code SHALL reside under `src/api/` as a Python package containing route modules.
2. THE Research_Manager and orchestration logic SHALL reside under `src/core/` as a Python package.
3. All Agent_Module files SHALL reside under `src/agents/` as a Python package, preserving their existing stateless interfaces.
4. All Pydantic data models (existing domain models and new Request_DTO/Response_DTO types) SHALL reside under `src/models/` as a Python package.
5. THE database layer (connection pool management, table initialization, queries) SHALL reside under `src/db/` as a Python package.
6. SSE event formatting and streaming utilities SHALL reside under `src/streaming/` as a Python package.
7. Configuration constants and environment loading SHALL reside under `src/config/` as a Python package.
8. THE Usage_Tracker module SHALL reside under `src/core/` alongside the Research_Manager.
9. A `src/__init__.py` and per-package `__init__.py` files SHALL exist so that all packages are importable.
10. WHEN the reorganization is complete, THE API_Server SHALL start without import errors using `uvicorn src.api.main:app`.

### Requirement 3: FastAPI Application Bootstrap

**User Story:** As a developer, I want a FastAPI application entrypoint that initializes the database pool on startup and tears it down on shutdown, so that the API is ready to serve requests with a managed connection lifecycle.

#### Acceptance Criteria

1. THE API_Server SHALL define a FastAPI application in `src/api/main.py`.
2. WHEN the API_Server starts, THE API_Server SHALL initialize the Connection_Pool and run database table creation before accepting requests.
3. WHEN the API_Server shuts down, THE API_Server SHALL close the Connection_Pool gracefully.
4. THE API_Server SHALL load environment variables from `.env` on startup using `python-dotenv`.
5. THE API_Server SHALL register all route modules (research, chat, sessions) via FastAPI router includes.

### Requirement 4: Research Pipeline Endpoint with SSE Streaming

**User Story:** As an API client, I want to start a research task and receive real-time progress updates via SSE, so that I can display incremental status to the user during the long-running operation.

#### Acceptance Criteria

1. WHEN a POST request is received at `/api/research/start` with a JSON body containing `query` (string, required), `search_mode` (string, optional, default `"no_adaptive"`), and `cost_effective` (boolean, optional, default `false`), THE API_Server SHALL start the Research_Pipeline for the given query.
2. THE API_Server SHALL return an SSE stream (`text/event-stream`) as the response to the research start request.
3. WHILE the Research_Pipeline is running, THE SSE_Stream SHALL emit SSE_Event objects for each pipeline stage: search planning, search execution, adaptive searches, report writing, fact-checking, report editing, email sending, and completion.
4. WHEN the Research_Pipeline completes, THE SSE_Stream SHALL emit an SSE_Event with `type: "report"` containing the final markdown report, followed by an SSE_Event with `type: "cost"` containing the cost summary, followed by an SSE_Event with `type: "complete"`.
5. IF an error occurs during the Research_Pipeline, THEN THE SSE_Stream SHALL emit an SSE_Event with `type: "error"` containing the error message, and close the stream.
6. Each SSE_Event SHALL be a JSON object with at minimum a `type` field and a payload field appropriate to the event type (`message`, `content`, `summary`, or `error` key).
7. THE API_Server SHALL validate the request body using a Request_DTO Pydantic model and return HTTP 422 for invalid input.

### Requirement 5: Q&A Chat Endpoint with SSE Streaming

**User Story:** As an API client, I want to send a question about a generated report and receive the answer streamed back via SSE, so that the chat experience feels responsive.

#### Acceptance Criteria

1. WHEN a POST request is received at `/api/chat` with a JSON body containing `session_id` (UUID string, required), `message` (string, required), and `history` (list of `{role, content}` objects, optional, default `[]`), THE API_Server SHALL run the Q&A flow against the session's report.
2. THE API_Server SHALL return an SSE stream for the chat response.
3. WHILE the Q&A agent is generating a response, THE SSE_Stream SHALL emit SSE_Event objects with `type: "chunk"` containing incremental answer text.
4. WHEN the Q&A response is complete, THE SSE_Stream SHALL emit an SSE_Event with `type: "complete"`.
5. IF no report exists for the given session_id, THEN THE API_Server SHALL return HTTP 404 with a descriptive error message.
6. IF the message triggers a quality or bias analysis (via `/quality`, `/bias` commands or trigger phrases), THE API_Server SHALL route to the quality agent and stream the analysis result.

### Requirement 6: Session Management Endpoints

**User Story:** As an API client, I want to list, load, and delete research sessions, so that I can manage past research runs.

#### Acceptance Criteria

1. WHEN a GET request is received at `/api/sessions`, THE API_Server SHALL return a JSON array of session summaries (id, header, initial_prompt, created_at) ordered by last activity descending.
2. WHEN a GET request is received at `/api/sessions/{session_id}`, THE API_Server SHALL return the full session data including report markdown, cost summary, chat history, search mode, and cost-effective flag.
3. IF the session_id does not exist, THEN THE API_Server SHALL return HTTP 404 with a descriptive error message.
4. WHEN a DELETE request is received at `/api/sessions/{session_id}`, THE API_Server SHALL delete the session and its associated messages from the database and return HTTP 204.
5. IF the session_id for a DELETE request does not exist, THEN THE API_Server SHALL return HTTP 404.

### Requirement 7: Cost Summary Endpoint

**User Story:** As an API client, I want to retrieve the cost summary for a session, so that I can display token usage and estimated costs.

#### Acceptance Criteria

1. WHEN a GET request is received at `/api/sessions/{session_id}/cost`, THE API_Server SHALL return a JSON object containing `total_input_tokens`, `total_output_tokens`, `total_tool_calls`, and `total_cost` for the specified session.
2. IF the session_id does not exist, THEN THE API_Server SHALL return HTTP 404 with a descriptive error message.

### Requirement 8: Research Manager Decoupling

**User Story:** As a developer, I want the Research_Manager to be independent of any UI framework, so that it can be consumed by FastAPI, Gradio, or any other client.

#### Acceptance Criteria

1. THE Research_Manager SHALL have no imports from `gradio` or any presentation framework.
2. THE Research_Manager `run` method SHALL remain an async generator yielding string progress messages, preserving the existing streaming contract.
3. THE Research_Manager `chat` method SHALL remain an async generator yielding string chunks, preserving the existing streaming contract.
4. THE Research_Manager SHALL accept its dependencies (database pool reference, configuration) explicitly rather than relying on module-level global singletons.
5. THE API_Server SHALL instantiate and manage the Research_Manager lifecycle, translating its async generator yields into SSE_Event objects.

### Requirement 9: SSE Event Protocol

**User Story:** As an API client developer, I want a well-defined SSE event format, so that I can reliably parse and display real-time updates.

#### Acceptance Criteria

1. THE SSE_Stream SHALL format each event as a JSON object on a single `data:` line, followed by a blank line, conforming to the SSE specification.
2. THE SSE_Event `type` field SHALL use one of the following values: `"progress"`, `"report"`, `"cost"`, `"chunk"`, `"error"`, `"complete"`.
3. THE `"progress"` event SHALL contain a `message` field with a human-readable status string.
4. THE `"report"` event SHALL contain a `content` field with the full markdown report.
5. THE `"cost"` event SHALL contain a `summary` field with a JSON object of cost data.
6. THE `"chunk"` event SHALL contain a `content` field with an incremental text fragment (used for chat streaming).
7. THE `"error"` event SHALL contain a `message` field with a human-readable error description.
8. THE `"complete"` event SHALL contain no additional payload fields and signal the end of the stream.

### Requirement 10: Request and Response Data Models

**User Story:** As a developer, I want dedicated Pydantic models for API request and response payloads, so that validation is automatic and the API contract is explicit.

#### Acceptance Criteria

1. THE API_Server SHALL define a `ResearchStartRequest` Request_DTO with fields: `query` (str, required), `search_mode` (str, optional, default `"no_adaptive"`, validated against allowed values), `cost_effective` (bool, optional, default `false`).
2. THE API_Server SHALL define a `ChatRequest` Request_DTO with fields: `session_id` (UUID, required), `message` (str, required), `history` (list of `ChatMessage` objects, optional, default `[]`).
3. THE API_Server SHALL define a `SessionSummary` Response_DTO with fields: `id` (UUID), `header` (optional str), `initial_prompt` (str), `created_at` (datetime).
4. THE API_Server SHALL define a `SessionDetail` Response_DTO with fields: `id` (UUID), `header` (optional str), `initial_prompt` (str), `report_markdown` (optional str), `cost_summary` (CostSummary object), `chat_history` (list of ChatMessage), `search_mode` (str), `cost_effective` (bool).
5. THE API_Server SHALL define a `CostSummary` Response_DTO with fields: `total_input_tokens` (int), `total_output_tokens` (int), `total_tool_calls` (int), `total_cost` (float).
6. WHEN a request body fails validation, THE API_Server SHALL return HTTP 422 with a JSON body describing the validation errors (default FastAPI behavior).

### Requirement 11: Existing Agent Module Preservation

**User Story:** As a developer, I want all existing agent modules to be relocated without functional changes, so that the refactoring is purely structural and does not introduce regressions.

#### Acceptance Criteria

1. THE refactoring SHALL relocate all Agent_Module files into `src/agents/` without modifying their internal logic, prompt text, or output types.
2. WHEN agent modules are relocated, THE import paths in Research_Manager and other consumers SHALL be updated to reference the new `src.agents.*` paths.
3. THE stateless nature of all Agent_Module files SHALL be preserved — no instance state or side effects beyond what currently exists.

### Requirement 12: Database Layer Extraction

**User Story:** As a developer, I want the database layer extracted into its own package, so that connection management and queries are cleanly separated from business logic.

#### Acceptance Criteria

1. THE Connection_Pool initialization, table creation, and pool closure functions SHALL reside in `src/db/pool.py`.
2. Session-related database queries (create, update, list, load, delete) SHALL reside in `src/db/sessions.py` as standalone async functions accepting a pool or connection parameter.
3. Message-related database queries (insert, fetch by session) SHALL reside in `src/db/messages.py` as standalone async functions accepting a pool or connection parameter.
4. THE database functions SHALL not import or depend on the Research_Manager or any agent modules.

### Requirement 13: Gradio Re-integration as Thin Client

**User Story:** As a developer, I want to re-integrate the Gradio UI as a thin client that calls the FastAPI backend, so that the UI is decoupled and the backend remains the single source of truth.

#### Acceptance Criteria

1. WHEN the FastAPI backend is verified working, THE Developer SHALL create a Gradio application that consumes the API endpoints instead of directly instantiating Research_Manager.
2. THE Gradio client SHALL use `httpx` or `requests` to call REST endpoints and consume SSE streams for research and chat.
3. THE Gradio client SHALL preserve the existing UI layout: query input, search mode dropdown, cost-effective toggle, report display, cost summary, session list, and Q&A chatbot.
4. THE Gradio client SHALL reside in a separate file (e.g., `src/ui/gradio_app.py` or repo root `gradio_app.py`) and SHALL NOT import any modules from `src/core/` or `src/agents/` directly.
