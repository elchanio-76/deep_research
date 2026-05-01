"""
Unit tests for src/core/research_manager.py

Covers pure / near-pure methods only — no LLM, database, or HTTP calls:
  - _normalize_json_payload   (Requirements 7.1–7.7)
  - _get_search_budget        (Requirements 8.1–8.4)
  - _compute_brave_flags      (Requirements 9.1–9.6)
  - calculate_total_cost      (Requirements 10.1–10.5)
  - _format_cost_summary_from_snapshot  (Requirements 11.1–11.4)
  - reset_session_state       (Requirements 12.1–12.7)

ResearchManager is instantiated with MagicMock(spec=asyncpg.Pool).
Pool methods raise AttributeError if accidentally called — intentional guard.

Property tests use @settings(max_examples=100) — project standard.
"""

import json
import math
from collections.abc import Mapping
from unittest.mock import MagicMock

import asyncpg
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.config.settings import (
    AGENT_MODEL_MAP,
    DEFAULT_NUM_SEARCHES,
    MODEL_COSTS,
    SEARCH_MODE_DEFAULT,
    TOOL_COSTS,
)
from src.core.research_manager import ResearchManager
from src.models.domain import SessionUsage, WebSearchItem

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def manager() -> ResearchManager:
    """ResearchManager with a MagicMock pool for pure method tests.

    The pool is spec'd to asyncpg.Pool so any accidental pool method call
    raises AttributeError immediately.
    """
    pool = MagicMock(spec=asyncpg.Pool)
    return ResearchManager(pool)


# ---------------------------------------------------------------------------
# Hypothesis strategies (local — no shared conftest needed)
# ---------------------------------------------------------------------------

json_object_dict = st.dictionaries(
    keys=st.text(min_size=1, max_size=20),
    values=st.one_of(
        st.integers(),
        st.floats(allow_nan=False, allow_infinity=False),
        st.text(),
        st.booleans(),
    ),
    max_size=10,
)

unknown_mode = st.text().filter(lambda s: s not in {"deep_dive", "deep_dive_gap_fill"})

web_search_item = st.builds(
    WebSearchItem,
    query=st.text(min_size=1, max_size=50),
    reason=st.text(min_size=1, max_size=50),
)
search_list = st.lists(web_search_item, min_size=0, max_size=20)

non_neg_tokens = st.integers(min_value=0, max_value=10_000_000)


# ===========================================================================
# 3.2  _normalize_json_payload — example tests
# ===========================================================================


def test_normalize_json_payload_none_returns_empty_dict(manager):
    """Requirement 7.1 — None returns {}."""
    assert manager._normalize_json_payload(None) == {}


def test_normalize_json_payload_dict_returned_unchanged(manager):
    """Requirement 7.2 — dict argument returned unchanged."""
    d = {"key": "value", "count": 42}
    result = manager._normalize_json_payload(d)
    assert result == d
    assert result is d  # same object, not a copy


def test_normalize_json_payload_valid_json_string_returns_dict(manager):
    """Requirement 7.3 — valid JSON object string returns parsed dict."""
    payload = json.dumps({"a": 1, "b": "hello"})
    result = manager._normalize_json_payload(payload)
    assert result == {"a": 1, "b": "hello"}


def test_normalize_json_payload_invalid_json_string_returns_empty_dict(manager):
    """Requirement 7.4 — invalid JSON string returns {}."""
    assert manager._normalize_json_payload("{not valid json}") == {}


def test_normalize_json_payload_json_list_returns_empty_dict(manager):
    """Requirement 7.5 — valid JSON string decoding to list returns {}."""
    assert manager._normalize_json_payload(json.dumps([1, 2, 3])) == {}


def test_normalize_json_payload_json_int_returns_empty_dict(manager):
    """Requirement 7.5 — valid JSON string decoding to int returns {}."""
    assert manager._normalize_json_payload(json.dumps(42)) == {}


def test_normalize_json_payload_mapping_returns_plain_dict(manager):
    """Requirement 7.6 — Mapping (non-dict) returns plain dict equivalent."""

    class MyMapping(Mapping):
        def __init__(self, data):
            self._data = data

        def __getitem__(self, key):
            return self._data[key]

        def __iter__(self):
            return iter(self._data)

        def __len__(self):
            return len(self._data)

    m = MyMapping({"x": 10, "y": 20})
    result = manager._normalize_json_payload(m)
    assert result == {"x": 10, "y": 20}
    assert type(result) is dict


# ===========================================================================
# 3.3  Property 7 — _normalize_json_payload round-trips valid JSON objects
# ===========================================================================


@given(d=json_object_dict)
@settings(max_examples=100)
def test_property_normalize_json_payload_round_trips_valid_json(d):
    """# Feature: unit-test-strategy, Property 7: _normalize_json_payload round-trips valid JSON objects

    For any dict serialisable to a JSON object string, passing that JSON string to
    _normalize_json_payload SHALL return a dict equal to json.loads(s).

    Validates: Requirement 7.7
    """
    m = ResearchManager(MagicMock(spec=asyncpg.Pool))
    s = json.dumps(d)
    result = m._normalize_json_payload(s)
    assert result == json.loads(s)


# ===========================================================================
# 3.4  _get_search_budget — example tests
# ===========================================================================


def test_get_search_budget_no_adaptive(manager):
    """Requirement 8.1 — 'no_adaptive' returns DEFAULT_NUM_SEARCHES."""
    assert manager._get_search_budget("no_adaptive") == DEFAULT_NUM_SEARCHES


def test_get_search_budget_deep_dive(manager):
    """Requirement 8.2 — 'deep_dive' returns DEFAULT_NUM_SEARCHES + 3."""
    assert manager._get_search_budget("deep_dive") == DEFAULT_NUM_SEARCHES + 3


def test_get_search_budget_deep_dive_gap_fill(manager):
    """Requirement 8.3 — 'deep_dive_gap_fill' returns DEFAULT_NUM_SEARCHES * 2."""
    assert manager._get_search_budget("deep_dive_gap_fill") == DEFAULT_NUM_SEARCHES * 2


# ===========================================================================
# 3.5  Property 8 — _get_search_budget returns DEFAULT_NUM_SEARCHES for unknown modes
# ===========================================================================


@given(mode=unknown_mode)
@settings(max_examples=100)
def test_property_get_search_budget_unknown_mode_returns_default(mode):
    """# Feature: unit-test-strategy, Property 8: _get_search_budget returns DEFAULT_NUM_SEARCHES for unknown modes

    For any string that is not 'deep_dive' or 'deep_dive_gap_fill',
    _get_search_budget SHALL return DEFAULT_NUM_SEARCHES.

    Validates: Requirement 8.4
    """
    m = ResearchManager(MagicMock(spec=asyncpg.Pool))
    assert m._get_search_budget(mode) == DEFAULT_NUM_SEARCHES


# ===========================================================================
# 3.6  _compute_brave_flags — example tests
# ===========================================================================


def _make_searches(n: int) -> list[WebSearchItem]:
    """Helper: build a list of n WebSearchItem objects."""
    return [WebSearchItem(query=f"query {i}", reason=f"reason {i}") for i in range(n)]


def test_compute_brave_flags_cost_effective_false_all_false(manager):
    """Requirement 9.1 — cost_effective_search=False returns all False."""
    manager.cost_effective_search = False
    searches = _make_searches(5)
    flags = manager._compute_brave_flags(searches, phase="initial")
    assert flags == [False] * 5


def test_compute_brave_flags_initial_no_adaptive_all_true(manager):
    """Requirement 9.2 — cost_effective=True, phase='initial', mode='no_adaptive' → all True."""
    manager.cost_effective_search = True
    manager.search_mode = "no_adaptive"
    searches = _make_searches(4)
    flags = manager._compute_brave_flags(searches, phase="initial")
    assert flags == [True] * 4


def test_compute_brave_flags_deep_dive_ceil_half_true(manager):
    """Requirement 9.3 — cost_effective=True, phase='deep_dive' → ceil(n/2) True then False."""
    manager.cost_effective_search = True
    for n in [1, 2, 3, 4, 5, 6, 7]:
        searches = _make_searches(n)
        flags = manager._compute_brave_flags(searches, phase="deep_dive")
        expected_true = math.ceil(n / 2)
        assert flags == [True] * expected_true + [False] * (
            n - expected_true
        ), f"n={n}: expected {expected_true} True flags, got {flags}"


def test_compute_brave_flags_gap_fill_ceil_half_true(manager):
    """Requirement 9.4 — cost_effective=True, phase='gap_fill' → ceil(n/2) True then False."""
    manager.cost_effective_search = True
    for n in [1, 2, 3, 4, 5, 6]:
        searches = _make_searches(n)
        flags = manager._compute_brave_flags(searches, phase="gap_fill")
        expected_true = math.ceil(n / 2)
        assert flags == [True] * expected_true + [False] * (
            n - expected_true
        ), f"n={n}: expected {expected_true} True flags, got {flags}"


def test_compute_brave_flags_initial_non_no_adaptive_all_true(manager):
    """Requirement 9.5 — cost_effective=True, phase='initial', mode≠'no_adaptive' → all True."""
    manager.cost_effective_search = True
    manager.search_mode = "deep_dive"
    searches = _make_searches(6)
    flags = manager._compute_brave_flags(searches, phase="initial")
    assert flags == [True] * 6


# ===========================================================================
# 3.7  Property 9 — _compute_brave_flags length equals input length
# ===========================================================================


@given(
    searches=search_list,
    phase=st.sampled_from(["initial", "deep_dive", "gap_fill"]),
    cost_effective_search=st.booleans(),
    search_mode=st.sampled_from(["no_adaptive", "deep_dive", "deep_dive_gap_fill"]),
)
@settings(max_examples=100)
def test_property_compute_brave_flags_length_equals_input_length(
    searches, phase, cost_effective_search, search_mode
):
    """# Feature: unit-test-strategy, Property 9: _compute_brave_flags length equals input length

    For any list of WebSearchItem objects, any phase string, and any combination of
    cost_effective_search and search_mode settings, the list returned by
    _compute_brave_flags SHALL have the same length as the input list.

    Validates: Requirement 9.6
    """
    m = ResearchManager(MagicMock(spec=asyncpg.Pool))
    m.cost_effective_search = cost_effective_search
    m.search_mode = search_mode
    flags = m._compute_brave_flags(searches, phase)
    assert len(flags) == len(searches)


# ===========================================================================
# 3.8  calculate_total_cost — example tests
# ===========================================================================


def test_calculate_total_cost_empty_session_returns_zero(manager):
    """Requirement 10.1 — empty session_usage returns 0.0."""
    assert manager.calculate_total_cost() == 0.0


def test_calculate_total_cost_known_agent_token_counts(manager):
    """Requirement 10.2 — known agent with known token counts returns expected cost."""
    # Pick a known agent and its model
    agent_name = "planner_agent"
    model_name = AGENT_MODEL_MAP[agent_name]
    rates = MODEL_COSTS[model_name]

    input_tokens = 1_000_000
    output_tokens = 500_000

    manager.session_usage.add_agent_usage(agent_name, input_tokens, output_tokens)

    expected = (input_tokens / 1_000_000) * rates["input"] + (
        output_tokens / 1_000_000
    ) * rates["output"]
    assert manager.calculate_total_cost() == pytest.approx(expected)


def test_calculate_total_cost_tool_calls_added(manager):
    """Requirement 10.3 — tool calls add TOOL_COSTS[tool_name] * count to total."""
    tool_name = "web_search"
    count = 3
    manager.session_usage.add_tool_call("search_agent", tool_name, count)

    expected = TOOL_COSTS[tool_name] * count
    assert manager.calculate_total_cost() == pytest.approx(expected)


def test_calculate_total_cost_unknown_agent_skipped(manager):
    """Requirement 10.4 — unknown agent name is skipped without raising."""
    manager.session_usage.add_agent_usage("nonexistent_agent_xyz", 100_000, 50_000)
    # Should not raise; unknown agent is simply skipped
    cost = manager.calculate_total_cost()
    assert cost == 0.0


# ===========================================================================
# 3.9  Property 10 — calculate_total_cost is non-negative for all valid inputs
# ===========================================================================


@given(
    input_tokens=non_neg_tokens,
    output_tokens=non_neg_tokens,
    tool_call_count=st.integers(min_value=0, max_value=1000),
)
@settings(max_examples=100)
def test_property_calculate_total_cost_non_negative(
    input_tokens, output_tokens, tool_call_count
):
    """# Feature: unit-test-strategy, Property 10: calculate_total_cost is non-negative for all valid inputs

    For all non-negative token counts and tool-call counts for known agents,
    calculate_total_cost SHALL return a value >= 0.0.

    Validates: Requirement 10.5
    """
    m = ResearchManager(MagicMock(spec=asyncpg.Pool))
    # Use a known agent so the cost is actually computed (not skipped)
    agent_name = "writer_agent"
    m.session_usage.add_agent_usage(agent_name, input_tokens, output_tokens)
    m.session_usage.add_tool_call("search_agent", "web_search", tool_call_count)

    assert m.calculate_total_cost() >= 0.0


# ===========================================================================
# 3.10  _format_cost_summary_from_snapshot — example tests
# ===========================================================================


def test_format_cost_summary_none_returns_no_data_message(manager):
    """Requirement 11.1 — None returns string containing 'No cost data available'."""
    result = manager._format_cost_summary_from_snapshot(None)
    assert "No cost data available" in result


def test_format_cost_summary_empty_dict_returns_no_data_message(manager):
    """Requirement 11.2 — empty dict {} returns string containing 'No cost data available'."""
    result = manager._format_cost_summary_from_snapshot({})
    assert "No cost data available" in result


def test_format_cost_summary_valid_snapshot_includes_all_values(manager):
    """Requirement 11.3 — valid snapshot dict includes all four values in the output."""
    snapshot = {
        "total_input_tokens": 12345,
        "total_output_tokens": 67890,
        "total_tool_calls": 42,
        "total_cost": 1.2345,
    }
    result = manager._format_cost_summary_from_snapshot(snapshot)
    assert "12345" in result
    assert "67890" in result
    assert "42" in result
    assert "1.2345" in result


def test_format_cost_summary_total_cost_formatted_to_4_decimal_places(manager):
    """Requirement 11.4 — total_cost is formatted to 4 decimal places."""
    snapshot = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tool_calls": 0,
        "total_cost": 0.123456789,
    }
    result = manager._format_cost_summary_from_snapshot(snapshot)
    # The formatted value should appear as exactly 4 decimal places
    assert "0.1235" in result  # rounded to 4 dp


# ===========================================================================
# 3.11  reset_session_state — example tests
# ===========================================================================


def test_reset_session_state_clears_all_fields(manager):
    """Requirements 12.1–12.7 — reset_session_state clears every tracked field."""
    import uuid

    # Populate all fields with non-default values
    manager.report = object()  # type: ignore[assignment]
    manager.search_results = ["result 1", "result 2"]
    manager.last_query = "some query"
    manager.session_usage.add_agent_usage("planner_agent", 100, 200)
    manager.current_session_id = uuid.uuid4()
    manager.cost = 9.99
    manager.input_tokens = 500
    manager.output_tokens = 300
    manager.search_mode = "deep_dive"

    manager.reset_session_state()

    # Requirement 12.1
    assert manager.report is None
    # Requirement 12.2
    assert manager.search_results == []
    # Requirement 12.3
    assert manager.last_query is None
    # Requirement 12.4 — fresh SessionUsage with no agents and zero totals
    assert isinstance(manager.session_usage, SessionUsage)
    assert manager.session_usage.agents == {}
    assert manager.session_usage.total_input_tokens == 0
    assert manager.session_usage.total_output_tokens == 0
    # Requirement 12.5
    assert manager.current_session_id is None
    # Requirement 12.6
    assert manager.cost == 0.0
    assert manager.input_tokens == 0
    assert manager.output_tokens == 0
    # Requirement 12.7
    assert manager.search_mode == SEARCH_MODE_DEFAULT
