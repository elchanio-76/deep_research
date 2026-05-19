"""
Property 2: send_email always returns a non-empty str.
Feature: email-delivery-fix, Property 2: send_email always returns a str

**Validates: Requirements 4.3**

For any call to ResearchManager.send_email() — regardless of the values of
EMAIL_ENABLED, SENDER, RECIPIENT, or the agent output — the return value SHALL
be of type str and SHALL be non-empty.
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

# Arbitrary agent output text (what Runner.run returns as final_output)
agent_output_st = st.text(min_size=0, max_size=500)

# Boolean for EMAIL_ENABLED
email_enabled_st = st.booleans()

# SENDER / RECIPIENT: either empty string or a non-empty string
email_address_st = st.one_of(st.just(""), st.text(min_size=1, max_size=50))


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
# Property 2: send_email always returns a non-empty str
# ---------------------------------------------------------------------------


@given(
    markdown=markdown_report_st,
    email_enabled=email_enabled_st,
    sender=email_address_st,
    recipient=email_address_st,
    agent_output=agent_output_st,
)
@settings(max_examples=200)
def test_send_email_always_returns_non_empty_str(
    markdown: str,
    email_enabled: bool,
    sender: str,
    recipient: str,
    agent_output: str,
) -> None:
    """**Validates: Requirements 4.3**

    For any combination of EMAIL_ENABLED, SENDER, RECIPIENT, and agent output,
    ResearchManager.send_email() SHALL return a value of type str and SHALL be
    non-empty.
    """
    pool = MagicMock(spec=asyncpg.Pool)
    manager = ResearchManager(pool)
    report = _make_report(markdown)
    mock_result = _make_mock_runner_result(agent_output)

    with (
        patch(
            "src.core.research_manager.EMAIL_ENABLED",
            email_enabled,
            create=True,
        ),
        patch("src.config.settings.EMAIL_ENABLED", email_enabled),
        patch("src.config.settings.SENDER", sender),
        patch("src.config.settings.RECIPIENT", recipient),
        patch(
            "src.core.research_manager.Runner.run",
            new=AsyncMock(return_value=mock_result),
        ),
    ):
        result = asyncio.run(manager.send_email(report))

    assert isinstance(result, str), (
        f"send_email() returned {type(result).__name__!r}, expected str. "
        f"(EMAIL_ENABLED={email_enabled}, SENDER={sender!r}, "
        f"RECIPIENT={recipient!r}, agent_output={agent_output!r})"
    )
    assert len(result) > 0, (
        f"send_email() returned an empty string. "
        f"(EMAIL_ENABLED={email_enabled}, SENDER={sender!r}, "
        f"RECIPIENT={recipient!r}, agent_output={agent_output!r})"
    )
