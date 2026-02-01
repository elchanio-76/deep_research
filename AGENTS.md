# AGENTS.md

## Scope
- Applies to the entire repository.
- No nested AGENTS.md files currently exist.

## Repo Summary
- Python research assistant using OpenAI Agents SDK + Gradio UI.
- Key entrypoint: `deep_research.py`.
- Core orchestration: `research_manager.py` with async pipelines.
- Data models use Pydantic in `new_models.py`.
- Model defaults and shared constants live in `config.py`.
- Quality & bias analysis is available via the Q&A flow (`/quality`, `/bias`).
- Cost-effective search routing between OpenAI WebSearch and Brave Search API.

## Cursor/Copilot Rules
- No `.cursorrules`, `.cursor/rules/`, or `.github/copilot-instructions.md` found.
- If added later, merge those rules into this file.

## Environment Setup
- Create and activate a Python virtual environment.
- Install dependencies:
  - `pip install -r requirements.txt`
- Configure environment:
  - Create `.env` with `OPENAI_API_KEY=...` (see `README.md`).

## Dependency Notes
- Core libraries include `openai-agents`, `agents`, and `gradio`.
- Pydantic v2 is used for data models and validation.
- Async HTTP clients (`aiohttp`, `httpx`) are installed for search agents.
- Optional integrations include email (`sendgrid`) and Slack (`slack_sdk`).
- Keep dependency additions minimal and update `requirements.txt`.

## Build / Run Commands
- Run the app locally:
  - `python deep_research.py`
- CLI-style usage example (from README):
  - `python -c "from research_manager import ResearchManager; ..."`
- There is no build step (pure Python).

## Runtime Configuration
- `.env` is loaded in `deep_research.py` via `load_dotenv(override=True)`.
- Ensure `OPENAI_API_KEY` is set before running.
- Network access is required for search agents and model calls.
- If adding new integrations, document their env vars in `README.md`.

## Lint / Format Commands
- Linting uses Ruff (dependency listed in `requirements.txt`).
  - Full lint: `ruff check .`
  - Fixable issues: `ruff check . --fix`
- Formatting:
  - No formatter config in repo.
  - If you choose to format, prefer Ruff’s formatter: `ruff format .`
  - Only run formatters if the change scope is large or requested.

## Test Commands
- No tests or test framework found in the repo.
- No default test runner is configured.
- Single-test command: N/A (no tests directory or pytest dependency).
- If tests are added later, prefer `pytest` and document:
  - `python -m pytest`
  - `python -m pytest path/to/test_file.py::test_name`

## Code Style (Python)
- Follow PEP 8 style with 4-space indentation.
- Keep line lengths reasonable (≈ 88–100 chars), but match nearby style.
- Use f-strings for string interpolation.
- Prefer double quotes only when needed (prompts often use triple quotes).
- Keep comments minimal; favor docstrings on public classes/functions.

## Imports
- Keep all imports at the top of the file.
- Prefer grouping in this order when touching a file:
  1) Standard library
  2) Third-party
  3) Local modules
- Avoid unused imports; remove them during edits.
- Keep import names consistent with existing usage (e.g., `Runner`, `Usage`).

## Typing and Models
- Use type hints for function signatures and attributes.
- Prefer built-in generics (e.g., `list[str]`, `dict[str, int]`).
- Data models should be Pydantic `BaseModel` subclasses.
- Use `Field(...)` for metadata and defaults where appropriate.
- Avoid introducing new dataclass types unless needed.

## Naming Conventions
- `snake_case` for functions, methods, and variables.
- `PascalCase` for classes and Pydantic models.
- `UPPER_SNAKE_CASE` for module-level constants.
- Match existing module names (single-purpose `.py` files at repo root).

## Async Patterns
- Many flows are async generators (`async def ...` + `yield`).
- Preserve streaming behavior for report generation and Q&A.
- Await `Runner.run(...)` calls and extract outputs via `.final_output_as(...)`.
- Avoid blocking calls inside async methods.

## Agent/Runner Conventions
- Use `Runner.run(...)` for agent execution and collect `context_wrapper.usage`.
- Update usage/cost tracking via `ResearchManager.update_usage_stats` when relevant.
- Pass prompt inputs as clear, labeled strings (e.g., `CLAIMS TO VERIFY:`).
- Keep model names configurable when agents accept them (see `PlannerAgent`).
- Preserve existing streaming yields for progress updates.

## Error Handling
- Prefer early returns for guard clauses (see `ResearchManager.chat`).
- Use clear print statements for pipeline progress (existing style).
- Let exceptions bubble up unless a specific recovery path is required.
- When adding new error handling, keep it minimal and explicit.

## Logging / Tracing
- The codebase uses `print` for progress and `trace(...)` for tracing.
- Keep tracing in long-running workflows to preserve debug context.
- Avoid adding new logging frameworks unless asked.

## State and Side Effects
- `ResearchManager` stores report state in memory for Q&A.
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
- Keep “CLAIM #” and “SECTION” formats stable if extending prompts.
- Prefer explicit input labels (e.g., `CLAIMS TO VERIFY:`).

## File Organization
- Core modules live in repo root (no `src/` directory).
- Keep new modules at the root unless a new package is introduced.
- Update `README.md` if new entrypoints or scripts are added.

## Documentation Updates
- Add/adjust `README.md` when changing setup/run commands.
- Avoid adding new Markdown files unless requested.

## Safe Defaults for Agents
- Assume network access may be restricted; keep offline workflows.
- Do not commit changes unless explicitly requested.
- Do not add tests unless a test harness is introduced.

## Quick Reference
- App entrypoint: `deep_research.py`
- Orchestration: `research_manager.py`
- Models: `new_models.py`
- Agents: `planner_agent.py`, `writer_agent.py`, `qa_agent.py`, `quality_agent.py`, `brave_search_agent.py`, etc.
- Search Tools: `search_agent.py` (OpenAI WebSearch), `brave_search_tool.py` (Brave API)
