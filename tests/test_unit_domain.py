"""
Unit tests for src/models/domain.py

Covers:
  - AgentUsage.add_tokens / add_tool_call  (Requirements 1, 2)
  - SessionUsage.add_agent_usage / add_tool_call  (Requirements 3, 4)
  - ExtractedClaim field validator  (Requirement 5)
  - FinalReportData.from_writer_and_verification  (Requirement 6)

Property tests use @settings(max_examples=100) — project standard.
"""

from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from src.config.settings import FACT_CHECK_CONFIDENCE_THRESHOLD
from src.models.domain import (
    AgentUsage,
    ExtractedClaim,
    FinalReportData,
    SessionUsage,
    SingleClaimCitation,
    VerifiedClaims,
    WriterOutput,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies (local — no shared conftest needed)
# ---------------------------------------------------------------------------

token_count = st.integers(min_value=0, max_value=10_000_000)
positive_int = st.integers(min_value=1, max_value=1000)
name_str = st.text(min_size=1, max_size=50)

importance_level = st.sampled_from(["critical", "high", "medium", "low"])
controversy_level = st.sampled_from(
    ["uncontroversial", "somewhat_controversial", "highly_controversial"]
)

claim_citation = st.builds(
    SingleClaimCitation,
    claim=st.text(min_size=1, max_size=100),
    confidence_score=st.integers(min_value=0, max_value=100),
    is_verified=st.booleans(),
    verification_strategy=st.just("quick"),
    supporting_citations=st.just([]),
    contradicting_citations=st.just([]),
    confidence_rationale=st.just("test rationale"),
    search_queries_used=st.just([]),
)


# ===========================================================================
# 1.1  AgentUsage — example tests
# ===========================================================================


def test_agent_usage_initial_state():
    """Requirement 1.1 — initial token counts are zero."""
    usage = AgentUsage()
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0


def test_agent_usage_add_tokens_single_call():
    """Requirement 1.2 — single call reflects exact values passed."""
    usage = AgentUsage()
    usage.add_tokens(100, 200)
    assert usage.input_tokens == 100
    assert usage.output_tokens == 200


def test_agent_usage_add_tokens_multi_call_accumulates():
    """Requirement 1.3 — multiple calls accumulate correctly."""
    usage = AgentUsage()
    usage.add_tokens(10, 20)
    usage.add_tokens(30, 40)
    assert usage.input_tokens == 40
    assert usage.output_tokens == 60


def test_agent_usage_add_tokens_zero_idempotent():
    """Requirement 1.5 — adding zero tokens leaves totals unchanged."""
    usage = AgentUsage()
    usage.add_tokens(50, 75)
    usage.add_tokens(0, 0)
    assert usage.input_tokens == 50
    assert usage.output_tokens == 75


def test_agent_usage_add_tool_call_creates_entry():
    """Requirement 2.1 — first call for a new tool creates entry with count 1."""
    usage = AgentUsage()
    usage.add_tool_call("web_search")
    assert usage.tool_calls["web_search"] == 1


def test_agent_usage_add_tool_call_n_times():
    """Requirement 2.2 — calling n times records count n."""
    usage = AgentUsage()
    for _ in range(5):
        usage.add_tool_call("web_search")
    assert usage.tool_calls["web_search"] == 5


def test_agent_usage_add_tool_call_with_count_k():
    """Requirement 2.3 — add_tool_call(name, count=k) adds k to existing count."""
    usage = AgentUsage()
    usage.add_tool_call("web_search", count=3)
    usage.add_tool_call("web_search", count=7)
    assert usage.tool_calls["web_search"] == 10


def test_agent_usage_add_tool_call_independent_counts():
    """Requirement 2.5 — two distinct tool names maintain independent counts."""
    usage = AgentUsage()
    usage.add_tool_call("tool_a")
    usage.add_tool_call("tool_a")
    usage.add_tool_call("tool_b")
    assert usage.tool_calls["tool_a"] == 2
    assert usage.tool_calls["tool_b"] == 1


# ===========================================================================
# 1.2  Property 1 — AgentUsage token accumulation is additive
# ===========================================================================


@given(
    a=token_count,
    b=token_count,
    c=token_count,
    d=token_count,
)
@settings(max_examples=100)
def test_property_agent_usage_token_accumulation_additive(a, b, c, d):
    """# Feature: unit-test-strategy, Property 1: AgentUsage token accumulation is additive

    For any two pairs of non-negative integers (a, b) and (c, d), calling
    add_tokens(a, b) then add_tokens(c, d) on a fresh AgentUsage SHALL produce
    input_tokens == a + c and output_tokens == b + d.

    Validates: Requirement 1.4
    """
    usage = AgentUsage()
    usage.add_tokens(a, b)
    usage.add_tokens(c, d)
    assert usage.input_tokens == a + c
    assert usage.output_tokens == b + d


# ===========================================================================
# 1.3  Property 2 — AgentUsage tool-call counting is exact
# ===========================================================================


@given(t=name_str, n=positive_int)
@settings(max_examples=100)
def test_property_agent_usage_tool_call_counting_exact(t, n):
    """# Feature: unit-test-strategy, Property 2: AgentUsage tool-call counting is exact

    For any non-empty string t and positive integer n, calling add_tool_call(t)
    exactly n times on a fresh AgentUsage SHALL produce tool_calls[t] == n.

    Validates: Requirement 2.4
    """
    usage = AgentUsage()
    for _ in range(n):
        usage.add_tool_call(t)
    assert usage.tool_calls[t] == n


# ===========================================================================
# 1.4  SessionUsage — example tests
# ===========================================================================


def test_session_usage_add_agent_usage_creates_entry():
    """Requirement 3.1 — new agent creates an AgentUsage entry."""
    session = SessionUsage()
    session.add_agent_usage("planner", 100, 200)
    assert "planner" in session.agents
    assert isinstance(session.agents["planner"], AgentUsage)


def test_session_usage_add_agent_usage_accumulates_existing():
    """Requirement 3.2 — existing agent accumulates into the same entry."""
    session = SessionUsage()
    session.add_agent_usage("planner", 100, 200)
    session.add_agent_usage("planner", 50, 75)
    assert session.agents["planner"].input_tokens == 150
    assert session.agents["planner"].output_tokens == 275


def test_session_usage_add_tool_call_increments_total():
    """Requirement 4.1 — add_tool_call increments total_tool_calls[tool_name]."""
    session = SessionUsage()
    session.add_tool_call("planner", "web_search")
    session.add_tool_call("writer", "web_search")
    assert session.total_tool_calls["web_search"] == 2


def test_session_usage_add_tool_call_increments_agent_entry():
    """Requirement 4.2 — add_tool_call also increments agents[agent].tool_calls[tool]."""
    session = SessionUsage()
    session.add_tool_call("planner", "web_search")
    assert session.agents["planner"].tool_calls["web_search"] == 1


# ===========================================================================
# 1.5  Property 3 — SessionUsage totals equal sum of per-agent values
# ===========================================================================


@given(
    triples=st.lists(
        st.tuples(name_str, token_count, token_count),
        min_size=0,
        max_size=20,
    )
)
@settings(max_examples=100)
def test_property_session_usage_totals_equal_sum_of_agents(triples):
    """# Feature: unit-test-strategy, Property 3: SessionUsage totals equal sum of per-agent values

    For any sequence of (agent_name, input_tokens, output_tokens) triples applied
    via add_agent_usage, the SessionUsage total_input_tokens SHALL equal the sum of
    all input values and total_output_tokens SHALL equal the sum of all output values.

    Validates: Requirements 3.3, 3.4, 3.5
    """
    session = SessionUsage()
    for agent_name, inp, out in triples:
        session.add_agent_usage(agent_name, inp, out)

    expected_input = sum(inp for _, inp, _ in triples)
    expected_output = sum(out for _, _, out in triples)

    assert session.total_input_tokens == expected_input
    assert session.total_output_tokens == expected_output


# ===========================================================================
# 1.6  Property 4 — SessionUsage total_tool_calls equals sum across agents
# ===========================================================================


@given(
    pairs=st.lists(
        st.tuples(name_str, name_str),
        min_size=0,
        max_size=30,
    )
)
@settings(max_examples=100)
def test_property_session_usage_total_tool_calls_equals_sum_across_agents(pairs):
    """# Feature: unit-test-strategy, Property 4: SessionUsage total_tool_calls equals sum across agents

    For any sequence of (agent_name, tool_name) pairs applied via add_tool_call,
    the SessionUsage total_tool_calls[tool_name] SHALL equal the sum of that tool's
    count across all per-agent AgentUsage entries.

    Validates: Requirement 4.3
    """
    session = SessionUsage()
    for agent_name, tool_name in pairs:
        session.add_tool_call(agent_name, tool_name)

    # For every tool that appears in total_tool_calls, verify it equals the
    # sum of per-agent counts for that tool.
    for tool_name, total_count in session.total_tool_calls.items():
        per_agent_sum = sum(
            agent.tool_calls.get(tool_name, 0) for agent in session.agents.values()
        )
        assert total_count == per_agent_sum


# ===========================================================================
# 1.7  ExtractedClaim validator — example tests
# ===========================================================================

# Minimal valid field values shared across ExtractedClaim example tests.
_CLAIM_DEFAULTS = dict(
    claim_text="This is a factual claim that is at least ten characters long.",
    context="Surrounding context for the claim.",
    verifiability="easily_verifiable",
    claim_type="statistical",
    semantic_topic="economics",
)


def test_extracted_claim_highly_controversial_low_importance_coerced():
    """Requirement 5.1 — highly_controversial + importance='low' coerces to 'medium'."""
    claim = ExtractedClaim(
        **_CLAIM_DEFAULTS,
        controversy_level="highly_controversial",
        importance="low",
    )
    assert claim.importance == "medium"


def test_extracted_claim_highly_controversial_high_importance_preserved():
    """Requirement 5.2 — highly_controversial + importance='high' preserves 'high'."""
    claim = ExtractedClaim(
        **_CLAIM_DEFAULTS,
        controversy_level="highly_controversial",
        importance="high",
    )
    assert claim.importance == "high"


def test_extracted_claim_non_controversial_preserves_importance():
    """Requirement 5.3 — non-highly_controversial controversy preserves any importance."""
    for controversy in ("uncontroversial", "somewhat_controversial"):
        for importance in ("critical", "high", "medium", "low"):
            claim = ExtractedClaim(
                **_CLAIM_DEFAULTS,
                controversy_level=controversy,
                importance=importance,
            )
            assert claim.importance == importance


# ===========================================================================
# 1.8  Property 5 — ExtractedClaim validator never raises for valid enum combos
# ===========================================================================


@given(importance=importance_level, controversy=controversy_level)
@settings(max_examples=100)
def test_property_extracted_claim_validator_never_raises(importance, controversy):
    """# Feature: unit-test-strategy, Property 5: ExtractedClaim validator never raises for valid enum combinations

    For any valid ImportanceLevel and ControversyLevel value, constructing an
    ExtractedClaim with those values SHALL succeed without raising a ValidationError.

    Validates: Requirement 5.4
    """
    try:
        ExtractedClaim(
            **_CLAIM_DEFAULTS,
            importance=importance,
            controversy_level=controversy,
        )
    except ValidationError as exc:
        raise AssertionError(
            f"ValidationError raised for importance={importance!r}, "
            f"controversy_level={controversy!r}: {exc}"
        ) from exc


# ===========================================================================
# 1.9  FinalReportData.from_writer_and_verification — example tests
# ===========================================================================


def _make_writer_output(
    summary: str = "Short summary.",
    report: str = "# Report\n\nContent.",
    follow_ups: list[str] | None = None,
) -> WriterOutput:
    return WriterOutput(
        short_summary=summary,
        markdown_report=report,
        follow_up_questions=follow_ups or ["Question 1?", "Question 2?"],
    )


def _make_claim(confidence_score: int) -> SingleClaimCitation:
    return SingleClaimCitation(
        claim="A factual claim.",
        confidence_score=confidence_score,
        is_verified=confidence_score >= FACT_CHECK_CONFIDENCE_THRESHOLD,
        verification_strategy="quick",
        supporting_citations=[],
        contradicting_citations=[],
        confidence_rationale="rationale",
        search_queries_used=[],
    )


def test_final_report_data_copies_writer_fields():
    """Requirement 6.1 — short_summary, markdown_report, follow_up_questions copied unchanged."""
    writer = _make_writer_output(
        summary="My summary.",
        report="# My Report",
        follow_ups=["Q1?", "Q2?"],
    )
    verified = VerifiedClaims(claims=[_make_claim(80)])
    report = FinalReportData.from_writer_and_verification(writer, verified)

    assert report.short_summary == "My summary."
    assert report.markdown_report == "# My Report"
    assert report.follow_up_questions == ["Q1?", "Q2?"]


def test_final_report_data_total_claims_checked():
    """Requirement 6.2 — total_claims_checked equals number of claims."""
    claims = [_make_claim(80), _make_claim(60), _make_claim(90)]
    verified = VerifiedClaims(claims=claims)
    report = FinalReportData.from_writer_and_verification(
        _make_writer_output(), verified
    )
    assert report.total_claims_checked == 3


def test_final_report_data_dubious_claims_count():
    """Requirement 6.3 — dubious_claims_count equals count below threshold."""
    # FACT_CHECK_CONFIDENCE_THRESHOLD == 70
    claims = [
        _make_claim(80),  # not dubious
        _make_claim(69),  # dubious (< 70)
        _make_claim(70),  # not dubious (== 70, not strictly less)
        _make_claim(50),  # dubious
    ]
    verified = VerifiedClaims(claims=claims)
    report = FinalReportData.from_writer_and_verification(
        _make_writer_output(), verified
    )
    assert report.dubious_claims_count == 2


def test_final_report_data_was_edited_false_preserved():
    """Requirement 6.4 — was_edited=False is preserved."""
    verified = VerifiedClaims(claims=[_make_claim(80)])
    report = FinalReportData.from_writer_and_verification(
        _make_writer_output(), verified, was_edited=False
    )
    assert report.was_edited is False


# ===========================================================================
# 1.10  Property 6 — FinalReportData dubious_claims_count matches threshold filter
# ===========================================================================


@given(claims=st.lists(claim_citation, min_size=0, max_size=20))
@settings(max_examples=100)
def test_property_final_report_data_dubious_claims_count_matches_threshold(claims):
    """# Feature: unit-test-strategy, Property 6: FinalReportData dubious_claims_count matches threshold filter

    For any list of SingleClaimCitation objects with arbitrary confidence_score
    values (0–100), FinalReportData.from_writer_and_verification SHALL produce a
    dubious_claims_count equal to
    len([c for c in claims if c.confidence_score < FACT_CHECK_CONFIDENCE_THRESHOLD]).

    Validates: Requirement 6.5
    """
    verified = VerifiedClaims(claims=claims)
    report = FinalReportData.from_writer_and_verification(
        _make_writer_output(), verified
    )

    expected = len(
        [c for c in claims if c.confidence_score < FACT_CHECK_CONFIDENCE_THRESHOLD]
    )
    assert report.dubious_claims_count == expected
