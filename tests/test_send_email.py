"""
Unit tests for the updated ResearchManager.send_email() method and its
integration with the SSE stream produced by ResearchManager.run().

Tests:
  - test_send_email_skipped_when_disabled        (Requirements 2.1, 2.2)
  - test_send_email_skipped_when_no_credentials  (Requirements 3.1, 3.3)
  - test_send_email_success                      (Requirements 4.1)
  - test_send_email_failure_surfaced             (Requirements 4.2)
  - test_run_yields_email_status                 (Requirements 5.2)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest

from src.core.research_manager import ResearchManager
from src.models.domain import FinalReportData, VerifiedClaims

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pool() -> MagicMock:
    """Return a MagicMock spec'd to asyncpg.Pool."""
    return MagicMock(spec=asyncpg.Pool)


def _make_report() -> FinalReportData:
    """Minimal FinalReportData sufficient for send_email() calls."""
    return FinalReportData(
        short_summary="Test summary",
        markdown_report="# Test Report\n\nSome content.",
        follow_up_questions=[],
        verified_claims=VerifiedClaims(claims=[]),
        total_claims_checked=0,
        dubious_claims_count=0,
        was_edited=False,
    )


def _make_mock_runner_result(output_text: str) -> MagicMock:
    """Build a mock Runner.run result whose final_output stringifies to output_text."""
    mock_result = MagicMock()
    mock_result.final_output = output_text
    mock_result.context_wrapper.usage = MagicMock(input_tokens=10, output_tokens=20)
    return mock_result


# ---------------------------------------------------------------------------
# Test 1: send_email skipped when EMAIL_ENABLED is False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_email_skipped_when_disabled() -> None:
    """Requirements 2.1, 2.2 — when EMAIL_ENABLED=False, send_email() returns
    the skip string and Runner.run is never called.
    """
    manager = ResearchManager(_make_pool())
    report = _make_report()
    mock_runner_run = AsyncMock()

    with (
        patch("src.config.settings.EMAIL_ENABLED", False),
        patch("src.core.research_manager.Runner.run", mock_runner_run),
    ):
        result = await manager.send_email(report)

    assert result == "Email skipped: EMAIL_ENABLED is not set.\n"
    mock_runner_run.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2: send_email skipped when SENDER is empty (no credentials)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_email_skipped_when_no_credentials() -> None:
    """Requirements 3.1, 3.3 — when EMAIL_ENABLED=True but SENDER is empty,
    send_email() returns the missing-credentials skip string and Runner.run
    is never called.
    """
    manager = ResearchManager(_make_pool())
    report = _make_report()
    mock_runner_run = AsyncMock()

    with (
        patch("src.config.settings.EMAIL_ENABLED", True),
        patch("src.config.settings.SENDER", ""),
        patch("src.config.settings.RECIPIENT", "recipient@example.com"),
        patch("src.core.research_manager.Runner.run", mock_runner_run),
    ):
        result = await manager.send_email(report)

    assert result == "Email skipped: SENDER or RECIPIENT not configured.\n"
    mock_runner_run.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: send_email returns "Email sent.\n" on success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_email_success() -> None:
    """Requirements 4.1 — when EMAIL_ENABLED=True, credentials are set, and
    the agent output does not contain "error", send_email() returns "Email sent.\n".
    """
    manager = ResearchManager(_make_pool())
    report = _make_report()
    mock_result = _make_mock_runner_result('{"status": "success", "message": "Sent"}')

    with (
        patch("src.config.settings.EMAIL_ENABLED", True),
        patch("src.config.settings.SENDER", "sender@example.com"),
        patch("src.config.settings.RECIPIENT", "recipient@example.com"),
        patch(
            "src.core.research_manager.Runner.run",
            new=AsyncMock(return_value=mock_result),
        ),
    ):
        result = await manager.send_email(report)

    assert result == "Email sent.\n"


# ---------------------------------------------------------------------------
# Test 4: send_email surfaces a warning when agent output contains "error"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_email_failure_surfaced() -> None:
    """Requirements 4.2 — when the agent output contains "error" (case-insensitive),
    send_email() returns a string containing "Warning".
    """
    manager = ResearchManager(_make_pool())
    report = _make_report()
    mock_result = _make_mock_runner_result(
        '{"status": "error", "message": "SES rejected the request"}'
    )

    with (
        patch("src.config.settings.EMAIL_ENABLED", True),
        patch("src.config.settings.SENDER", "sender@example.com"),
        patch("src.config.settings.RECIPIENT", "recipient@example.com"),
        patch(
            "src.core.research_manager.Runner.run",
            new=AsyncMock(return_value=mock_result),
        ),
    ):
        result = await manager.send_email(report)

    assert "Warning" in result


# ---------------------------------------------------------------------------
# Test 5: run() yields the string returned by send_email() in the SSE stream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_yields_email_status() -> None:
    """Requirements 5.2 — the string returned by send_email() is yielded into
    the SSE stream produced by ResearchManager.run().

    The entire pipeline is mocked so only the email step is exercised.
    """
    manager = ResearchManager(_make_pool())

    # Build the final report that the mocked pipeline will produce
    final_report = _make_report()

    # Mock all async pipeline steps so run() reaches the email step
    mock_plan_searches = AsyncMock(return_value=MagicMock(searches=[]))
    mock_perform_searches = AsyncMock(return_value=[])
    mock_write_report = AsyncMock(
        return_value=MagicMock(
            short_summary="summary",
            markdown_report="# Report",
            follow_up_questions=[],
        )
    )
    mock_fact_check = AsyncMock(return_value=VerifiedClaims(claims=[]))
    mock_generate_header = AsyncMock(return_value="Test Session")
    mock_insert_message = AsyncMock()
    mock_update_session = AsyncMock()
    mock_create_session = AsyncMock()

    # send_email returns a known status string
    expected_email_status = "Email sent.\n"
    mock_send_email = AsyncMock(return_value=expected_email_status)

    with (
        patch.object(manager, "plan_searches", mock_plan_searches),
        patch.object(manager, "perform_searches", mock_perform_searches),
        patch.object(manager, "write_report", mock_write_report),
        patch.object(manager, "fact_check_report", mock_fact_check),
        patch.object(manager, "_generate_session_header", mock_generate_header),
        patch.object(manager, "_insert_message", mock_insert_message),
        patch.object(manager, "_update_session", mock_update_session),
        patch.object(manager, "_create_session", mock_create_session),
        patch.object(manager, "send_email", mock_send_email),
        # Suppress the trace context manager
        patch("src.core.research_manager.trace"),
        patch("src.core.research_manager.gen_trace_id", return_value="trace-123"),
    ):
        yielded_chunks: list[str] = []
        async for chunk in manager.run("test query"):
            yielded_chunks.append(chunk)

    assert expected_email_status in yielded_chunks, (
        f"Expected {expected_email_status!r} in SSE stream, "
        f"but got: {yielded_chunks!r}"
    )
