# Design Document: Export Formats

## Overview

This feature adds two deterministic, LLM-free export endpoints to the Deep Research API. A new FastAPI router (`Export_Router`) mounted at `/api/export/` exposes `GET /api/export/{session_id}/markdown` and `GET /api/export/{session_id}/pdf`. Both endpoints fetch session data from the database, assemble a structured document (metadata header + report body + Q&A appendix), and return it either as a direct file download or as a server-side file with a JSON URL response.

The export pipeline is entirely deterministic: given the same session data and timestamp, it always produces the same output. No LLM is invoked. The endpoints carry rich OpenAPI metadata so they can be called as tools by an LLM orchestrator.

### Key Design Decisions

- **Markdown → HTML → PDF pipeline**: `weasyprint` converts HTML (produced from Markdown via `markdown` or `mistune`) to PDF bytes. This avoids a direct Markdown-to-PDF dependency and gives full CSS control over styling.
- **Session ID as sole input**: the endpoint fetches everything it needs (session record + chat messages) from the database using the existing `get_pool` dependency.
- **Delivery modes**: `download` (default) streams bytes directly; `url` writes to disk and returns a JSON body with `file_path` and `url`.
- **No agent dependencies**: `Export_Router` never imports from `src/agents/` or `src/core/research_manager.py`.
- **Config via env vars**: `EXPORT_DIR` (default `./exports`) and `EXPORT_BASE_URL` (default `/exports`) are read at request time so they can be overridden per environment.

---

## Architecture

```mermaid
flowchart TD
    Client -->|GET /api/export/{id}/markdown\nGET /api/export/{id}/pdf| Router[Export_Router\nsrc/export/router.py]
    Router -->|get_pool| DB[(PostgreSQL)]
    Router --> Service[Export_Service\nsrc/export/service.py]
    Service -->|load_session| DB
    Service -->|fetch_chat_messages| DB
    Service --> Assembler[Document Assembler\nbuild_document_parts]
    Assembler --> MDRenderer[Markdown_Renderer\nrenderers/markdown.py]
    Assembler --> PDFRenderer[PDF_Renderer\nrenderers/pdf.py]
    MDRenderer -->|markdown string| Router
    PDFRenderer -->|markdown → HTML → PDF bytes| Router
    Router -->|download mode| FileResponse[StreamingResponse\napplication/octet-stream or application/pdf]
    Router -->|url mode| JSONResponse[JSONResponse\n{file_path, url}]
```

The `Export_Service` is a plain async module (not a class instance stored in `app.state`) — it is stateless and receives the pool as a parameter on each call, matching the pattern used by `src/db/sessions.py` and `src/db/messages.py`.

---

## Components and Interfaces

### `src/export/__init__.py`
Empty package marker.

### `src/export/router.py` — `Export_Router`

```python
router = APIRouter(prefix="/export", tags=["export"])

@router.get(
    "/{session_id}/markdown",
    summary="Export session report as Markdown",
    description="...",  # LLM-tool-friendly description
)
async def export_markdown(
    session_id: UUID,
    delivery_mode: DeliveryMode = DeliveryMode.download,
    pool: asyncpg.Pool = Depends(get_pool),
) -> Response: ...

@router.get(
    "/{session_id}/pdf",
    summary="Export session report as PDF",
    description="...",
)
async def export_pdf(
    session_id: UUID,
    delivery_mode: DeliveryMode = DeliveryMode.download,
    pool: asyncpg.Pool = Depends(get_pool),
) -> Response: ...
```

Both handlers:
1. Call `Export_Service.export(session_id, format, pool)` to get `ExportResult`.
2. Dispatch on `delivery_mode` to return either a `StreamingResponse` or `JSONResponse`.
3. Translate `ExportError` subtypes to the appropriate HTTP status codes.

### `src/export/service.py` — `Export_Service`

```python
async def export(
    session_id: UUID,
    fmt: ExportFormat,
    pool: asyncpg.Pool,
) -> ExportResult: ...
```

Responsibilities:
- Fetch session via `db.sessions.load_session`.
- Raise `SessionNotFoundError` (→ 404) if `None`.
- Raise `ReportNotReadyError` (→ 422) if `report_markdown` is `None`.
- Fetch messages via `db.messages.fetch_chat_messages`.
- Build `DocumentParts` (metadata header + report body + Q&A pairs).
- Delegate to `MarkdownRenderer` or `PDFRenderer`.
- Handle `weasyprint` exceptions → `RenderError` (→ 500).

### `src/export/renderers/markdown.py` — `MarkdownRenderer`

```python
def render(parts: DocumentParts) -> str: ...
```

Pure function. Produces the final Markdown string in this order:
1. Fenced metadata block (YAML-style front matter).
2. Report body (verbatim, no escaping).
3. `## Q&A History` section (omitted when `parts.qa_pairs` is empty).

### `src/export/renderers/pdf.py` — `PDFRenderer`

```python
def render(parts: DocumentParts) -> bytes: ...
```

Pipeline: `MarkdownRenderer.render(parts)` → `markdown_to_html(md_str)` → inject CSS → `weasyprint.HTML(string=html).write_pdf()`.

Wraps `weasyprint` exceptions in `RenderError`.

### `src/export/models.py` — Internal DTOs

See Data Models section below.

---

## Data Models

### `ExportFormat` (enum)

```python
class ExportFormat(str, Enum):
    markdown = "markdown"
    pdf = "pdf"
```

### `DeliveryMode` (enum)

```python
class DeliveryMode(str, Enum):
    download = "download"
    url = "url"
```

FastAPI validates query parameter values automatically; unknown values produce a 422.

### `QAPair`

```python
@dataclass
class QAPair:
    question: str   # role == "user" content
    answer: str     # role == "assistant" content
```

Chat messages are paired sequentially: user message N → question, assistant message N → answer. Unpaired trailing messages are included with an empty counterpart.

### `MetadataHeader`

```python
@dataclass
class MetadataHeader:
    title: str          # session.header or initial_prompt[:120] + "…"
    session_id: str     # UUID as string
    exported_at: str    # UTC ISO-8601, e.g. "2025-01-15T10:30:00Z"
    format: str         # "markdown" or "pdf"
```

`exported_at` is generated at request time via `datetime.now(timezone.utc).isoformat()`.

Title derivation:
- If `session.header` is not `None` and not empty → use as-is.
- Otherwise → `session.initial_prompt[:120]` + `"…"` if `len(initial_prompt) > 120`.

### `DocumentParts`

```python
@dataclass
class DocumentParts:
    metadata: MetadataHeader
    report_body: str        # verbatim report_markdown
    qa_pairs: list[QAPair]  # empty list when no chat messages
```

### `ExportResult`

```python
@dataclass
class ExportResult:
    content: bytes          # rendered bytes (UTF-8 for MD, binary for PDF)
    filename: str           # "report-{session_id}.md" or ".pdf"
    media_type: str         # "application/octet-stream" or "application/pdf"
    fmt: ExportFormat
```

### Error types (`src/export/errors.py`)

```python
class ExportError(Exception): ...
class SessionNotFoundError(ExportError): ...
class ReportNotReadyError(ExportError): ...
class RenderError(ExportError):
    reason: str
```

### API response model for `delivery_mode=url`

```python
class ExportUrlResponse(BaseModel):
    file_path: str   # absolute path on server
    url: str         # relative URL, e.g. "/exports/report-<id>.pdf"
```

---

## Correctness Properties


*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Metadata header completeness and document ordering

*For any* valid `DocumentParts` (arbitrary title, session_id, report body, and Q&A pairs), the rendered Markdown string SHALL contain all four metadata fields (`title`, `session_id`, `exported_at`, `format`) AND the metadata block SHALL appear before the report body, which SHALL appear before the `## Q&A History` section (when Q&A pairs are non-empty).

**Validates: Requirements 1.3, 1.4, 3.1, 3.2**

### Property 2: Q&A block count invariant

*For any* list of chat messages (arbitrary mix of `user` and `assistant` roles), the number of `**A:**` blocks in the rendered Markdown output SHALL equal the number of `assistant`-role messages in the input list.

**Validates: Requirements 1.5, 7.3**

### Property 3: Report body verbatim preservation

*For any* `report_markdown` string (including strings containing Markdown syntax such as headings, code fences, bold, and links), the rendered Markdown output SHALL contain the original `report_markdown` string as a verbatim substring without escaping or modification.

**Validates: Requirements 7.2, 7.4**

### Property 4: Renderer determinism

*For any* `DocumentParts`, calling `MarkdownRenderer.render(parts)` twice in succession SHALL produce byte-for-byte identical output strings.

**Validates: Requirements 7.1**

### Property 5: Title derivation from initial_prompt

*For any* `initial_prompt` string and a `None` session header, the derived title SHALL equal `initial_prompt` when `len(initial_prompt) <= 120`, and SHALL equal `initial_prompt[:120] + "…"` when `len(initial_prompt) > 120`.

**Validates: Requirements 3.3**

### Property 6: Output filename pattern

*For any* session UUID and export format (`markdown` or `pdf`), the derived filename SHALL match the pattern `report-{session_id}.md` for Markdown and `report-{session_id}.pdf` for PDF.

**Validates: Requirements 4.4**

### Property 7: Invalid delivery_mode produces 422

*For any* string value that is not `"download"` or `"url"` supplied as the `delivery_mode` query parameter, the endpoint SHALL return HTTP 422.

**Validates: Requirements 4.1, 4.5**

### Property 8: PDF output is valid PDF bytes

*For any* valid `DocumentParts`, `PDFRenderer.render(parts)` SHALL return a non-empty `bytes` object whose first four bytes are `%PDF`, confirming a well-formed PDF was produced.

**Validates: Requirements 2.3**

### Property 9: No stack traces in error responses

*For any* exception type raised during export processing (database errors, render errors, not-found errors), the HTTP response body SHALL NOT contain the strings `"Traceback"`, `"File \""`, or any absolute filesystem path from the server.

**Validates: Requirements 8.4**

---

## Error Handling

| Condition | HTTP Status | Response body |
|---|---|---|
| `session_id` path param is not a valid UUID | 422 | FastAPI standard validation error |
| Session not found in DB | 404 | `{"detail": "Session <id> not found"}` |
| `report_markdown` is `NULL` | 422 | `{"detail": "Report not yet available for session <id>"}` |
| `delivery_mode` is not `download` or `url` | 422 | FastAPI enum validation error |
| Database error during fetch | 500 | `{"detail": "Database error: <category>"}` |
| `weasyprint` raises during PDF render | 500 | `{"detail": "PDF rendering failed", "reason": "<exception message>"}` |

**Stack trace suppression**: all exception handlers in `router.py` catch broad exceptions and construct the response body manually. No `traceback.format_exc()` output or internal paths are ever included.

**`EXPORT_DIR` creation**: when `delivery_mode=url`, the service calls `Path(export_dir).mkdir(parents=True, exist_ok=True)` before writing, so a missing directory is never a fatal error.

---

## Testing Strategy

### Dual approach

- **Unit / property tests** (`tests/test_property_export_*.py`, `tests/test_unit_export_*.py`): test the pure renderer functions and service logic in isolation using mocked DB calls.
- **Integration tests** (`tests/test_api_integration.py` extension or a new `tests/test_export_integration.py`): test the full HTTP stack with a real (test) database.

### Property-based testing

The project already uses `hypothesis` for property-based tests. Each correctness property above maps to one `@given`-decorated test with a minimum of 100 examples.

**Library**: `hypothesis` (already in `requirements.txt`)  
**Async support**: `pytest-asyncio` (already in use)  
**Minimum iterations**: 100 per property (Hypothesis default `max_examples=100`)

Tag format in test comments: `# Feature: export-formats, Property <N>: <property_text>`

#### Hypothesis strategies needed

```python
# Arbitrary DocumentParts
st.builds(DocumentParts,
    metadata=st.builds(MetadataHeader,
        title=st.text(min_size=1, max_size=200),
        session_id=st.uuids().map(str),
        exported_at=st.just("2025-01-01T00:00:00Z"),
        format=st.sampled_from(["markdown", "pdf"]),
    ),
    report_body=st.text(min_size=0, max_size=2000),
    qa_pairs=st.lists(
        st.builds(QAPair,
            question=st.text(min_size=1),
            answer=st.text(min_size=1),
        ),
        max_size=20,
    ),
)
```

### Unit tests (example-based)

- HTTP 404 for unknown session_id
- HTTP 422 for `report_markdown=None`
- HTTP 422 for invalid UUID path param
- HTTP 422 for invalid `delivery_mode`
- HTTP 500 with correct JSON shape when `weasyprint` raises
- HTTP 500 with correct JSON shape when DB raises `asyncpg.PostgresError`
- `delivery_mode=download` returns correct `Content-Type` and `Content-Disposition`
- `delivery_mode=url` returns JSON with `file_path` and `url`, file exists on disk
- `delivery_mode=url` with non-existent `EXPORT_DIR` creates the directory
- Empty Q&A list → `## Q&A History` heading absent from output
- CSS string in `PDFRenderer` contains `font-family`, `margin`, `monospace`

### Smoke tests

- Export router is registered and endpoints appear in `/openapi.json`
- No imports from `src/agents/` or `src/core/research_manager` in `src/export/`
- `EXPORT_DIR` and `EXPORT_BASE_URL` defaults work when env vars are unset
