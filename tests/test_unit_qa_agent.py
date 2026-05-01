"""
Unit tests for src/agents/qa_agent.py — is_quality_request classifier.

Covers Requirements 14.1–14.6 and Property 14.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from src.agents.qa_agent import (
    QUALITY_COMMANDS,
    QUALITY_TRIGGER_PHRASES,
    is_quality_request,
)

# ---------------------------------------------------------------------------
# Example tests — Requirements 14.1–14.5
# ---------------------------------------------------------------------------


def test_is_quality_request_slash_quality_returns_true():
    # Requirement 14.1
    assert is_quality_request("/quality") is True


def test_is_quality_request_slash_bias_returns_true():
    # Requirement 14.2
    assert is_quality_request("/bias") is True


def test_is_quality_request_run_bias_analysis_returns_true():
    # Requirement 14.3 — trigger phrase embedded in message
    assert is_quality_request("run bias analysis") is True


def test_is_quality_request_quality_check_returns_true():
    # Requirement 14.3 — trigger phrase embedded in message
    assert is_quality_request("quality check") is True


def test_is_quality_request_non_matching_returns_false():
    # Requirement 14.4
    assert is_quality_request("tell me about climate change") is False


def test_is_quality_request_empty_string_returns_false():
    # Requirement 14.4 — edge case: empty input
    assert is_quality_request("") is False


def test_is_quality_request_whitespace_around_command_returns_true():
    # Requirement 14.5 — leading/trailing whitespace is stripped
    assert is_quality_request("  /quality  ") is True


def test_is_quality_request_whitespace_around_bias_returns_true():
    # Requirement 14.5 — same for /bias
    assert is_quality_request("  /bias  ") is True


def test_is_quality_request_trigger_phrase_in_longer_message_returns_true():
    # Requirement 14.3 — phrase appears inside a longer sentence
    assert is_quality_request("Please run bias analysis on this report") is True


def test_is_quality_request_evaluate_research_quality_returns_true():
    # Requirement 14.3 — another known trigger phrase
    assert is_quality_request("evaluate research quality") is True


def test_is_quality_request_run_quality_analysis_returns_true():
    # Requirement 14.3 — another known trigger phrase
    assert is_quality_request("run quality analysis") is True


def test_is_quality_request_case_insensitive_command():
    # Requirement 14.5 — normalisation lowercases before matching
    assert is_quality_request("/QUALITY") is True


def test_is_quality_request_case_insensitive_trigger_phrase():
    # Requirement 14.3 — trigger phrase matching is case-insensitive
    assert is_quality_request("Quality Check please") is True


# ---------------------------------------------------------------------------
# Property test — Property 14 / Requirement 14.6
# ---------------------------------------------------------------------------

# Build the combined set of all known commands and trigger phrases once so
# the filter strategy can reference it without re-computing on every draw.
_ALL_KNOWN: frozenset[str] = frozenset(QUALITY_COMMANDS | QUALITY_TRIGGER_PHRASES)


def _is_non_quality_string(s: str) -> bool:
    """Return True iff s would NOT be matched by is_quality_request."""
    normalized = s.strip().lower()
    if normalized in QUALITY_COMMANDS:
        return False
    if any(phrase in normalized for phrase in QUALITY_TRIGGER_PHRASES):
        return False
    return True


# Strategy: arbitrary text that contains none of the known commands or phrases.
non_quality_str = st.text().filter(_is_non_quality_string)


@given(s=non_quality_str)
@settings(max_examples=100)
def test_property_is_quality_request_returns_false_for_non_matching_strings(s: str):
    """
    # Feature: unit-test-strategy, Property 14:
    # is_quality_request returns False for non-matching strings.

    For any string that does not contain any known quality command or trigger
    phrase, is_quality_request SHALL return False.
    """
    assert is_quality_request(s) is False
