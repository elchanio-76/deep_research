"""
Property 5: Agent output containing "error" produces a warning return value.
Feature: email-delivery-fix, Property 5

**Validates: Requirements 4.2**

For any agent output string that contains the substring "error"
(case-insensitive), ResearchManager.send_email() SHALL return a string
containing "Warning".
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
# Strategies
# ---------------------------------------------------------------------------

# Generate strings that contain "error" in some case variant
_error_variants = st.sampled_from(["error", "Error", "ERROR", "eRrOr", "ErRoR"])

# Surround the error token with arbitrary text on either side
_surrounding_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    max_size=50,
)

error_containing_string = st.builds(
    lambda prefix, variant, suffix: prefix + variant + suffix,
    prefix=_surrounding_text,
    variant=_error_variants,
    suffix=_surrounding_text,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_report() -> FinalReportData:
    """Minimal FinalReportData for send_email() calls."""
    return FinalReportData(
        short_summary="summary",
        markdown_report="# Report",
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
    mock_result.context_wrapper.usage = MagicMock(input_tokens=0, output_tokens=0)
    return mock_result


# ---------------------------------------------------------------------------
# Property 5: Agent output containing "error" produces a warning return value
# ---------------------------------------------------------------------------


@given(output_text=error_containing_string)
@settings(max_examples=200)
def test_property_error_output_produces_warning(output_text: str) -> None:
    """**Validates: Requirements 4.2**

    For any agent output string that contains "error" (case-insensitive),
    send_email() SHALL return a string containing "Warning".
    """
    # Confirm the generated string actually contains "error" case-insensitively
    assert (
        "error" in output_text.lower()
    ), f"Strategy produced a string without 'error': {output_text!r}"

    pool = MagicMock(spec=asyncpg.Pool)
    manager = ResearchManager(pool)
    report = _make_report()
    mock_result = _make_mock_runner_result(output_text)

    with (
        patch(
            "src.core.research_manager.EMAIL_ENABLED",
            True,
            create=True,
        ),
        patch(
            "src.core.research_manager.SENDER",
            "sender@example.com",
            create=True,
        ),
        patch(
            "src.core.research_manager.RECIPIENT",
            "recipient@example.com",
            create=True,
        ),
        patch(
            "src.core.research_manager.Runner.run",
            new=AsyncMock(return_value=mock_result),
        ),
    ):
        # Patch the local import inside send_email() via the settings module
        with (
            patch(
                "src.config.settings.EMAIL_ENABLED",
                True,
            ),
            patch(
                "src.config.settings.SENDER",
                "sender@example.com",
            ),
            patch(
                "src.config.settings.RECIPIENT",
                "recipient@example.com",
            ),
        ):
            result = asyncio.run(manager.send_email(report))

    assert isinstance(result, str), f"Expected str, got {type(result)!r}"
    assert "Warning" in result, (
        f"Expected 'Warning' in return value for output {output_text!r}, "
        f"got {result!r}"
    )
