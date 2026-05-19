"""Unit tests for Export_Router (src/export/router.py).

All service calls are mocked so no real DB or renderer is required.
Requirements: 1.7, 1.8, 1.9, 1.10, 2.7, 2.8, 2.9, 4.1, 4.2, 4.3, 4.5,
              4.6, 8.1, 8.2, 8.3, 8.4
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.export.errors import RenderError, ReportNotReadyError, SessionNotFoundError
from src.export.models import ExportFormat, ExportResult
from src.export.router import router

# ---------------------------------------------------------------------------
# App fixture — minimal FastAPI app with the export router and a mock pool
# ---------------------------------------------------------------------------

FAKE_SESSION_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
FAKE_MD_CONTENT = b"# Report\n\nHello world."
FAKE_PDF_CONTENT = b"%PDF-1.4 fake pdf bytes"
FAKE_DOCX_CONTENT = b"PK\x03\x04fake docx bytes"  # ZIP magic bytes (DOCX is a ZIP)


def _make_app() -> FastAPI:
    """Return a minimal FastAPI app with the export router wired in."""
    app = FastAPI()
    app.include_router(router, prefix="/api")

    # Attach a mock pool to app.state so get_pool works
    app.state.pool = MagicMock(spec=asyncpg.Pool)
    return app


@pytest.fixture()
def client():
    """TestClient with a fresh app per test."""
    return TestClient(_make_app(), raise_server_exceptions=False)


def _md_result() -> ExportResult:
    return ExportResult(
        content=FAKE_MD_CONTENT,
        filename=f"report-{FAKE_SESSION_ID}.md",
        media_type="application/octet-stream",
        fmt=ExportFormat.markdown,
    )


def _pdf_result() -> ExportResult:
    return ExportResult(
        content=FAKE_PDF_CONTENT,
        filename=f"report-{FAKE_SESSION_ID}.pdf",
        media_type="application/pdf",
        fmt=ExportFormat.pdf,
    )


def _docx_result() -> ExportResult:
    return ExportResult(
        content=FAKE_DOCX_CONTENT,
        filename=f"report-{FAKE_SESSION_ID}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        fmt=ExportFormat.docx,
    )


# ---------------------------------------------------------------------------
# 404 — session not found (Requirements 1.8, 2.6)
# ---------------------------------------------------------------------------


def test_markdown_404_when_session_not_found(client):
    """HTTP 404 is returned when the session does not exist."""
    with patch(
        "src.export.router.export",
        new=AsyncMock(
            side_effect=SessionNotFoundError(f"Session {FAKE_SESSION_ID} not found")
        ),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/markdown")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_pdf_404_when_session_not_found(client):
    """HTTP 404 is returned when the session does not exist (PDF endpoint)."""
    with patch(
        "src.export.router.export",
        new=AsyncMock(
            side_effect=SessionNotFoundError(f"Session {FAKE_SESSION_ID} not found")
        ),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/pdf")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 422 — report not ready (Requirements 1.7, 2.5)
# ---------------------------------------------------------------------------


def test_markdown_422_when_report_not_ready(client):
    """HTTP 422 is returned when report_markdown is NULL."""
    with patch(
        "src.export.router.export",
        new=AsyncMock(
            side_effect=ReportNotReadyError(
                f"Report not yet available for session {FAKE_SESSION_ID}"
            )
        ),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/markdown")
    assert resp.status_code == 422
    assert "not yet available" in resp.json()["detail"].lower()


def test_pdf_422_when_report_not_ready(client):
    """HTTP 422 is returned when report_markdown is NULL (PDF endpoint)."""
    with patch(
        "src.export.router.export",
        new=AsyncMock(
            side_effect=ReportNotReadyError(
                f"Report not yet available for session {FAKE_SESSION_ID}"
            )
        ),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/pdf")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 422 — invalid UUID path param (Requirement 8.2)
# ---------------------------------------------------------------------------


def test_markdown_422_for_invalid_uuid(client):
    """HTTP 422 is returned when the session_id path param is not a valid UUID."""
    resp = client.get("/api/export/not-a-uuid/markdown")
    assert resp.status_code == 422


def test_pdf_422_for_invalid_uuid(client):
    """HTTP 422 is returned when the session_id path param is not a valid UUID (PDF)."""
    resp = client.get("/api/export/not-a-uuid/pdf")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 422 — invalid delivery_mode (Requirements 4.1, 4.5)
# ---------------------------------------------------------------------------


def test_markdown_422_for_invalid_delivery_mode(client):
    """HTTP 422 is returned when delivery_mode is not 'download' or 'url'."""
    resp = client.get(f"/api/export/{FAKE_SESSION_ID}/markdown?delivery_mode=ftp")
    assert resp.status_code == 422


def test_pdf_422_for_invalid_delivery_mode(client):
    """HTTP 422 is returned when delivery_mode is not 'download' or 'url' (PDF)."""
    resp = client.get(f"/api/export/{FAKE_SESSION_ID}/pdf?delivery_mode=ftp")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 500 — weasyprint / RenderError (Requirements 2.9, 8.3)
# ---------------------------------------------------------------------------


def test_pdf_500_with_render_error_shape(client):
    """HTTP 500 with {detail, reason} when weasyprint raises."""
    with patch(
        "src.export.router.export",
        new=AsyncMock(side_effect=RenderError("weasyprint exploded")),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/pdf")
    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == "PDF rendering failed"
    assert body["reason"] == "weasyprint exploded"


def test_markdown_500_with_render_error_shape(client):
    """HTTP 500 with {detail, reason} when a RenderError is raised on the markdown endpoint."""
    with patch(
        "src.export.router.export",
        new=AsyncMock(side_effect=RenderError("render boom")),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/markdown")
    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == "Markdown rendering failed"
    assert body["reason"] == "render boom"


# ---------------------------------------------------------------------------
# 500 — asyncpg.PostgresError (Requirement 8.1)
# ---------------------------------------------------------------------------


def test_markdown_500_on_postgres_error(client):
    """HTTP 500 with {detail: 'Database error: ...'} when asyncpg raises."""
    with patch(
        "src.export.router.export",
        new=AsyncMock(side_effect=asyncpg.PostgresError()),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/markdown")
    assert resp.status_code == 500
    assert "database error" in resp.json()["detail"].lower()


def test_pdf_500_on_postgres_error(client):
    """HTTP 500 with {detail: 'Database error: ...'} when asyncpg raises (PDF)."""
    with patch(
        "src.export.router.export",
        new=AsyncMock(side_effect=asyncpg.PostgresError()),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/pdf")
    assert resp.status_code == 500
    assert "database error" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# download mode — Content-Type and Content-Disposition (Requirements 1.9, 2.7, 4.2)
# ---------------------------------------------------------------------------


def test_markdown_download_headers(client):
    """delivery_mode=download returns correct Content-Type and Content-Disposition."""
    with patch("src.export.router.export", new=AsyncMock(return_value=_md_result())):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/markdown")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/octet-stream")
    cd = resp.headers["content-disposition"]
    assert "attachment" in cd
    assert f"report-{FAKE_SESSION_ID}.md" in cd


def test_pdf_download_headers(client):
    """delivery_mode=download returns correct Content-Type and Content-Disposition for PDF."""
    with patch("src.export.router.export", new=AsyncMock(return_value=_pdf_result())):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    cd = resp.headers["content-disposition"]
    assert "attachment" in cd
    assert f"report-{FAKE_SESSION_ID}.pdf" in cd


def test_markdown_download_body_content(client):
    """download mode streams the exact bytes returned by the service."""
    with patch("src.export.router.export", new=AsyncMock(return_value=_md_result())):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/markdown")
    assert resp.content == FAKE_MD_CONTENT


# ---------------------------------------------------------------------------
# url mode — JSON response with file_path and url (Requirements 1.10, 2.8, 4.3)
# ---------------------------------------------------------------------------


def test_markdown_url_mode_returns_json(client, tmp_path):
    """delivery_mode=url returns JSON with file_path and url."""
    fake_abs = str(tmp_path / f"report-{FAKE_SESSION_ID}.md")
    fake_url = f"/exports/report-{FAKE_SESSION_ID}.md"

    with patch(
        "src.export.router.export_to_file",
        new=AsyncMock(return_value=(_md_result(), fake_abs, fake_url)),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/markdown?delivery_mode=url")

    assert resp.status_code == 200
    body = resp.json()
    assert body["file_path"] == fake_abs
    assert body["url"] == fake_url


def test_pdf_url_mode_returns_json(client, tmp_path):
    """delivery_mode=url returns JSON with file_path and url (PDF)."""
    fake_abs = str(tmp_path / f"report-{FAKE_SESSION_ID}.pdf")
    fake_url = f"/exports/report-{FAKE_SESSION_ID}.pdf"

    with patch(
        "src.export.router.export_to_file",
        new=AsyncMock(return_value=(_pdf_result(), fake_abs, fake_url)),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/pdf?delivery_mode=url")

    assert resp.status_code == 200
    body = resp.json()
    assert body["file_path"] == fake_abs
    assert body["url"] == fake_url


def test_url_mode_file_exists_on_disk(tmp_path):
    """delivery_mode=url actually writes the file to EXPORT_DIR."""
    export_dir = str(tmp_path / "exports")
    app = _make_app()

    with TestClient(app, raise_server_exceptions=False) as c:
        with patch("src.export.router.export_to_file") as mock_export_to_file:

            async def _fake_export_to_file(
                session_id, fmt, pool, export_dir_arg, base_url_arg
            ):  # noqa: ARG001
                Path(export_dir_arg).mkdir(parents=True, exist_ok=True)
                (Path(export_dir_arg) / f"report-{session_id}.md").write_bytes(
                    FAKE_MD_CONTENT
                )
                return (
                    _md_result(),
                    str((Path(export_dir_arg) / f"report-{session_id}.md").resolve()),
                    f"/exports/report-{session_id}.md",
                )

            mock_export_to_file.side_effect = _fake_export_to_file

            # Patch the module-level constant so the router passes our tmp dir
            with patch("src.export.router.EXPORT_DIR", export_dir):
                resp = c.get(
                    f"/api/export/{FAKE_SESSION_ID}/markdown?delivery_mode=url"
                )

    assert resp.status_code == 200
    expected_file = Path(export_dir) / f"report-{FAKE_SESSION_ID}.md"
    assert expected_file.exists()
    assert expected_file.read_bytes() == FAKE_MD_CONTENT


def test_url_mode_creates_export_dir_if_missing(tmp_path):
    """delivery_mode=url creates EXPORT_DIR when it does not exist (Requirement 4.6)."""
    export_dir = str(tmp_path / "new_exports_dir")
    assert not Path(export_dir).exists()

    app = _make_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        with patch("src.export.router.export_to_file") as mock_export_to_file:

            async def _fake(
                session_id, fmt, pool, export_dir_arg, base_url_arg
            ):  # noqa: ARG001
                Path(export_dir_arg).mkdir(parents=True, exist_ok=True)
                (Path(export_dir_arg) / f"report-{session_id}.md").write_bytes(
                    FAKE_MD_CONTENT
                )
                return (
                    _md_result(),
                    str((Path(export_dir_arg) / f"report-{session_id}.md").resolve()),
                    f"/exports/report-{session_id}.md",
                )

            mock_export_to_file.side_effect = _fake

            with patch("src.export.router.EXPORT_DIR", export_dir):
                resp = c.get(
                    f"/api/export/{FAKE_SESSION_ID}/markdown?delivery_mode=url"
                )

    assert resp.status_code == 200
    assert Path(export_dir).exists()


# ---------------------------------------------------------------------------
# Empty Q&A — ## Q&A History absent (Requirement 1.6)
# ---------------------------------------------------------------------------


def test_markdown_download_no_qa_section_when_empty(client):
    """When Q&A pairs are empty, '## Q&A History' is absent from the output."""
    # Use the real markdown renderer with a minimal DocumentParts
    from src.export.models import DocumentParts, MetadataHeader
    from src.export.renderers import markdown as md_renderer

    parts = DocumentParts(
        metadata=MetadataHeader(
            title="Test",
            session_id=str(FAKE_SESSION_ID),
            exported_at="2025-01-01T00:00:00+00:00",
            format="markdown",
        ),
        report_body="Some report content.",
        qa_pairs=[],
    )
    rendered = md_renderer.render(parts).encode("utf-8")
    result = ExportResult(
        content=rendered,
        filename=f"report-{FAKE_SESSION_ID}.md",
        media_type="application/octet-stream",
        fmt=ExportFormat.markdown,
    )

    with patch("src.export.router.export", new=AsyncMock(return_value=result)):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/markdown")

    assert resp.status_code == 200
    assert "## Q&A History" not in resp.text


# ---------------------------------------------------------------------------
# No stack traces in error responses (Requirement 8.4)
# ---------------------------------------------------------------------------


def test_no_stack_trace_in_404_response(client):
    """Error responses must not contain Python stack trace markers."""
    with patch(
        "src.export.router.export",
        new=AsyncMock(side_effect=SessionNotFoundError("not found")),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/markdown")
    body = resp.text
    assert "Traceback" not in body
    assert 'File "' not in body


def test_no_stack_trace_in_500_response(client):
    """500 error responses must not contain Python stack trace markers."""
    with patch(
        "src.export.router.export",
        new=AsyncMock(side_effect=RenderError("boom")),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/pdf")
    body = resp.text
    assert "Traceback" not in body
    assert 'File "' not in body


# ---------------------------------------------------------------------------
# DOCX endpoint — 404 / 422 / 500 error handling
# ---------------------------------------------------------------------------


def test_docx_404_when_session_not_found(client):
    """HTTP 404 is returned when the session does not exist (DOCX endpoint)."""
    with patch(
        "src.export.router.export",
        new=AsyncMock(
            side_effect=SessionNotFoundError(f"Session {FAKE_SESSION_ID} not found")
        ),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/docx")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_docx_422_when_report_not_ready(client):
    """HTTP 422 is returned when report_markdown is NULL (DOCX endpoint)."""
    with patch(
        "src.export.router.export",
        new=AsyncMock(
            side_effect=ReportNotReadyError(
                f"Report not yet available for session {FAKE_SESSION_ID}"
            )
        ),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/docx")
    assert resp.status_code == 422
    assert "not yet available" in resp.json()["detail"].lower()


def test_docx_422_for_invalid_uuid(client):
    """HTTP 422 is returned when the session_id path param is not a valid UUID (DOCX)."""
    resp = client.get("/api/export/not-a-uuid/docx")
    assert resp.status_code == 422


def test_docx_422_for_invalid_delivery_mode(client):
    """HTTP 422 is returned when delivery_mode is not 'download' or 'url' (DOCX)."""
    resp = client.get(f"/api/export/{FAKE_SESSION_ID}/docx?delivery_mode=ftp")
    assert resp.status_code == 422


def test_docx_500_with_render_error_shape(client):
    """HTTP 500 with {detail, reason} when the DOCX renderer raises a RenderError."""
    with patch(
        "src.export.router.export",
        new=AsyncMock(side_effect=RenderError("python-docx exploded")),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/docx")
    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == "DOCX rendering failed"
    assert body["reason"] == "python-docx exploded"


def test_docx_500_on_postgres_error(client):
    """HTTP 500 with {detail: 'Database error: ...'} when asyncpg raises (DOCX)."""
    with patch(
        "src.export.router.export",
        new=AsyncMock(side_effect=asyncpg.PostgresError()),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/docx")
    assert resp.status_code == 500
    assert "database error" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# DOCX endpoint — download mode headers and body
# ---------------------------------------------------------------------------


def test_docx_download_headers(client):
    """delivery_mode=download returns correct Content-Type and Content-Disposition for DOCX."""
    with patch("src.export.router.export", new=AsyncMock(return_value=_docx_result())):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/docx")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    cd = resp.headers["content-disposition"]
    assert "attachment" in cd
    assert f"report-{FAKE_SESSION_ID}.docx" in cd


def test_docx_download_body_content(client):
    """download mode streams the exact bytes returned by the service (DOCX)."""
    with patch("src.export.router.export", new=AsyncMock(return_value=_docx_result())):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/docx")
    assert resp.content == FAKE_DOCX_CONTENT


# ---------------------------------------------------------------------------
# DOCX endpoint — url mode
# ---------------------------------------------------------------------------


def test_docx_url_mode_returns_json(client, tmp_path):
    """delivery_mode=url returns JSON with file_path and url (DOCX)."""
    fake_abs = str(tmp_path / f"report-{FAKE_SESSION_ID}.docx")
    fake_url = f"/exports/report-{FAKE_SESSION_ID}.docx"

    with patch(
        "src.export.router.export_to_file",
        new=AsyncMock(return_value=(_docx_result(), fake_abs, fake_url)),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/docx?delivery_mode=url")

    assert resp.status_code == 200
    body = resp.json()
    assert body["file_path"] == fake_abs
    assert body["url"] == fake_url


# ---------------------------------------------------------------------------
# DOCX endpoint — no stack traces in error responses
# ---------------------------------------------------------------------------


def test_no_stack_trace_in_docx_404_response(client):
    """Error responses for the DOCX endpoint must not contain stack trace markers."""
    with patch(
        "src.export.router.export",
        new=AsyncMock(side_effect=SessionNotFoundError("not found")),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/docx")
    body = resp.text
    assert "Traceback" not in body
    assert 'File "' not in body


def test_no_stack_trace_in_docx_500_response(client):
    """500 error responses for the DOCX endpoint must not contain stack trace markers."""
    with patch(
        "src.export.router.export",
        new=AsyncMock(side_effect=RenderError("boom")),
    ):
        resp = client.get(f"/api/export/{FAKE_SESSION_ID}/docx")
    body = resp.text
    assert "Traceback" not in body
    assert 'File "' not in body
