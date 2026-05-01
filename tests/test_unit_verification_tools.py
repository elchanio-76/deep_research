"""
Unit tests for src/agents/verification_tools.parse_verification_result.

Covers Requirements 16.1, 16.2, 16.3.
"""

import pytest

from src.agents.verification_tools import parse_verification_result
from src.models.domain import SingleClaimCitation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claim_dict(
    claim: str = "The sky is blue.",
    confidence_score: int = 80,
    is_verified: bool = True,
    verification_strategy: str = "quick",
) -> dict:
    """Return a minimal valid SingleClaimCitation payload as a plain dict."""
    return {
        "claim": claim,
        "confidence_score": confidence_score,
        "confidence_rationale": "Test rationale.",
        "is_verified": is_verified,
        "verification_strategy": verification_strategy,
        "search_queries_used": [],
        "supporting_citations": [],
        "contradicting_citations": [],
    }


# ---------------------------------------------------------------------------
# Requirement 16.1 — dict with "verified_claims" returns a list of
#                    SingleClaimCitation objects
# ---------------------------------------------------------------------------


class TestParseVerificationResultGroupResult:
    """Tests for group verification results (Requirement 16.1)."""

    def test_group_result_returns_list(self):
        """A dict containing 'verified_claims' must return a list."""
        payload = {"verified_claims": [_make_claim_dict()]}
        result = parse_verification_result(payload)
        assert isinstance(result, list)

    def test_group_result_items_are_single_claim_citations(self):
        """Every item in the returned list must be a SingleClaimCitation."""
        payload = {
            "verified_claims": [
                _make_claim_dict("Claim A"),
                _make_claim_dict("Claim B"),
            ]
        }
        result = parse_verification_result(payload)
        for item in result:
            assert isinstance(item, SingleClaimCitation)

    def test_group_result_preserves_claim_text(self):
        """Claim text must be preserved after parsing."""
        payload = {"verified_claims": [_make_claim_dict(claim="Water is wet.")]}
        result = parse_verification_result(payload)
        assert result[0].claim == "Water is wet."

    def test_group_result_preserves_confidence_score(self):
        """Confidence score must be preserved after parsing."""
        payload = {"verified_claims": [_make_claim_dict(confidence_score=42)]}
        result = parse_verification_result(payload)
        assert result[0].confidence_score == 42


# ---------------------------------------------------------------------------
# Requirement 16.2 — dict without "verified_claims" returns a single
#                    SingleClaimCitation object
# ---------------------------------------------------------------------------


class TestParseVerificationResultSingleResult:
    """Tests for single verification results (Requirement 16.2)."""

    def test_single_result_returns_single_claim_citation(self):
        """A dict without 'verified_claims' must return a SingleClaimCitation."""
        result = parse_verification_result(_make_claim_dict())
        assert isinstance(result, SingleClaimCitation)

    def test_single_result_is_not_a_list(self):
        """A single result must NOT be wrapped in a list."""
        result = parse_verification_result(_make_claim_dict())
        assert not isinstance(result, list)

    def test_single_result_preserves_claim_text(self):
        """Claim text must be preserved after parsing."""
        result = parse_verification_result(_make_claim_dict(claim="Grass is green."))
        assert result.claim == "Grass is green."

    def test_single_result_preserves_is_verified(self):
        """is_verified flag must be preserved after parsing."""
        result = parse_verification_result(_make_claim_dict(is_verified=False))
        assert result.is_verified is False

    def test_single_result_with_skipped_strategy(self):
        """Skipped verification strategy must be accepted and preserved."""
        payload = _make_claim_dict(verification_strategy="skipped")
        result = parse_verification_result(payload)
        assert result.verification_strategy == "skipped"

    def test_single_result_with_thorough_strategy(self):
        """Thorough verification strategy must be accepted and preserved."""
        payload = _make_claim_dict(verification_strategy="thorough")
        result = parse_verification_result(payload)
        assert result.verification_strategy == "thorough"


# ---------------------------------------------------------------------------
# Requirement 16.3 — group result with n claims returns list of length n
# ---------------------------------------------------------------------------


class TestParseVerificationResultGroupLength:
    """Tests that group result length matches the number of claims (Requirement 16.3)."""

    def test_group_result_empty_list(self):
        """An empty 'verified_claims' list must return an empty list."""
        payload = {"verified_claims": []}
        result = parse_verification_result(payload)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_group_result_single_claim_length(self):
        """A group with 1 claim must return a list of length 1."""
        payload = {"verified_claims": [_make_claim_dict()]}
        result = parse_verification_result(payload)
        assert len(result) == 1

    def test_group_result_two_claims_length(self):
        """A group with 2 claims must return a list of length 2."""
        payload = {
            "verified_claims": [
                _make_claim_dict("Claim 1"),
                _make_claim_dict("Claim 2"),
            ]
        }
        result = parse_verification_result(payload)
        assert len(result) == 2

    def test_group_result_five_claims_length(self):
        """A group with 5 claims must return a list of length 5."""
        payload = {
            "verified_claims": [_make_claim_dict(f"Claim {i}") for i in range(5)]
        }
        result = parse_verification_result(payload)
        assert len(result) == 5

    def test_group_result_ten_claims_length(self):
        """A group with 10 claims must return a list of length 10."""
        payload = {
            "verified_claims": [_make_claim_dict(f"Claim {i}") for i in range(10)]
        }
        result = parse_verification_result(payload)
        assert len(result) == 10

    def test_group_result_preserves_order(self):
        """Claims must appear in the same order as in the input."""
        claims = [f"Claim {i}" for i in range(4)]
        payload = {"verified_claims": [_make_claim_dict(c) for c in claims]}
        result = parse_verification_result(payload)
        for i, citation in enumerate(result):
            assert citation.claim == claims[i]
