# Requirements Document

## Introduction

This feature adds deterministic multi-format report export to the Deep Research API. Two new FastAPI endpoints under `/api/export/` allow callers to export a research session's report and Q&A conversation history as a Markdown document or a PDF. No LLM is involved — export is pure document generation. The endpoints are designed with clear input/output contracts so they can be called as tools by an LLM orchestrator.

The initial formats are **Markdown** and **PDF**. Both formats include a metadata header and a structured Q&A appendix assembled from the session's stored conversation history.

## Glossary

- **Export_Router**: The FastAPI `APIRouter` mounted at `/api/export`, containing all export endpoints.
- **Export_Service**: The internal module (`src/export/service.py`) responsible for assembling document content from session data.
- **Markdown_Renderer**: The component within Export_Service that serialises session data into a Markdown string.
- **PDF_Renderer**: The component within Export_Service that converts a Markdown string to HTML and then to PDF bytes using `weasyprint`.
- **Session**: A research session stored in the database, identified by a UUID, containing a report and conversation history.
- **Report**: The `report_markdown` field of a Session — the main research output in Markdown format.
- **Conversation_History**: The ordered list of `chat`-type messages (role + content) associated with a Session, fetched via `db.messages.fetch_chat_messages`.
- **Metadata_Header**: A block at the top of every exported document containing: report title (session `header` or `initial_prompt`), session ID, export timestamp (UTC ISO-8601), and export format name.
- **QA_Appendix**: A structured section appended after the Report body, containing each Question–Answer pair from the Conversation_History.
- **Delivery_Mode**: The caller-specified response strategy — either `download` (binary file in HTTP response body) or `url` (server writes the file and returns its path/URL).
- **Export_Request**: The request body or query parameters accepted by an export endpoint.
- **Export_Response**: The HTTP response produced by an export endpoint — either a binary file stream or a JSON object with a file path/URL.

---

## Requirements

### Requirement 1: Markdown Export Endpoint

**User Story:** As an API caller (human or LLM tool), I want to export a session's report and Q&A history as a Markdown file, so that I can store, display, or further process the research output in a portable text format.

#### Acceptance Criteria

1. THE Export_Router SHALL expose a `GET /api/export/{session_id}/markdown` endpoint that accepts a session UUID as a path parameter.
2. WHEN a valid `session_id` is provided, THE Export_Service SHALL fetch the session record and Conversation_History from the database without invoking any LLM.
3. WHEN the session record is retrieved, THE Markdown_Renderer SHALL produce a document containing, in order: the Metadata_Header, the Report body, and the QA_Appendix.
4. THE Markdown_Renderer SHALL format the Metadata_Header as a fenced block or front-matter section containing: report title, session ID, export date (UTC ISO-8601), and format label `"markdown"`.
5. WHEN the Conversation_History contains one or more messages, THE Markdown_Renderer SHALL render the QA_Appendix as a level-2 heading `## Q&A History` followed by each exchange as a `**Q:**` / `**A:**` block in chronological order.
6. WHEN the Conversation_History is empty, THE Markdown_Renderer SHALL omit the QA_Appendix section entirely.
7. WHEN the session's `report_markdown` field is `NULL`, THE Export_Router SHALL return HTTP 422 with a descriptive error message indicating the report is not yet available.
8. WHEN the `session_id` does not exist in the database, THE Export_Router SHALL return HTTP 404 with a descriptive error message.
9. WHEN `delivery_mode` query parameter is `download` (default), THE Export_Router SHALL return the Markdown document as an `application/octet-stream` response with `Content-Disposition: attachment; filename="report-{session_id}.md"`.
10. WHERE the caller sets `delivery_mode=url`, THE Export_Router SHALL write the Markdown file to a configurable server-side directory and return a JSON response containing the absolute file path and a relative URL.

---

### Requirement 2: PDF Export Endpoint

**User Story:** As an API caller (human or LLM tool), I want to export a session's report and Q&A history as a PDF file, so that I can share or archive the research output in a universally readable, print-ready format.

#### Acceptance Criteria

1. THE Export_Router SHALL expose a `GET /api/export/{session_id}/pdf` endpoint that accepts a session UUID as a path parameter.
2. WHEN a valid `session_id` is provided, THE Export_Service SHALL fetch the session record and Conversation_History from the database without invoking any LLM.
3. WHEN the session record is retrieved, THE PDF_Renderer SHALL first produce the same Markdown document as the Markdown_Renderer (including Metadata_Header and QA_Appendix), then convert it to HTML, then render the HTML to PDF bytes using `weasyprint`.
4. THE PDF_Renderer SHALL apply CSS styling that provides: a readable serif or sans-serif body font, distinct heading sizes for `h1`–`h3`, monospace font for code blocks, and page margins of at least 1.5 cm on all sides.
5. WHEN the session's `report_markdown` field is `NULL`, THE Export_Router SHALL return HTTP 422 with a descriptive error message indicating the report is not yet available.
6. WHEN the `session_id` does not exist in the database, THE Export_Router SHALL return HTTP 404 with a descriptive error message.
7. WHEN `delivery_mode` query parameter is `download` (default), THE Export_Router SHALL return the PDF as an `application/pdf` response with `Content-Disposition: attachment; filename="report-{session_id}.pdf"`.
8. WHERE the caller sets `delivery_mode=url`, THE Export_Router SHALL write the PDF file to a configurable server-side directory and return a JSON response containing the absolute file path and a relative URL.
9. IF `weasyprint` raises an exception during rendering, THEN THE Export_Router SHALL return HTTP 500 with an error message that includes the renderer failure reason and does not expose internal stack traces to the caller.

---

### Requirement 3: Metadata Header Content

**User Story:** As a consumer of exported documents, I want every export to include a consistent metadata header, so that I can identify the source session and know when the document was generated without inspecting the database.

#### Acceptance Criteria

1. THE Export_Service SHALL include a Metadata_Header in every exported document regardless of format.
2. THE Metadata_Header SHALL contain the following fields: `title` (session `header` if non-null, otherwise the first 120 characters of `initial_prompt`), `session_id` (UUID string), `exported_at` (UTC timestamp in ISO-8601 format), and `format` (one of `"markdown"` or `"pdf"`).
3. WHEN the session `header` field is `NULL`, THE Export_Service SHALL derive the title from the first 120 characters of `initial_prompt`, appending `"…"` if truncated.
4. THE Export_Service SHALL generate the `exported_at` timestamp at the moment the export request is processed, not at the time the report was created.

---

### Requirement 4: Delivery Mode Configuration

**User Story:** As an API caller, I want to choose whether the export is returned as a direct file download or saved server-side with a URL returned, so that I can integrate the export endpoint into both interactive download flows and automated pipeline workflows.

#### Acceptance Criteria

1. THE Export_Router SHALL accept a `delivery_mode` query parameter on both export endpoints with allowed values `download` and `url`, defaulting to `download`.
2. WHEN `delivery_mode=download`, THE Export_Router SHALL stream the file bytes directly in the HTTP response body with the appropriate `Content-Type` and `Content-Disposition` headers.
3. WHERE `delivery_mode=url` is selected, THE Export_Router SHALL write the exported file to a directory defined by the `EXPORT_DIR` configuration setting and return a JSON body with fields `file_path` (absolute path on the server) and `url` (relative URL path for retrieval).
4. THE Export_Service SHALL derive the output filename as `report-{session_id}.{ext}` where `ext` is `md` for Markdown and `pdf` for PDF.
5. IF `delivery_mode` is set to a value other than `download` or `url`, THEN THE Export_Router SHALL return HTTP 422 with a descriptive validation error.
6. WHERE `delivery_mode=url` is selected and the `EXPORT_DIR` directory does not exist, THE Export_Service SHALL create it before writing the file.

---

### Requirement 5: Export Configuration

**User Story:** As a system operator, I want export behaviour (output directory, base URL) to be configurable via environment variables, so that I can deploy the service in different environments without code changes.

#### Acceptance Criteria

1. THE Export_Service SHALL read the export output directory from a `EXPORT_DIR` environment variable, defaulting to `./exports` relative to the working directory.
2. THE Export_Service SHALL read the base URL prefix for served export files from an `EXPORT_BASE_URL` environment variable, defaulting to `/exports`.
3. WHEN `EXPORT_DIR` or `EXPORT_BASE_URL` are not set, THE Export_Service SHALL use the documented default values without raising an error.

---

### Requirement 6: Router Registration

**User Story:** As a backend developer, I want the export router registered in the existing FastAPI app, so that the new endpoints are reachable under `/api/export/` alongside the existing API surface.

#### Acceptance Criteria

1. THE Export_Router SHALL be registered in `src/api/main.py` with the prefix `/api` so that endpoints are reachable at `/api/export/{session_id}/markdown` and `/api/export/{session_id}/pdf`.
2. THE Export_Router SHALL use the existing `get_pool` dependency from `src/api/dependencies.py` to obtain the database connection pool.
3. THE Export_Router SHALL NOT depend on `get_research_manager` or any agent module, preserving the deterministic, LLM-free nature of the export pipeline.
4. THE Export_Router SHALL include OpenAPI `summary` and `description` metadata on each endpoint sufficient for an LLM tool-calling system to understand the endpoint's purpose, inputs, and outputs without additional documentation.

---

### Requirement 7: Document Assembly Round-Trip Integrity

**User Story:** As a developer maintaining the export feature, I want the Markdown assembly to be deterministic and structurally consistent, so that automated tests can verify correctness without relying on LLM output.

#### Acceptance Criteria

1. THE Markdown_Renderer SHALL produce identical output for identical inputs (same session data, same timestamp) — the function is pure with respect to its inputs.
2. WHEN a Markdown document is assembled and then parsed back into its constituent sections (Metadata_Header, Report body, QA_Appendix), THE Export_Service SHALL recover the original Report body text without modification.
3. FOR ALL valid session data inputs, the number of Q&A blocks in the QA_Appendix SHALL equal the number of assistant-role messages in the Conversation_History.
4. THE Markdown_Renderer SHALL preserve all Markdown formatting present in the original `report_markdown` field without escaping or altering it.

---

### Requirement 8: Error Handling and Observability

**User Story:** As an API caller or LLM tool, I want export errors to return structured, descriptive HTTP error responses, so that I can handle failures programmatically without parsing free-form error text.

#### Acceptance Criteria

1. WHEN a database error occurs during session or message retrieval, THE Export_Router SHALL return HTTP 500 with a JSON body containing a `detail` field describing the failure category.
2. WHEN the `session_id` path parameter is not a valid UUID, THE Export_Router SHALL return HTTP 422 with FastAPI's standard validation error structure.
3. IF the PDF rendering step fails, THEN THE Export_Router SHALL return HTTP 500 with a `detail` field containing the string `"PDF rendering failed"` and a `reason` field with the exception message.
4. THE Export_Router SHALL NOT expose Python stack traces or internal file paths in any error response body.
