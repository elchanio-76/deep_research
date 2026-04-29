"""Export service — assembles document content and delegates to renderers.

This module is stateless: it receives the database pool as a parameter on
each call, matching the pattern used by ``src/db/sessions.py`` and
``src/db/messages.py``.  No LLM is invoked.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import asyncpg

from src.config.settings import EXPORT_BASE_URL, EXPORT_DIR
from src.db import messages as db_messages
from src.db import sessions as db_sessions
from src.export.errors import RenderError, ReportNotReadyError, SessionNotFoundError
from src.export.models import (
    DocumentParts,
    ExportFormat,
    ExportResult,
    MetadataHeader,
    QAPair,
)
from src.export.renderers import docx as docx_renderer
from src.export.renderers import markdown as markdown_renderer
from src.export.renderers import pdf as pdf_renderer


def _build_qa_pairs(messages: list[dict]) -> list[QAPair]:
    """Pair user/assistant messages into QAPair instances.

    Messages are processed in order.  A user message opens a pair; the
    following assistant message closes it.  Unpaired trailing messages are
    included with an empty counterpart.
    """
    pairs: list[QAPair] = []
    pending_question: str | None = None

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user":
            # If there was an unanswered question, close it with an empty answer
            if pending_question is not None:
                pairs.append(QAPair(question=pending_question, answer=""))
            pending_question = content
        elif role == "assistant":
            question = pending_question if pending_question is not None else ""
            pairs.append(QAPair(question=question, answer=content))
            pending_question = None

    # Close any trailing unanswered question
    if pending_question is not None:
        pairs.append(QAPair(question=pending_question, answer=""))

    return pairs


async def export(
    session_id: UUID,
    fmt: ExportFormat,
    pool: asyncpg.Pool,
) -> ExportResult:
    """Assemble and render an export document for *session_id*.

    Args:
        session_id: UUID of the research session to export.
        fmt: Target export format (markdown or pdf).
        pool: asyncpg connection pool.

    Returns:
        An :class:`ExportResult` containing the rendered bytes, filename,
        media type, and format.

    Raises:
        SessionNotFoundError: if the session does not exist (→ HTTP 404).
        ReportNotReadyError: if ``report_markdown`` is NULL (→ HTTP 422).
        RenderError: if the renderer raises an exception (→ HTTP 500).
    """
    # --- 1. Fetch session (Requirements 1.2, 2.2) ---
    session = await db_sessions.load_session(pool, session_id)
    if session is None:
        raise SessionNotFoundError(f"Session {session_id} not found")

    # --- 2. Guard: report must be ready (Requirements 1.7, 2.5) ---
    report_markdown: str | None = session.get("report_markdown")
    if report_markdown is None:
        raise ReportNotReadyError(f"Report not yet available for session {session_id}")

    # --- 3. Fetch conversation history (Requirements 1.2, 2.2) ---
    messages = await db_messages.fetch_chat_messages(pool, session_id)

    # --- 4. Build DocumentParts (Requirements 3.1, 3.2, 3.3, 3.4) ---
    title = MetadataHeader.derive_title(
        header=session.get("header"),
        initial_prompt=session.get("initial_prompt", ""),
    )
    metadata = MetadataHeader(
        title=title,
        session_id=str(session_id),
        exported_at=MetadataHeader.now_utc(),
        format=fmt.value,
    )
    qa_pairs = _build_qa_pairs(messages)
    parts = DocumentParts(
        metadata=metadata,
        report_body=report_markdown,
        qa_pairs=qa_pairs,
    )

    # --- 5. Render (Requirements 1.3, 2.3) ---
    filename = ExportResult.filename_for(str(session_id), fmt)

    try:
        if fmt == ExportFormat.markdown:
            content_str = markdown_renderer.render(parts)
            content = content_str.encode("utf-8")
            media_type = "application/octet-stream"
        elif fmt == ExportFormat.pdf:
            content = pdf_renderer.render(parts)
            media_type = "application/pdf"
        else:  # docx
            content = docx_renderer.render(parts)
            media_type = (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
    except RenderError:
        raise
    except Exception as exc:
        raise RenderError(str(exc)) from exc

    return ExportResult(
        content=content,
        filename=filename,
        media_type=media_type,
        fmt=fmt,
    )


async def export_to_file(
    session_id: UUID,
    fmt: ExportFormat,
    pool: asyncpg.Pool,
    export_dir: str = EXPORT_DIR,
    base_url: str = EXPORT_BASE_URL,
) -> tuple[ExportResult, str, str]:
    """Export and write the result to *export_dir*.

    Creates *export_dir* if it does not exist (Requirement 4.6).

    Returns:
        A tuple of ``(ExportResult, absolute_file_path, relative_url)``.
    """
    result = await export(session_id, fmt, pool)

    dest_dir = Path(export_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    file_path = dest_dir / result.filename
    file_path.write_bytes(result.content)

    relative_url = f"{base_url.rstrip('/')}/{result.filename}"
    return result, str(file_path.resolve()), relative_url
