# AGENTS.md

## Scope

- Applies to the entire repository (worktree: `export-formats` branch).
- No nested AGENTS.md files currently exist.

## Repo Summary

- Python research assistant using OpenAI Agents SDK with a FastAPI REST backend.
- Key entrypoint: `uvicorn src.api.main:app` (FastAPI server).
- Gradio thin client: `gradio_app.py` (consumes the FastAPI API via HTTP/SSE; includes export UI).
- Core orchestration: `src/core/research_manager.py` with async pipelines.
- Data models use Pydantic in `src/models/domain.py` (domain) and `src/models/api.py` (DTOs).
- Configuration constants and env loading live in `src/config/settings.py`.
- Quality & bias analysis is available via the Q&A flow (`/quality`, `/bias`).
- Cost-effective search routing between OpenAI WebSearch and Brave Search API.
- Deterministic Markdown and PDF export via `src/export/` (no LLM involved).

## Cursor/Copilot Rules

- No `.cursorrules`, `.cursor/rules/`, or `.github/copilot-instructions.md` found.
- If added later, merge those rules into this file.

## Environment Setup

- Create and activate a Python virtual environment.
- Install dependencies:
  - `pip install -r requirements.txt`
- Configure environment:
  - Create `.env` with required keys (see `README.md`).

## Dependency Notes

- Core libraries: `fastapi`, `uvicorn`, `sse-starlette`, `openai-agents`, `asyncpg`.
- Pydantic v2 is used for data models and validation.
- Async HTTP clients (`aiohttp`, `httpx`) are used in search agents and the Gradio thin client.
- Optional integrations: email (`sendgrid`), Slack (`slack_sdk`).
- `hypothesis` and `pytest-asyncio` are used for property-based and async tests.
- `weasyprint` and `markdown` are used by `src/export/` for PDF rendering (no LLM).
- Keep dependency additions minimal and update `requirements.txt`.

## Build / Run Commands

- Start the FastAPI server:
  - `uvicorn src.api.main:app --reload`
- Run the Gradio thin client (requires the FastAPI server to be running):
  - `python gradio_app.py`
- There is no build step (pure Python).

## Runtime Configuration

- `.env` is loaded in `src/api/main.py` via `load_dotenv(override=True)` during lifespan startup.
- Ensure `OPENAI_API_KEY` and `DATABASE_URL` are set before running.
- Network access is required for search agents and model calls.
- Export configuration (optional, read at request time):
  - `EXPORT_DIR` — server-side directory for `delivery_mode=url` exports (default: `./exports`).
  - `EXPORT_BASE_URL` — URL prefix returned in export URL responses (default: `/exports`).
- If adding new integrations, document their env vars in `README.md`.

## Lint / Format Commands

- Linting uses Ruff:
  - Full lint: `ruff check .`
  - Fixable issues: `ruff check . --fix`
- Formatting:
  - `ruff format .` (only run if change scope is large or requested)

## Test Commands

- Run all tests:
  - `python -m pytest`
- Run a specific test file:
  - `python -m pytest tests/path/to/test_file.py`
- Run a specific test:
  - `python -m pytest tests/path/to/test_file.py::test_name`
- Tests live in the `tests/` directory.

## Package Structure

```
src/
├── api/           # FastAPI routes and app bootstrap
│   ├── main.py        # App + lifespan (pool init, ResearchManager)
│   ├── research.py    # POST /api/research/start (SSE)
│   ├── chat.py        # POST /api/chat (SSE)
│   ├── sessions.py    # GET/DELETE /api/sessions, cost endpoint
│   └── dependencies.py # get_pool, get_research_manager
├── core/          # Orchestration
│   ├── research_manager.py  # ResearchManager (no UI imports)
│   └── usage_tracker.py     # ContextVar-based token tracking
├── agents/        # All AI agent modules (stateless)
├── models/
│   ├── domain.py  # Pydantic domain models
│   └── api.py     # Request/Response DTOs + SSE event models
├── db/
│   ├── pool.py    # asyncpg pool lifecycle
│   ├── sessions.py # Session CRUD queries
│   └── messages.py # Message insert/fetch queries
├── export/        # Deterministic export pipeline (no LLM)
│   ├── router.py      # GET /api/export/{id}/markdown, /pdf
│   ├── service.py     # Fetch session + messages, build DocumentParts, delegate to renderers
│   ├── models.py      # ExportFormat, DeliveryMode, DocumentParts, ExportResult, ExportUrlResponse
│   ├── errors.py      # SessionNotFoundError, ReportNotReadyError, RenderError
│   └── renderers/
│       ├── markdown.py  # Pure render(parts) → str
│       └── pdf.py       # render(parts) → bytes via markdown → HTML → weasyprint
├── streaming/
│   └── sse.py     # SSE event formatting + async generator adapters
└── config/
    └── settings.py # All constants + env loading (incl. EXPORT_DIR, EXPORT_BASE_URL)
```

## Code Style (Python)

- Follow PEP 8 style with 4-space indentation.
- Keep line lengths reasonable (≈ 88–100 chars), but match nearby style.
- Use f-strings for string interpolation.
- Keep comments minimal; favor docstrings on public classes/functions.

## Imports

- Keep all imports at the top of the file.
- Prefer grouping in this order:
  1. Standard library
  2. Third-party
  3. Local (`src.*`)
- Avoid unused imports; remove them during edits.
- Use `src.*` absolute paths for all internal imports (e.g., `from src.config.settings import ...`).

## Typing and Models

- Use type hints for function signatures and attributes.
- Prefer built-in generics (e.g., `list[str]`, `dict[str, int]`).
- Data models should be Pydantic `BaseModel` subclasses.
- Use `Field(...)` for metadata and defaults where appropriate.

## Naming Conventions

- `snake_case` for functions, methods, and variables.
- `PascalCase` for classes and Pydantic models.
- `UPPER_SNAKE_CASE` for module-level constants.

## Async Patterns

- Many flows are async generators (`async def ...` + `yield`).
- Preserve streaming behavior for report generation and Q&A.
- Await `Runner.run(...)` calls and extract outputs via `.final_output_as(...)`.
- Avoid blocking calls inside async methods.

## Agent/Runner Conventions

- Use `Runner.run(...)` for agent execution and collect `context_wrapper.usage`.
- Update usage/cost tracking via `ResearchManager.update_usage_stats` when relevant.
- Pass prompt inputs as clear, labeled strings (e.g., `CLAIMS TO VERIFY:`).
- Keep model names configurable when agents accept them.
- Preserve existing streaming yields for progress updates.

## Error Handling

- Prefer early returns for guard clauses.
- Use clear print statements for pipeline progress (existing style).
- Let exceptions bubble up unless a specific recovery path is required.
- SSE streams catch exceptions and emit an `{"type": "error", "message": "..."}` event before closing.

## Logging / Tracing

- The codebase uses `print` for progress and `trace(...)` for tracing.
- Keep tracing in long-running workflows to preserve debug context.
- Avoid adding new logging frameworks unless asked.

## State and Side Effects

- `ResearchManager` stores report state in memory for Q&A.
- The FastAPI app holds a single `ResearchManager` instance in `app.state`.
- Keep shared state minimal; prefer passing values explicitly.
- Email sending is part of the main pipeline; avoid extra side effects.
- If adding tests, mock network and email calls.

## External Services

- Web search uses OpenAI WebSearch or Brave Search API based on cost-effective toggle.
- Email features depend on `sendgrid` configuration.
- Slack support uses `slack_sdk` / `slack_bolt` when enabled.
- Document any new service credentials in `README.md`.
- Avoid hardcoding secrets in code or prompts.

## Prompts and Agent Inputs

- Prompts are often multi-line triple-quoted strings.
- Preserve spacing and section headers in prompts for readability.
- Keep "CLAIM #" and "SECTION" formats stable if extending prompts.
- Prefer explicit input labels (e.g., `CLAIMS TO VERIFY:`).

## File Organization

- All source code lives under `src/` — do not add new modules at the repo root.
- `gradio_app.py` at the repo root is the only UI entrypoint; it must not import from `src/core/` or `src/agents/` directly.
- `src/export/` is a self-contained package; its router uses only `get_pool` — never `get_research_manager` or any agent module.
- Update `README.md` if new entrypoints or scripts are added.

## Documentation Updates

- Add/adjust `README.md` when changing setup/run commands.
- Avoid adding new Markdown files unless requested.

## Safe Defaults for Agents

- Assume network access may be restricted; keep offline workflows.
- Do not commit changes unless explicitly requested.

## Quick Reference

- API entrypoint: `src/api/main.py` → `uvicorn src.api.main:app`
- Gradio UI: `gradio_app.py` (includes export format dropdown + download button)
- Orchestration: `src/core/research_manager.py`
- Domain models: `src/models/domain.py`
- API DTOs: `src/models/api.py`
- Config: `src/config/settings.py`
- Agents: `src/agents/` (planner, writer, qa, quality, brave_search, etc.)
- DB layer: `src/db/` (pool, sessions, messages)
- SSE streaming: `src/streaming/sse.py`
- Export pipeline: `src/export/` (router, service, renderers, models, errors)
- Tests: `tests/`
- Feature plans and documentation: `docs/`
