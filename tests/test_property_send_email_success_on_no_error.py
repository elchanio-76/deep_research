"""
Property 6: Agent output not containing "error" produces the success return value.
Feature: email-delivery-fix, Property 6: Agent output not containing "error" produces the success return value

**Validates: Requirements 4.1**

For any agent output string that does not contain the substring "error"
(case-insensitive), ResearchManager.send_email() SHALL return "Email sent.\n".
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

# Agent output strings that do NOT contain "error" (case-insensitive).
# We generate arbitrary text and filter out any that contain the substring.
agent_output_no_error_st = st.text(min_size=0, max_size=500).filter(
    lambda s: "error" not in s.lower()
)


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


def _make_mock_runner_result(output_text: str):
    """Build a mock object that mimics the result of Runner.run(...)."""
    mock_result = MagicMock()
    mock_result.final_output = output_text
    mock_result.context_wrapper.usage.input_tokens = 0
    mock_result.context_wrapper.usage.output_tokens = 0
    return mock_result


# ---------------------------------------------------------------------------
# Property 6: Agent output not containing "error" produces the success return value
# ---------------------------------------------------------------------------


@given(
    markdown=markdown_report_st,
    agent_output=agent_output_no_error_st,
)
@settings(max_examples=200)
def test_send_email_success_when_agent_output_has_no_error(
    markdown: str,
    agent_output: str,
) -> None:
    """**Validates: Requirements 4.1**

    For any agent output string that does not contain the substring "error"
    (case-insensitive), ResearchManager.send_email() SHALL return "Email sent.\n".
    """
    pool = MagicMock(spec=asyncpg.Pool)
    manager = ResearchManager(pool)
    report = _make_report(markdown)
    mock_result = _make_mock_runner_result(agent_output)

    with (
        patch(
            "src.core.research_manager.EMAIL_ENABLED",
            True,
            create=True,
        ),
        patch("src.config.settings.EMAIL_ENABLED", True),
        patch("src.config.settings.SENDER", "sender@example.com"),
        patch("src.config.settings.RECIPIENT", "recipient@example.com"),
        patch(
            "src.core.research_manager.Runner.run",
            new=AsyncMock(return_value=mock_result),
        ),
    ):
        result = asyncio.run(manager.send_email(report))

    assert result == "Email sent.\n", (
        f"send_email() returned {result!r} instead of 'Email sent.\\n'. "
        f"(agent_output={agent_output!r})"
    )
