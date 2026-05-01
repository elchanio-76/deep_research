# Deep Research Agent

An intelligent research assistant built with OpenAI's Agents SDK. It conducts comprehensive research, generates detailed reports, and provides fact-checking with intelligent verification strategies. The backend is a FastAPI REST API with Server-Sent Events (SSE) for real-time streaming; a Gradio thin client provides the web UI.

## Features

- **Automated Research**: Multi-step web search planning and execution
- **Intelligent Report Generation**: Comprehensive markdown reports (1000+ words)
- **Advanced Fact-Checking**: Adaptive verification strategies with confidence scoring
- **Report Editing**: Automatic correction of dubious claims based on fact-checking results
- **Interactive Q&A**: Chat interface for querying report findings
- **Cost-Effective Search**: Hybrid routing between OpenAI WebSearch and Brave Search API
- **Session Management**: Persistent research sessions stored in PostgreSQL
- **REST API**: FastAPI backend with SSE streaming for any HTTP client
- **Report Export**: Deterministic Markdown, PDF, and DOCX export of completed research reports

## Architecture

```
gradio_app.py  (Gradio thin client — HTTP/SSE only)
      │
      ▼
src/api/main.py  (FastAPI app)
  ├── POST /api/research/start        →  SSE stream
  ├── POST /api/chat                  →  SSE stream
  ├── GET/DELETE /api/sessions        →  JSON
  └── GET /api/export/{id}/markdown   →  Markdown file / URL
      GET /api/export/{id}/pdf        →  PDF file / URL
      │
      ▼
src/core/research_manager.py  (orchestrator, async generators)
  ├── src/agents/               (all AI agent modules)
  ├── src/db/                   (asyncpg pool + SQL queries)
  └── src/streaming/sse.py      (SSE event formatting)
```

### Package Structure

```
src/
├── api/
│   ├── main.py          # FastAPI app + lifespan (pool, ResearchManager)
│   ├── research.py      # POST /api/research/start
│   ├── chat.py          # POST /api/chat
│   ├── sessions.py      # GET/DELETE /api/sessions, /cost
│   └── dependencies.py  # get_pool, get_research_manager
├── core/
│   ├── research_manager.py   # Core orchestrator
│   └── usage_tracker.py      # ContextVar token tracking
├── agents/              # All AI agent modules (stateless)
│   ├── planner_agent.py
│   ├── search_agent.py
│   ├── brave_search_agent.py
│   ├── brave_search_tool.py
│   ├── writer_agent.py
│   ├── editor_agent.py
│   ├── qa_agent.py
│   ├── quality_agent.py
│   ├── claim_extraction_agent.py
│   ├── fact_check_planner_agent.py
│   ├── verification_tools.py
│   ├── email_agent.py
│   ├── session_title_agent.py
│   ├── adaptive_search_planner.py
│   └── citation_agent.py
├── models/
│   ├── domain.py        # Pydantic domain models
│   └── api.py           # Request/Response DTOs + SSE event models
├── db/
│   ├── pool.py          # asyncpg pool lifecycle + DDL
│   ├── sessions.py      # Session CRUD
│   └── messages.py      # Message insert/fetch
├── streaming/
│   └── sse.py           # SSE event formatting + stream adapters
├── export/
│   ├── router.py        # GET /api/export/{id}/markdown, /pdf
│   ├── service.py       # Export orchestration (fetch session, render, write)
│   ├── models.py        # ExportFormat, DeliveryMode, ExportResult, ExportUrlResponse
│   ├── errors.py        # SessionNotFoundError, ReportNotReadyError, RenderError
│   └── renderers/
│       ├── markdown.py  # Pure Markdown renderer
│       ├── pdf.py       # Markdown → HTML → PDF via weasyprint
│       └── docx.py      # Markdown → DOCX via python-docx
└── config/
    └── settings.py      # All constants + env loading
```

## Installation & Setup

1. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment** — create a `.env` file:

   ```
   OPENAI_API_KEY=your_openai_api_key
   DATABASE_URL=postgresql://user:password@localhost:5432/deep_research
   BRAVE_API_KEY=your_brave_api_key        # optional: cost-effective search
   SENDGRID_API_KEY=your_sendgrid_key      # optional: email reports
   FROM_EMAIL=you@example.com              # optional: email sender
   TO_EMAIL=recipient@example.com          # optional: email recipient
   EXPORT_DIR=./exports                    # optional: server-side export directory (default: ./exports)
   EXPORT_BASE_URL=/exports                # optional: URL prefix for exported files (default: /exports)
   ```

3. **Start the API server**:

   ```bash
   uvicorn src.api.main:app --reload
   ```

4. **Start the Gradio UI** (in a separate terminal):

   ```bash
   python gradio_app.py
   ```

## API Reference

### `POST /api/research/start`

Start a research pipeline. Returns an SSE stream.

**Request body:**
```json
{
  "query": "Impact of AI on healthcare",
  "search_mode": "no_adaptive",
  "cost_effective": false
}
```

`search_mode` values: `no_adaptive` | `deep_dive` | `deep_dive_gap_fill`

**SSE event sequence:**
```
data: {"type": "progress",   "message": "Planning searches..."}
data: {"type": "progress",   "message": "Executing searches..."}
data: {"type": "report",     "content": "# Research Report\n\n..."}
data: {"type": "cost",       "summary": {"total_input_tokens": 15234, ...}}
data: {"type": "session_id", "session_id": "uuid-of-created-session"}
data: {"type": "complete"}
```

### `POST /api/chat`

Ask a question about a session's report. Returns an SSE stream.

**Request body:**
```json
{
  "session_id": "uuid-here",
  "message": "What are the main findings?",
  "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
}
```

**SSE event sequence:**
```
data: {"type": "chunk",    "content": "Based on the report..."}
data: {"type": "complete"}
```

Special commands: `/quality`, `/bias` — routes to quality/bias analysis agent.

### `GET /api/sessions`

Returns a list of session summaries ordered by last activity.

### `GET /api/sessions/{session_id}`

Returns full session data including report, cost summary, and chat history.

### `DELETE /api/sessions/{session_id}`

Deletes a session and its messages. Returns 204.

### `GET /api/sessions/{session_id}/cost`

Returns token usage and cost summary for a session.

### `GET /api/export/{session_id}/markdown`

Export a completed session report as a Markdown document.

**Query parameters:**
- `delivery_mode` (optional, default `download`): `download` streams the file in the response body; `url` writes the file server-side and returns a JSON object.

**Responses:**
- `200` — Markdown file (`Content-Type: text/markdown`) or `{"file_path": "...", "url": "..."}` JSON.
- `404` — Session not found.
- `422` — Report not yet generated, or invalid parameters.
- `500` — Database or rendering error.

### `GET /api/export/{session_id}/pdf`

Export a completed session report as a PDF document (generated via weasyprint — no LLM involved).

**Query parameters:**
- `delivery_mode` (optional, default `download`): same as the Markdown endpoint.

**Responses:**
- `200` — PDF file (`Content-Type: application/pdf`) or `{"file_path": "...", "url": "..."}` JSON.
- `404` — Session not found.
- `422` — Report not yet generated, or invalid parameters.
- `500` — Database or rendering error.

### `GET /api/export/{session_id}/docx`

Export a completed session report as a DOCX document (generated via python-docx — no LLM involved). Includes metadata properties, formatted headings, bullet/numbered lists, inline code, bold/italic, links, code blocks, and an optional Q&A history section.

**Query parameters:**
- `delivery_mode` (optional, default `download`): `download` streams the file in the response body; `url` writes the file server-side and returns a JSON object.

**Responses:**
- `200` — DOCX file (`Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document`) or `{"file_path": "...", "url": "..."}` JSON.
- `404` — Session not found.
- `422` — Report not yet generated, or invalid parameters.
- `500` — Database or rendering error.

## Usage Examples

### Python client (httpx + SSE)

```python
import httpx

with httpx.Client() as client:
    with client.stream("POST", "http://localhost:8000/api/research/start",
                       json={"query": "Impact of AI on healthcare"}) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                print(line[6:])
```

### Direct ResearchManager usage (testing/scripting)

```python
import asyncio
from src.core.research_manager import ResearchManager
from src.db.pool import init_db, close_pool

async def main():
    pool = await init_db()
    rm = ResearchManager(pool=pool)
    async for update in rm.run("Impact of AI on healthcare"):
        print(update)
    await close_pool()

asyncio.run(main())
```

## Cost Optimization

- **Claim Prioritization**: Focus verification budget on important claims
- **Strategy Selection**: Match verification intensity to claim characteristics (skip / quick / thorough / red-team / group)
- **Batch Processing**: Group related claims for efficient verification
- **Cost-Effective Search Routing**:
  - `no_adaptive` + cost-effective ON → all searches use Brave Search API
  - `deep_dive` / `gap_fill` + cost-effective ON → 50/50 split Brave / OpenAI
  - cost-effective OFF → all searches use OpenAI WebSearch

Typical costs:
- Simple query: $0.10–0.30
- Complex topic with fact-checking: $0.50–1.50
- With cost-effective search enabled: significantly reduced

## Testing

```bash
python -m pytest                                              # all tests
python -m pytest tests/test_unit_domain.py                   # domain model unit + property tests
python -m pytest tests/test_unit_research_manager.py         # ResearchManager pure method unit + property tests
python -m pytest tests/test_unit_usage_tracker.py            # UsageTracker ContextVar unit tests
python -m pytest tests/test_unit_qa_agent.py                 # is_quality_request classifier unit + property tests
python -m pytest tests/test_unit_brave_search_tool.py        # BraveSearchTool formatting unit + property tests
python -m pytest tests/test_unit_verification_tools.py       # parse_verification_result unit tests
python -m pytest tests/test_unit_export_models.py            # ExportModels pure helper unit + property tests
python -m pytest tests/test_unit_docx_renderer.py           # DOCX renderer unit tests (_parse_paragraph, _add_formatted_run, render)
python -m pytest tests/test_unit_sse_formatting.py           # SSE formatting unit tests
python -m pytest tests/test_property_sse_roundtrip.py        # SSE round-trip property tests
python -m pytest tests/test_property_dto_validation.py       # DTO validation property tests
python -m pytest tests/test_api_integration.py               # API integration tests
python -m pytest tests/ -k "property" -v                     # all property-based tests
```

Tests cover:
- **Domain models** (`src/models/domain.py`): `AgentUsage` token accumulation and tool-call counting, `SessionUsage` aggregate totals, `ExtractedClaim` field validator, `FinalReportData.from_writer_and_verification` — unit and Hypothesis property-based
- **ResearchManager pure methods** (`src/core/research_manager.py`): `_normalize_json_payload`, `_get_search_budget`, `_compute_brave_flags`, `calculate_total_cost`, `_format_cost_summary_from_snapshot`, `reset_session_state` — unit and Hypothesis property-based (no LLM, database, or HTTP calls; pool is mocked)
- **UsageTracker** (`src/core/usage_tracker.py`): `set_session_usage`, `get_session_usage`, `record_agent_usage`, `record_tool_call` — ContextVar round-trip, delegation to `SessionUsage`, and no-op behaviour when unbound
- **QA agent** (`src/agents/qa_agent.py`): `is_quality_request` classifier — example tests for known commands/phrases and Hypothesis property test for non-matching strings
- **Brave search tool** (`src/agents/brave_search_tool.py`): `_format_brave_results` and `_process_search_response` — empty list, truncation, missing fields, and Hypothesis field-inclusion property test
- **Verification tools** (`src/agents/verification_tools.py`): `parse_verification_result` dispatch between single and group results
- **Export models** (`src/export/models.py`): `MetadataHeader.derive_title` (header precedence, short/long prompt truncation) and `ExportResult.filename_for` (extension and session-id inclusion) — unit and Hypothesis property-based
- **SSE event formatting** (`src/streaming/sse.py`): unit tests for each `format_*()` function and Hypothesis round-trip property tests
- **Request DTO validation** (`src/models/api.py`): Hypothesis property-based tests for `ResearchStartRequest` and `ChatRequest`
- **Invalid request rejection**: Hypothesis-driven HTTP 422 verification for all POST endpoints
- **Export pipeline** (`src/export/`): unit tests for router and service; Hypothesis property tests for renderers; unit tests for DOCX renderer internals (`_sanitize`, `_core_prop`, `_parse_paragraph`, `_add_formatted_run`, `_process_markdown`) and `render()` output (metadata properties, content presence, Q&A section, determinism, Unicode, control-character stripping); DOCX-specific property tests: valid ZIP/DOCX bytes (Property 10), renderer determinism (Property 11), core properties contain title and session_id (Property 12), Q&A paragraph count invariant (Property 13), title paragraph presence (Property 14)
- **API endpoint integration**: research SSE stream, chat SSE stream, session CRUD, 404 handling

## Future Enhancements

See `EXTENSIONS.md` for planned features including multi-format export, advanced citation management, and collaborative research workflows.

## License

[Add appropriate license information]
