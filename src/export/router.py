"""Export router — FastAPI endpoints for Markdown and PDF report export.

Mounted at ``/api/export`` in ``src/api/main.py``.  All export logic is
delegated to :mod:`src.export.service`; this module only handles HTTP
concerns (request parsing, response construction, error translation).

No LLM is invoked.  The router depends only on ``get_pool`` from
``src/api/dependencies.py`` — never on ``get_research_manager`` or any
agent module.

Requirements: 1.1, 1.9, 1.10, 2.1, 2.7, 2.8, 4.1, 4.2, 4.3, 4.5,
              6.1, 6.2, 6.3, 6.4, 8.1, 8.2, 8.3, 8.4
"""

from __future__ import annotations

import io
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from src.api.dependencies import get_pool
from src.config.settings import EXPORT_BASE_URL, EXPORT_DIR
from src.export.errors import RenderError, ReportNotReadyError, SessionNotFoundError
from src.export.models import DeliveryMode, ExportFormat, ExportUrlResponse
from src.export.service import export, export_to_file

router = APIRouter(prefix="/export", tags=["export"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _download_response(
    content: bytes, media_type: str, filename: str
) -> StreamingResponse:
    """Return a ``StreamingResponse`` that triggers a file download."""
    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _error_json(status_code: int, detail: str, **extra) -> JSONResponse:
    """Return a ``JSONResponse`` with a ``detail`` field and optional extras."""
    body: dict = {"detail": detail, **extra}
    return JSONResponse(status_code=status_code, content=body)


# ---------------------------------------------------------------------------
# Markdown endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/{session_id}/markdown",
    summary="Export session report as Markdown",
    description=(
        "Export the research report and Q&A conversation history for the given "
        "session as a Markdown document.\n\n"
        "**Parameters**\n"
        "- `session_id` (path, UUID): the research session to export.\n"
        "- `delivery_mode` (query, default `download`): `download` streams the "
        "  file directly in the response body; `url` writes the file to the "
        "  server-side export directory and returns a JSON object with "
        "  `file_path` and `url`.\n\n"
        "**Responses**\n"
        "- `200 OK`: Markdown file (download mode) or `{file_path, url}` JSON (url mode).\n"
        "- `404 Not Found`: session does not exist.\n"
        "- `422 Unprocessable Entity`: report not yet available, or invalid parameters.\n"
        "- `500 Internal Server Error`: database or rendering failure.\n\n"
        "No LLM is invoked; export is purely deterministic document generation."
    ),
    response_class=StreamingResponse,
)
async def export_markdown(
    session_id: UUID,
    delivery_mode: DeliveryMode = DeliveryMode.download,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Export a session report as a Markdown document."""
    try:
        if delivery_mode == DeliveryMode.download:
            result = await export(session_id, ExportFormat.markdown, pool)
            return _download_response(
                result.content, result.media_type, result.filename
            )
        else:
            result, file_path, url = await export_to_file(
                session_id, ExportFormat.markdown, pool, EXPORT_DIR, EXPORT_BASE_URL
            )
            return JSONResponse(
                content=ExportUrlResponse(file_path=file_path, url=url).model_dump()
            )
    except SessionNotFoundError as exc:
        return _error_json(404, str(exc))
    except ReportNotReadyError as exc:
        return _error_json(422, str(exc))
    except RenderError as exc:
        return _error_json(500, "PDF rendering failed", reason=exc.reason)
    except asyncpg.PostgresError as exc:
        return _error_json(500, f"Database error: {type(exc).__name__}")


# ---------------------------------------------------------------------------
# PDF endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/{session_id}/pdf",
    summary="Export session report as PDF",
    description=(
        "Export the research report and Q&A conversation history for the given "
        "session as a PDF document.\n\n"
        "**Parameters**\n"
        "- `session_id` (path, UUID): the research session to export.\n"
        "- `delivery_mode` (query, default `download`): `download` streams the "
        "  PDF directly in the response body; `url` writes the file to the "
        "  server-side export directory and returns a JSON object with "
        "  `file_path` and `url`.\n\n"
        "**Responses**\n"
        "- `200 OK`: PDF file (download mode) or `{file_path, url}` JSON (url mode).\n"
        "- `404 Not Found`: session does not exist.\n"
        "- `422 Unprocessable Entity`: report not yet available, or invalid parameters.\n"
        "- `500 Internal Server Error`: database or rendering failure.\n\n"
        "No LLM is invoked; the PDF is generated deterministically from stored "
        "session data using weasyprint."
    ),
    response_class=StreamingResponse,
)
async def export_pdf(
    session_id: UUID,
    delivery_mode: DeliveryMode = DeliveryMode.download,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Export a session report as a PDF document."""
    try:
        if delivery_mode == DeliveryMode.download:
            result = await export(session_id, ExportFormat.pdf, pool)
            return _download_response(
                result.content, result.media_type, result.filename
            )
        else:
            result, file_path, url = await export_to_file(
                session_id, ExportFormat.pdf, pool, EXPORT_DIR, EXPORT_BASE_URL
            )
            return JSONResponse(
                content=ExportUrlResponse(file_path=file_path, url=url).model_dump()
            )
    except SessionNotFoundError as exc:
        return _error_json(404, str(exc))
    except ReportNotReadyError as exc:
        return _error_json(422, str(exc))
    except RenderError as exc:
        return _error_json(500, "PDF rendering failed", reason=exc.reason)
    except asyncpg.PostgresError as exc:
        return _error_json(500, f"Database error: {type(exc).__name__}")
