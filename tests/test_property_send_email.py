"""
Property tests for ResearchManager.send_email().

Property 3: Email_Agent is never called when EMAIL_ENABLED is False
  For any FinalReportData value, when EMAIL_ENABLED is False, calling
  ResearchManager.send_email() SHALL NOT invoke Runner.run with the Email_Agent.

**Validates: Requirements 2.1, 2.3**
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.core.research_manager import ResearchManager
from src.models.domain import FinalReportData, VerifiedClaims

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Strategy for non-empty strings (short_summary, markdown_report)
non_empty_text = st.text(min_size=1, max_size=200)

# Strategy for a list of follow-up question strings
follow_up_questions_st = st.lists(
    st.text(min_size=1, max_size=100),
    min_size=0,
    max_size=5,
)

# Strategy for FinalReportData — only fields that affect send_email behaviour
# (verified_claims is always empty to keep generation fast)
final_report_data_st = st.builds(
    FinalReportData,
    short_summary=non_empty_text,
    markdown_report=non_empty_text,
    follow_up_questions=follow_up_questions_st,
    verified_claims=st.just(VerifiedClaims(claims=[])),
    total_claims_checked=st.integers(min_value=0, max_value=100),
    dubious_claims_count=st.integers(min_value=0, max_value=100),
    was_edited=st.booleans(),
)


# ---------------------------------------------------------------------------
# Property 3: Email_Agent is never called when EMAIL_ENABLED is False
# ---------------------------------------------------------------------------


@given(report=final_report_data_st)
@settings(max_examples=100)
def test_property_runner_never_called_when_email_disabled(
    report: FinalReportData,
) -> None:
    """**Validates: Requirements 2.1, 2.3**

    For any FinalReportData value, when EMAIL_ENABLED is False,
    ResearchManager.send_email() SHALL NOT invoke Runner.run with the Email_Agent.
    """
    pool = MagicMock(spec=asyncpg.Pool)
    manager = ResearchManager(pool)

    mock_runner_run = AsyncMock()

    with patch("src.config.settings.EMAIL_ENABLED", False), patch(
        "src.core.research_manager.Runner.run", mock_runner_run
    ):
        result = asyncio.run(manager.send_email(report))

    # Runner.run must never have been called
    mock_runner_run.assert_not_called()

    # The return value must be the skip string (sanity check)
    assert result == "Email skipped: EMAIL_ENABLED is not set.\n"
