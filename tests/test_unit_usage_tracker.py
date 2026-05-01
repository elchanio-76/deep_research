"""Unit tests for src/core/usage_tracker.py.

Covers Requirements 13.1–13.6:
  - set_session_usage / get_session_usage round-trip
  - record_agent_usage delegation and no-op when unbound
  - record_tool_call delegation and no-op when unbound
"""

from unittest.mock import MagicMock, call

import pytest
from agents import Usage

from src.core.usage_tracker import (
    get_session_usage,
    record_agent_usage,
    record_tool_call,
    set_session_usage,
)
from src.models.domain import SessionUsage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_context_var():
    """Ensure the ContextVar is cleared before and after every test.

    Prevents cross-test contamination when tests call set_session_usage.
    """
    set_session_usage(None)
    yield
    set_session_usage(None)


# ---------------------------------------------------------------------------
# set_session_usage / get_session_usage — Requirements 13.1, 13.2
# ---------------------------------------------------------------------------


def test_set_and_get_session_usage_round_trip():
    """set_session_usage followed by get_session_usage returns the same object.

    Requirement 13.1
    """
    su = SessionUsage()
    set_session_usage(su)
    assert get_session_usage() is su


def test_set_session_usage_none_returns_none():
    """set_session_usage(None) makes get_session_usage() return None.

    Requirement 13.2
    """
    su = SessionUsage()
    set_session_usage(su)
    # Confirm it was set first
    assert get_session_usage() is su

    set_session_usage(None)
    assert get_session_usage() is None


def test_get_session_usage_default_is_none():
    """get_session_usage() returns None when nothing has been set.

    Requirement 13.2 (initial state)
    """
    # autouse fixture already called set_session_usage(None)
    assert get_session_usage() is None


# ---------------------------------------------------------------------------
# record_agent_usage — Requirements 13.3, 13.4
# ---------------------------------------------------------------------------


def test_record_agent_usage_delegates_to_add_agent_usage():
    """record_agent_usage with a bound session calls session_usage.add_agent_usage.

    Requirement 13.3
    """
    mock_session = MagicMock(spec=SessionUsage)
    set_session_usage(mock_session)

    usage = Usage(input_tokens=10, output_tokens=5)
    record_agent_usage("writer_agent", usage)

    mock_session.add_agent_usage.assert_called_once_with("writer_agent", 10, 5)


def test_record_agent_usage_passes_correct_token_values():
    """record_agent_usage forwards input_tokens and output_tokens from Usage object.

    Requirement 13.3
    """
    mock_session = MagicMock(spec=SessionUsage)
    set_session_usage(mock_session)

    usage = Usage(input_tokens=1234, output_tokens=567)
    record_agent_usage("planner_agent", usage)

    mock_session.add_agent_usage.assert_called_once_with("planner_agent", 1234, 567)


def test_record_agent_usage_no_bound_session_does_not_raise():
    """record_agent_usage with no bound session returns without raising.

    Requirement 13.4
    """
    # autouse fixture ensures no session is bound
    usage = Usage(input_tokens=10, output_tokens=5)
    # Must not raise
    record_agent_usage("writer_agent", usage)


def test_record_agent_usage_no_bound_session_is_noop():
    """record_agent_usage with no bound session has no observable effect.

    Requirement 13.4
    """
    assert get_session_usage() is None
    usage = Usage(input_tokens=99, output_tokens=42)
    record_agent_usage("any_agent", usage)
    # Session is still None — nothing was created
    assert get_session_usage() is None


# ---------------------------------------------------------------------------
# record_tool_call — Requirements 13.5, 13.6
# ---------------------------------------------------------------------------


def test_record_tool_call_delegates_to_add_tool_call():
    """record_tool_call with a bound session calls session_usage.add_tool_call.

    Requirement 13.5
    """
    mock_session = MagicMock(spec=SessionUsage)
    set_session_usage(mock_session)

    record_tool_call("qa_agent", "brave_search")

    mock_session.add_tool_call.assert_called_once_with("qa_agent", "brave_search", 1)


def test_record_tool_call_passes_custom_count():
    """record_tool_call forwards a custom count argument to add_tool_call.

    Requirement 13.5
    """
    mock_session = MagicMock(spec=SessionUsage)
    set_session_usage(mock_session)

    record_tool_call("qa_agent", "web_search", count=3)

    mock_session.add_tool_call.assert_called_once_with("qa_agent", "web_search", 3)


def test_record_tool_call_no_bound_session_does_not_raise():
    """record_tool_call with no bound session returns without raising.

    Requirement 13.6
    """
    # autouse fixture ensures no session is bound
    record_tool_call("qa_agent", "brave_search")


def test_record_tool_call_no_bound_session_is_noop():
    """record_tool_call with no bound session has no observable effect.

    Requirement 13.6
    """
    assert get_session_usage() is None
    record_tool_call("any_agent", "any_tool")
    assert get_session_usage() is None


# ---------------------------------------------------------------------------
# Integration: real SessionUsage (no mocks)
# ---------------------------------------------------------------------------


def test_record_agent_usage_updates_real_session():
    """record_agent_usage correctly updates a real SessionUsage instance."""
    su = SessionUsage()
    set_session_usage(su)

    usage = Usage(input_tokens=100, output_tokens=50)
    record_agent_usage("writer_agent", usage)

    assert su.agents["writer_agent"].input_tokens == 100
    assert su.agents["writer_agent"].output_tokens == 50
    assert su.total_input_tokens == 100
    assert su.total_output_tokens == 50


def test_record_tool_call_updates_real_session():
    """record_tool_call correctly updates a real SessionUsage instance."""
    su = SessionUsage()
    set_session_usage(su)

    record_tool_call("qa_agent", "brave_search")
    record_tool_call("qa_agent", "brave_search")

    assert su.total_tool_calls["brave_search"] == 2
    assert su.agents["qa_agent"].tool_calls["brave_search"] == 2


def test_multiple_agents_tracked_independently():
    """Multiple agents accumulate usage independently in the same session."""
    su = SessionUsage()
    set_session_usage(su)

    record_agent_usage("agent_a", Usage(input_tokens=10, output_tokens=5))
    record_agent_usage("agent_b", Usage(input_tokens=20, output_tokens=8))

    assert su.agents["agent_a"].input_tokens == 10
    assert su.agents["agent_b"].input_tokens == 20
    assert su.total_input_tokens == 30
    assert su.total_output_tokens == 13
