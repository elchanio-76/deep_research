"""
Property 4: Email_Agent is never called when credentials are missing.
Feature: email-delivery-fix, Property 4: Email_Agent never called when credentials are missing

**Validates: Requirements 3.1, 3.2, 3.4**

For any FinalReportData value and any combination of empty SENDER or empty
RECIPIENT (with EMAIL_ENABLED=True), calling ResearchManager.send_email()
SHALL NOT invoke Runner.run with the Email_Agent.

Covers:
- SENDER="" with EMAIL_ENABLED=True and any RECIPIENT
- RECIPIENT="" with EMAIL_ENABLED=True and any SENDER
- Both SENDER="" and RECIPIENT="" with EMAIL_ENABLED=True
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
from hypothesis import given, settings
from hypothesis import strategies as st

from src.core.research_manager import ResearchManager
from src.models.domain import FinalReportData, VerifiedClaims


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Arbitrary non-empty markdown report text
markdown_report_st = st.text(min_size=1, max_size=500)

# Non-empty email address (represents a configured credential)
non_empty_email_st = st.text(min_size=1, max_size=80).filter(lambda s: s.strip() != "")


def _make_report(markdown: str) -> FinalReportData:
    """Build a minimal FinalReportData with the given markdown_report."""
    return FinalReportData(
        short_summary="summary",
        markdown_report=markdown,
        follow_up_questions=[],
        verified_claims=VerifiedClaims(claims=[]),
        total_claims_checked=0,
        dubious_claims_count=0,
        was_edited=False,
    )


# ---------------------------------------------------------------------------
# Property 4a: Runner.run is never called when SENDER is empty
# ---------------------------------------------------------------------------


@given(
    markdown=markdown_report_st,
    recipient=non_empty_email_st,
)
@settings(max_examples=100)
def test_runner_not_called_when_sender_is_empty(
    markdown: str,
    recipient: str,
) -> None:
    """**Validates: Requirements 3.1, 3.4**

    When EMAIL_ENABLED=True and SENDER is an empty string (regardless of
    RECIPIENT), ResearchManager.send_email() SHALL NOT invoke Runner.run.
    """
    pool = MagicMock(spec=asyncpg.Pool)
    manager = ResearchManager(pool)
    report = _make_report(markdown)
    mock_runner_run = AsyncMock()

    with (
        patch("src.config.settings.EMAIL_ENABLED", True),
        patch("src.config.settings.SENDER", ""),
        patch("src.config.settings.RECIPIENT", recipient),
        patch(
            "src.core.research_manager.Runner.run",
            new=mock_runner_run,
        ),
    ):
        asyncio.run(manager.send_email(report))

    mock_runner_run.assert_not_called()


# ---------------------------------------------------------------------------
# Property 4b: Runner.run is never called when RECIPIENT is empty
# ---------------------------------------------------------------------------


@given(
    markdown=markdown_report_st,
    sender=non_empty_email_st,
)
@settings(max_examples=100)
def test_runner_not_called_when_recipient_is_empty(
    markdown: str,
    sender: str,
) -> None:
    """**Validates: Requirements 3.2, 3.4**

    When EMAIL_ENABLED=True and RECIPIENT is an empty string (regardless of
    SENDER), ResearchManager.send_email() SHALL NOT invoke Runner.run.
    """
    pool = MagicMock(spec=asyncpg.Pool)
    manager = ResearchManager(pool)
    report = _make_report(markdown)
    mock_runner_run = AsyncMock()

    with (
        patch("src.config.settings.EMAIL_ENABLED", True),
        patch("src.config.settings.SENDER", sender),
        patch("src.config.settings.RECIPIENT", ""),
        patch(
            "src.core.research_manager.Runner.run",
            new=mock_runner_run,
        ),
    ):
        asyncio.run(manager.send_email(report))

    mock_runner_run.assert_not_called()


# ---------------------------------------------------------------------------
# Property 4c: Runner.run is never called when both SENDER and RECIPIENT are empty
# ---------------------------------------------------------------------------


@given(
    markdown=markdown_report_st,
)
@settings(max_examples=100)
def test_runner_not_called_when_both_credentials_empty(
    markdown: str,
) -> None:
    """**Validates: Requirements 3.1, 3.2, 3.4**

    When EMAIL_ENABLED=True and both SENDER and RECIPIENT are empty strings,
    ResearchManager.send_email() SHALL NOT invoke Runner.run.
    """
    pool = MagicMock(spec=asyncpg.Pool)
    manager = ResearchManager(pool)
    report = _make_report(markdown)
    mock_runner_run = AsyncMock()

    with (
        patch("src.config.settings.EMAIL_ENABLED", True),
        patch("src.config.settings.SENDER", ""),
        patch("src.config.settings.RECIPIENT", ""),
        patch(
            "src.core.research_manager.Runner.run",
            new=mock_runner_run,
        ),
    ):
        asyncio.run(manager.send_email(report))

    mock_runner_run.assert_not_called()
