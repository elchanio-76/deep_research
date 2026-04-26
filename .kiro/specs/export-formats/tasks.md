# Implementation Plan: Export Formats

## Overview

Add two deterministic, LLM-free export endpoints (`GET /api/export/{session_id}/markdown` and `GET /api/export/{session_id}/pdf`) to the Deep Research API. The implementation is structured as a new `src/export/` package with a router, service, renderers, models, and error types, wired into the existing FastAPI app.

## Tasks

- [ ] 1. Add dependencies and configuration
  - Add `weasyprint` and `markdown` (or `mistune`) to `requirements.txt`
  - Add `EXPORT_DIR` (default `./exports`) and `EXPORT_BASE_URL` (default `/exports`) constants to `src/config/settings.py`, reading from environment variables via `os.getenv`
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 2. Create `src/export/` package skeleton and internal models
  - [ ] 2.1 Create `src/export/__init__.py` (empty package marker) and `src/export/renderers/__init__.py` (empty)
    - _Requirements: 6.1_
  - [ ] 2.2 Create `src/export/errors.py` with `ExportError`, `SessionNotFoundError`, `ReportNotReadyError`, and `RenderError(reason: str)` exception classes
    - _Requirements: 8.1, 8.2, 8.3, 8.4_
  - [ ] 2.3 Create `src/export/models.py` with `ExportFormat` enum, `DeliveryMode` enum, `QAPair` dataclass, `MetadataHeader` dataclass, `DocumentParts` dataclass, `ExportResult` dataclass, and `ExportUrlResponse` Pydantic model
    - Title derivation logic: use `session.header` if non-null/non-empty, else `initial_prompt[:120]` + `"…"` if truncated
    - `exported_at` uses `datetime.now(timezone.utc).isoformat()`
    - Filename pattern: `report-{session_id}.md` / `report-{session_id}.pdf`
    - _Requirements: 3.2, 3.3, 3.4, 4.4_

- [ ] 3. Implement `MarkdownRenderer`
  - [ ] 3.1 Create `src/export/renderers/markdown.py` with a pure `render(parts: DocumentParts) -> str` function
    - Output order: fenced YAML-style metadata block → report body (verbatim) → `## Q&A History` section (omitted when `parts.qa_pairs` is empty)
    - Metadata block contains `title`, `session_id`, `exported_at`, `format`
    - Q&A section: each pair rendered as `**Q:** ...` / `**A:** ...` blocks in order
    - No escaping or modification of `report_body`
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 3.1, 7.1, 7.2, 7.4_

  - [ ] 3.2 Write property test for `MarkdownRenderer` — Property 1: metadata completeness and document ordering
    - **Property 1: Metadata header completeness and document ordering**
    - **Validates: Requirements 1.3, 1.4, 3.1, 3.2**
    - File: `tests/test_property_export_renderers.py`
    - Use `hypothesis` `@given` with arbitrary `DocumentParts`; assert all four metadata fields present and ordering: metadata before report body before Q&A section

  - [ ] 3.3 Write property test for `MarkdownRenderer` — Property 2: Q&A block count invariant
    - **Property 2: Q&A block count invariant**
    - **Validates: Requirements 1.5, 7.3**
    - File: `tests/test_property_export_renderers.py`
    - Generate arbitrary lists of chat messages; assert count of `**A:**` blocks equals count of assistant-role messages

  - [ ] 3.4 Write property test for `MarkdownRenderer` — Property 3: report body verbatim preservation
    - **Property 3: Report body verbatim preservation**
    - **Validates: Requirements 7.2, 7.4**
    - File: `tests/test_property_export_renderers.py`
    - Generate arbitrary `report_markdown` strings (including Markdown syntax); assert original string is a verbatim substring of rendered output

  - [ ] 3.5 Write property test for `MarkdownRenderer` — Property 4: renderer determinism
    - **Property 4: Renderer determinism**
    - **Validates: Requirements 7.1**
    - File: `tests/test_property_export_renderers.py`
    - Call `render(parts)` twice; assert byte-for-byte identical output

  - [ ] 3.6 Write property test for `MetadataHeader` title derivation — Property 5
    - **Property 5: Title derivation from initial_prompt**
    - **Validates: Requirements 3.3**
    - File: `tests/test_property_export_renderers.py`
    - Generate arbitrary `initial_prompt` strings with `None` header; assert title equals prompt when `len <= 120`, else `prompt[:120] + "…"`

  - [ ] 3.7 Write property test for filename pattern — Property 6
    - **Property 6: Output filename pattern**
    - **Validates: Requirements 4.4**
    - File: `tests/test_property_export_renderers.py`
    - Generate arbitrary UUIDs and formats; assert filename matches `report-{session_id}.md` / `report-{session_id}.pdf`

- [ ] 4. Implement `PDFRenderer`
  - [ ] 4.1 Create `src/export/renderers/pdf.py` with a `render(parts: DocumentParts) -> bytes` function
    - Pipeline: call `MarkdownRenderer.render(parts)` → convert to HTML via `markdown` library → inject CSS (serif/sans-serif body font, distinct `h1`–`h3` sizes, monospace for code, ≥1.5 cm page margins) → `weasyprint.HTML(string=html).write_pdf()`
    - Wrap any `weasyprint` exception in `RenderError`
    - _Requirements: 2.3, 2.4, 2.9_

  - [ ] 4.2 Write property test for `PDFRenderer` — Property 8: valid PDF bytes
    - **Property 8: PDF output is valid PDF bytes**
    - **Validates: Requirements 2.3**
    - File: `tests/test_property_export_renderers.py`
    - Generate arbitrary `DocumentParts`; assert returned `bytes` is non-empty and starts with `b"%PDF"`

- [ ] 5. Implement `Export_Service`
  - [ ] 5.1 Create `src/export/service.py` with `async def export(session_id: UUID, fmt: ExportFormat, pool: asyncpg.Pool) -> ExportResult`
    - Fetch session via `db.sessions.load_session`; raise `SessionNotFoundError` if `None`
    - Raise `ReportNotReadyError` if `report_markdown` is `None`
    - Fetch messages via `db.messages.fetch_chat_messages`
    - Build `DocumentParts` (derive title per Req 3.2/3.3, pair messages into `QAPair` list)
    - Delegate to `MarkdownRenderer.render` or `PDFRenderer.render`; wrap renderer exceptions in `RenderError`
    - When `delivery_mode=url`: call `Path(export_dir).mkdir(parents=True, exist_ok=True)` before writing
    - _Requirements: 1.2, 2.2, 3.1, 3.4, 4.3, 4.4, 4.6, 5.1, 5.2_

  - [ ] 5.2 Write unit tests for `Export_Service` in `tests/test_unit_export_service.py`
    - Mock `load_session` returning `None` → assert `SessionNotFoundError` raised
    - Mock session with `report_markdown=None` → assert `ReportNotReadyError` raised
    - Mock renderer raising exception → assert `RenderError` raised
    - Mock valid session + messages → assert `ExportResult` has correct `filename`, `media_type`, `fmt`
    - _Requirements: 1.7, 1.8, 2.5, 2.6, 2.9_

- [ ] 6. Implement `Export_Router`
  - [ ] 6.1 Create `src/export/router.py` with `router = APIRouter(prefix="/export", tags=["export"])`
    - `GET /{session_id}/markdown` and `GET /{session_id}/pdf` handlers
    - Both accept `session_id: UUID` path param and `delivery_mode: DeliveryMode = DeliveryMode.download` query param
    - Use `get_pool` dependency from `src/api/dependencies.py`; no `get_research_manager` or agent imports
    - `download` mode: return `StreamingResponse` with correct `Content-Type` and `Content-Disposition: attachment; filename="report-{session_id}.{ext}"`
    - `url` mode: write file to `EXPORT_DIR`, return `JSONResponse` with `ExportUrlResponse` (`file_path`, `url`)
    - Translate `SessionNotFoundError` → 404, `ReportNotReadyError` → 422, `RenderError` → 500 `{"detail": "PDF rendering failed", "reason": "..."}`, `asyncpg.PostgresError` → 500 `{"detail": "Database error: ..."}`
    - No stack traces or internal paths in any error response body
    - Rich OpenAPI `summary` and `description` on each endpoint
    - _Requirements: 1.1, 1.9, 1.10, 2.1, 2.7, 2.8, 4.1, 4.2, 4.3, 4.5, 6.1, 6.2, 6.3, 6.4, 8.1, 8.2, 8.3, 8.4_

  - [ ] 6.2 Write unit tests for `Export_Router` in `tests/test_unit_export_router.py`
    - HTTP 404 for unknown `session_id`
    - HTTP 422 for `report_markdown=None`
    - HTTP 422 for invalid UUID path param
    - HTTP 422 for invalid `delivery_mode` value
    - HTTP 500 with `{"detail": "PDF rendering failed", "reason": "..."}` when `weasyprint` raises
    - HTTP 500 with `{"detail": "Database error: ..."}` when `asyncpg.PostgresError` raised
    - `delivery_mode=download` returns correct `Content-Type` and `Content-Disposition` headers
    - `delivery_mode=url` returns JSON with `file_path` and `url`, file exists on disk
    - `delivery_mode=url` with non-existent `EXPORT_DIR` creates the directory
    - Empty Q&A list → `## Q&A History` absent from Markdown output
    - _Requirements: 1.7, 1.8, 1.9, 1.10, 2.7, 2.8, 2.9, 4.1, 4.2, 4.3, 4.5, 4.6, 8.1, 8.2, 8.3, 8.4_

  - [ ] 6.3 Write property test for router — Property 7: invalid delivery_mode produces 422
    - **Property 7: Invalid delivery_mode produces 422**
    - **Validates: Requirements 4.1, 4.5**
    - File: `tests/test_property_export_renderers.py`
    - Generate arbitrary strings not in `{"download", "url"}`; assert endpoint returns HTTP 422

  - [ ] 6.4 Write property test for router — Property 9: no stack traces in error responses
    - **Property 9: No stack traces in error responses**
    - **Validates: Requirements 8.4**
    - File: `tests/test_property_export_renderers.py`
    - Inject various exception types; assert response body does not contain `"Traceback"`, `"File \""`, or absolute filesystem paths

- [ ] 7. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Register router and smoke tests
  - [ ] 8.1 Register `Export_Router` in `src/api/main.py`
    - Add `from src.export.router import router as export_router`
    - Add `app.include_router(export_router, prefix="/api")`
    - _Requirements: 6.1_

  - [ ] 8.2 Write smoke / integration tests in `tests/test_export_integration.py`
    - Export router endpoints appear in `/openapi.json`
    - No imports from `src/agents/` or `src/core/research_manager` anywhere in `src/export/`
    - `EXPORT_DIR` and `EXPORT_BASE_URL` defaults work when env vars are unset
    - _Requirements: 5.3, 6.1, 6.3_

- [ ] 9. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Add export UI to Gradio thin client
  - [ ] 10.1 Add export controls to `gradio_app.py` below the report output area
    - Add a `gr.Dropdown` with label `"Export Format"` and choices `[("Markdown", "markdown"), ("PDF", "pdf")]`, defaulting to `"markdown"`
    - Add a `gr.Button("Export Report", variant="secondary")` next to the dropdown
    - Add a `gr.File(label="Download", visible=False)` output component to surface the downloaded file to the user
    - Group the dropdown, button, and file output in a `gr.Row` for compact layout
  - [ ] 10.2 Implement `export_report` async handler in `gradio_app.py`
    - Accept `session_id: str | None` (from `session_state`) and `fmt: str` (from the format dropdown)
    - If `session_id` is `None`, return a `gr.update` that keeps the file component hidden and show no file
    - Call `GET {API_BASE}/export/{session_id}/{fmt}` via `httpx.AsyncClient` with `delivery_mode=download` (default)
    - On success (HTTP 200): write the response bytes to a temp file with the correct extension (`.md` or `.pdf`), return `gr.update(value=<temp_path>, visible=True)` so Gradio surfaces the download link
    - On HTTP 404/422: return `gr.update(visible=False)` and surface the error in the report area or via `gr.Warning`
    - On other errors: log and return `gr.update(visible=False)`
    - Follow the existing `httpx.AsyncClient` pattern used in `run()` and `chat()` — no direct imports from `src/`
  - [ ] 10.3 Wire the export button click event
    - `export_button.click(fn=export_report, inputs=[session_state, export_format_dropdown], outputs=[export_file_output])`
    - Ensure `session_state` is passed so the handler always has the current session ID
  - [ ] 10.4 Ensure the export controls are disabled / hidden when no session is active
    - On `new_session_button.click` and on initial page load, reset `export_file_output` to `gr.update(value=None, visible=False)`
    - Add `export_file_output` to the outputs list of `new_session` so it resets alongside the other components

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Property tests use `hypothesis` with `@given` and `@settings(max_examples=100)`
- Property test file: `tests/test_property_export_renderers.py`
- Unit test files: `tests/test_unit_export_service.py`, `tests/test_unit_export_router.py`
- Integration test file: `tests/test_export_integration.py`
- All work must be done on the `export-formats` git branch
- No commits unless explicitly requested
