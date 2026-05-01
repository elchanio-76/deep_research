"""Unit tests for Export_Service (src/export/service.py).

All database calls are mocked so no real DB connection is required.
Requirements: 1.7, 1.8, 2.5, 2.6, 2.9
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.export.errors import RenderError, ReportNotReadyError, SessionNotFoundError
from src.export.models import ExportFormat, ExportResult
from src.export.service import _build_qa_pairs, export


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_SESSION_ID = uuid.UUID("12345678-1234-5678-1234-567812345678")

VALID_SESSION = {
    "id": FAKE_SESSION_ID,
    "header": "Test Report",
    "initial_prompt": "What is the capital of France?",
    "report_markdown": "# Report\n\nParis is the capital of France.",
    "search_mode": "no_adaptive",
    "cost_effective_search": False,
    "usage_jsonb": None,
    "cost_summary_jsonb": None,
    "created_at": None,
    "updated_at": None,
    "last_activity_at": None,
}

CHAT_MESSAGES = [
    {"role": "user", "content": "What about Lyon?"},
    {"role": "assistant", "content": "Lyon is the second-largest city."},
]


def _make_pool() -> MagicMock:
    """Return a minimal mock that satisfies asyncpg.Pool type hints."""
    return MagicMock()


# ---------------------------------------------------------------------------
# SessionNotFoundError (Requirement 1.8)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_raises_session_not_found_when_load_session_returns_none():
    pool = _make_pool()
    with patch(
        "src.export.service.db_sessions.load_session",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(SessionNotFoundError):
            await export(FAKE_SESSION_ID, ExportFormat.markdown, pool)


# ---------------------------------------------------------------------------
# ReportNotReadyError (Requirement 1.7, 2.5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_raises_report_not_ready_when_report_markdown_is_none():
    pool = _make_pool()
    session_no_report = {**VALID_SESSION, "report_markdown": None}
    with patch(
        "src.export.service.db_sessions.load_session",
        new=AsyncMock(return_value=session_no_report),
    ):
        with pytest.raises(ReportNotReadyError):
            await export(FAKE_SESSION_ID, ExportFormat.markdown, pool)


# ---------------------------------------------------------------------------
# RenderError propagation (Requirement 2.9)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_wraps_renderer_exception_in_render_error():
    pool = _make_pool()
    with (
        patch(
            "src.export.service.db_sessions.load_session",
            new=AsyncMock(return_value=VALID_SESSION),
        ),
        patch(
            "src.export.service.db_messages.fetch_chat_messages",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "src.export.service.markdown_renderer.render",
            side_effect=RuntimeError("boom"),
        ),
    ):
        with pytest.raises(RenderError):
            await export(FAKE_SESSION_ID, ExportFormat.markdown, pool)


@pytest.mark.asyncio
async def test_export_re_raises_render_error_unchanged():
    """A RenderError raised by the renderer should propagate as-is."""
    pool = _make_pool()
    original = RenderError("weasyprint exploded")
    with (
        patch(
            "src.export.service.db_sessions.load_session",
            new=AsyncMock(return_value=VALID_SESSION),
        ),
        patch(
            "src.export.service.db_messages.fetch_chat_messages",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "src.export.service.pdf_renderer.render",
            side_effect=original,
        ),
    ):
        with pytest.raises(RenderError) as exc_info:
            await export(FAKE_SESSION_ID, ExportFormat.pdf, pool)
        assert exc_info.value is original


# ---------------------------------------------------------------------------
# Successful markdown export (Requirements 1.2, 3.1, 4.4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_markdown_returns_correct_result():
    pool = _make_pool()
    with (
        patch(
            "src.export.service.db_sessions.load_session",
            new=AsyncMock(return_value=VALID_SESSION),
        ),
        patch(
            "src.export.service.db_messages.fetch_chat_messages",
            new=AsyncMock(return_value=CHAT_MESSAGES),
        ),
    ):
        result = await export(FAKE_SESSION_ID, ExportFormat.markdown, pool)

    assert isinstance(result, ExportResult)
    assert result.fmt == ExportFormat.markdown
    assert result.filename == f"report-{FAKE_SESSION_ID}.md"
    assert result.media_type == "application/octet-stream"
    assert isinstance(result.content, bytes)
    assert len(result.content) > 0


# ---------------------------------------------------------------------------
# Successful PDF export (Requirements 2.2, 2.3, 4.4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_pdf_returns_correct_result():
    pool = _make_pool()
    fake_pdf = b"%PDF-1.4 fake"
    with (
        patch(
            "src.export.service.db_sessions.load_session",
            new=AsyncMock(return_value=VALID_SESSION),
        ),
        patch(
            "src.export.service.db_messages.fetch_chat_messages",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "src.export.service.pdf_renderer.render",
            return_value=fake_pdf,
        ),
    ):
        result = await export(FAKE_SESSION_ID, ExportFormat.pdf, pool)

    assert isinstance(result, ExportResult)
    assert result.fmt == ExportFormat.pdf
    assert result.filename == f"report-{FAKE_SESSION_ID}.pdf"
    assert result.media_type == "application/pdf"
    assert result.content == fake_pdf


# ---------------------------------------------------------------------------
# Title derivation (Requirements 3.2, 3.3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_uses_header_as_title_when_present():
    pool = _make_pool()
    with (
        patch(
            "src.export.service.db_sessions.load_session",
            new=AsyncMock(return_value=VALID_SESSION),
        ),
        patch(
            "src.export.service.db_messages.fetch_chat_messages",
            new=AsyncMock(return_value=[]),
        ),
    ):
        result = await export(FAKE_SESSION_ID, ExportFormat.markdown, pool)

    decoded = result.content.decode("utf-8")
    assert "Test Report" in decoded


@pytest.mark.asyncio
async def test_export_derives_title_from_initial_prompt_when_header_is_none():
    pool = _make_pool()
    long_prompt = "A" * 130
    session = {**VALID_SESSION, "header": None, "initial_prompt": long_prompt}
    with (
        patch(
            "src.export.service.db_sessions.load_session",
            new=AsyncMock(return_value=session),
        ),
        patch(
            "src.export.service.db_messages.fetch_chat_messages",
            new=AsyncMock(return_value=[]),
        ),
    ):
        result = await export(FAKE_SESSION_ID, ExportFormat.markdown, pool)

    decoded = result.content.decode("utf-8")
    assert "A" * 120 + "…" in decoded


# ---------------------------------------------------------------------------
# _build_qa_pairs unit tests
# ---------------------------------------------------------------------------


def test_build_qa_pairs_empty_messages():
    assert _build_qa_pairs([]) == []


def test_build_qa_pairs_single_exchange():
    msgs = [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1"},
    ]
    pairs = _build_qa_pairs(msgs)
    assert len(pairs) == 1
    assert pairs[0].question == "Q1"
    assert pairs[0].answer == "A1"


def test_build_qa_pairs_multiple_exchanges():
    msgs = [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "Q2"},
        {"role": "assistant", "content": "A2"},
    ]
    pairs = _build_qa_pairs(msgs)
    assert len(pairs) == 2
    assert pairs[1].question == "Q2"
    assert pairs[1].answer == "A2"


def test_build_qa_pairs_trailing_unanswered_question():
    msgs = [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "Q2"},
    ]
    pairs = _build_qa_pairs(msgs)
    assert len(pairs) == 2
    assert pairs[1].question == "Q2"
    assert pairs[1].answer == ""


def test_build_qa_pairs_assistant_only_messages():
    msgs = [{"role": "assistant", "content": "Unprompted answer"}]
    pairs = _build_qa_pairs(msgs)
    assert len(pairs) == 1
    assert pairs[0].question == ""
    assert pairs[0].answer == "Unprompted answer"


# ---------------------------------------------------------------------------
# Successful DOCX export
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_docx_returns_correct_result():
    """export() with ExportFormat.docx returns a valid ExportResult."""
    pool = _make_pool()
    fake_docx = b"PK\x03\x04fake docx bytes"
    with (
        patch(
            "src.export.service.db_sessions.load_session",
            new=AsyncMock(return_value=VALID_SESSION),
        ),
        patch(
            "src.export.service.db_messages.fetch_chat_messages",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "src.export.service.docx_renderer.render",
            return_value=fake_docx,
        ),
    ):
        result = await export(FAKE_SESSION_ID, ExportFormat.docx, pool)

    assert isinstance(result, ExportResult)
    assert result.fmt == ExportFormat.docx
    assert result.filename == f"report-{FAKE_SESSION_ID}.docx"
    assert result.media_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert result.content == fake_docx


@pytest.mark.asyncio
async def test_export_docx_wraps_renderer_exception_in_render_error():
    """A non-RenderError raised by the DOCX renderer is wrapped in RenderError."""
    pool = _make_pool()
    with (
        patch(
            "src.export.service.db_sessions.load_session",
            new=AsyncMock(return_value=VALID_SESSION),
        ),
        patch(
            "src.export.service.db_messages.fetch_chat_messages",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "src.export.service.docx_renderer.render",
            side_effect=RuntimeError("docx boom"),
        ),
    ):
        with pytest.raises(RenderError):
            await export(FAKE_SESSION_ID, ExportFormat.docx, pool)


@pytest.mark.asyncio
async def test_export_docx_re_raises_render_error_unchanged():
    """A RenderError raised by the DOCX renderer propagates as-is."""
    pool = _make_pool()
    original = RenderError("python-docx exploded")
    with (
        patch(
            "src.export.service.db_sessions.load_session",
            new=AsyncMock(return_value=VALID_SESSION),
        ),
        patch(
            "src.export.service.db_messages.fetch_chat_messages",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "src.export.service.docx_renderer.render",
            side_effect=original,
        ),
    ):
        with pytest.raises(RenderError) as exc_info:
            await export(FAKE_SESSION_ID, ExportFormat.docx, pool)
        assert exc_info.value is original


@pytest.mark.asyncio
async def test_export_docx_passes_qa_pairs_to_renderer():
    """The DOCX renderer receives DocumentParts with the correct Q&A pairs."""
    pool = _make_pool()
    captured: list = []

    def _capture_render(parts):
        captured.append(parts)
        return b"PK\x03\x04fake"

    with (
        patch(
            "src.export.service.db_sessions.load_session",
            new=AsyncMock(return_value=VALID_SESSION),
        ),
        patch(
            "src.export.service.db_messages.fetch_chat_messages",
            new=AsyncMock(return_value=CHAT_MESSAGES),
        ),
        patch(
            "src.export.service.docx_renderer.render",
            side_effect=_capture_render,
        ),
    ):
        await export(FAKE_SESSION_ID, ExportFormat.docx, pool)

    assert len(captured) == 1
    parts = captured[0]
    assert len(parts.qa_pairs) == 1
    assert parts.qa_pairs[0].question == "What about Lyon?"
    assert parts.qa_pairs[0].answer == "Lyon is the second-largest city."
