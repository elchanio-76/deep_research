from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from config import FACT_CHECK_CONFIDENCE_THRESHOLD


class WebSearchItem(BaseModel):
    reason: str = Field(
        description="Your reasoning for why this search is important to the query."
    )
    query: str = Field(description="The search term to use for the web search.")


class WebSearchPlan(BaseModel):
    searches: list[WebSearchItem] = Field(
        description="A list of web searches to perform to best answer the query."
    )


class WriterOutput(BaseModel):
    short_summary: str = Field(
        description="A short 2-3 sentence summary of the findings."
    )
    markdown_report: str = Field(description="The final report in markdown")
    follow_up_questions: list[str] = Field(
        description="Suggested topics to research further"
    )


class SingleClaimCitation(BaseModel):
    """Unified verification result for a single claim"""

    claim: str = Field(description="The claim being verified")
    search_queries_used: list[str] = Field(
        default=[], description="Web searches performed for this claim"
    )
    supporting_citations: list[str] = Field(
        default=[], description="APA format citations supporting the claim"
    )
    contradicting_citations: list[str] = Field(
        default=[], description="APA format citations contradicting the claim"
    )
    confidence_score: int = Field(description="Confidence score (0-100)", ge=0, le=100)
    confidence_rationale: str = Field(
        description="Detailed reasoning for the confidence score"
    )
    is_verified: bool = Field(description="Whether the claim is verified as accurate")
    verification_strategy: Literal[
        "skipped", "quick", "thorough", "red_teamed", "grouped"
    ] = Field(description="Strategy used for verification")
    red_team_critiques: Optional[list[str]] = Field(
        default=None, description="Logical critiques from red team (if red_teamed)"
    )
    grouped_with: Optional[list[str]] = Field(
        default=None, description="Other claims verified in same group (if grouped)"
    )


class QualityReport(BaseModel):
    scores: dict[str, int] = Field(
        description=(
            "Scores from 1-5 for source_diversity, credibility_tiers, "
            "recency, author_expertise"
        )
    )
    meta_scores: dict[str, int] = Field(
        description=(
            "Derived scores from 1-5 for geographic_balance, political_balance, "
            "stance_distribution"
        )
    )
    risk_flags: list[str] = Field(
        description="Short, actionable bias or quality concerns"
    )
    summary: str = Field(
        description="Narrative summary of the quality and bias assessment"
    )
    appendix_sources: list[str] = Field(
        description="Evaluated sources with brief notes"
    )
    appendix_followups: list[str] = Field(
        description="Suggested follow-up research questions or searches"
    )


class EditedReport(BaseModel):
    """Result of editing a report based on fact-checking"""

    edited_markdown: str = Field(description="The edited report in markdown format")
    edit_summary: str = Field(
        description="Summary of changes made (claims removed, qualified, citations added)"
    )
    claims_removed_count: int = Field(
        description="Number of claims removed or significantly changed"
    )
    citations_added_count: int = Field(description="Number of inline citations added")


ImportanceLevel = Literal["critical", "high", "medium", "low"]
ControversyLevel = Literal[
    "uncontroversial", "somewhat_controversial", "highly_controversial"
]
VerifiabilityLevel = Literal[
    "easily_verifiable", "moderately_verifiable", "hard_to_verify"
]
ClaimType = Literal[
    "statistical", "historical", "scientific", "predictive", "definitional", "opinion"
]


class ExtractedClaim(BaseModel):
    """A factual claim extracted from a research report with metadata for verification planning"""

    model_config = ConfigDict(
        use_enum_values=True,
        validate_assignment=True,
    )

    claim_text: str = Field(
        min_length=10,
        max_length=500,
        description="The factual claim extracted from the report",
    )

    context: str = Field(
        max_length=1000,
        description="Surrounding context from the report",
    )

    importance: ImportanceLevel = Field(
        description="How central this claim is to the report's thesis"
    )

    controversy_level: ControversyLevel = Field(
        description="How likely this claim is to be disputed among experts"
    )

    verifiability: VerifiabilityLevel = Field(
        description="How easy this claim is to fact-check with external sources"
    )

    claim_type: ClaimType = Field(description="The category of claim being made")

    semantic_topic: str = Field(
        min_length=3,
        max_length=50,
        description="Main topic/domain (e.g., 'climate science', 'economics')",
    )

    @field_validator("importance")
    @classmethod
    def validate_importance_controversy(cls, v: str, info) -> str:
        """Ensure highly controversial claims are not marked as low importance"""
        if info.data.get("controversy_level") == "highly_controversial" and v == "low":
            return "medium"
        return v


class ExtractedClaims(BaseModel):
    """Collection of claims extracted from a report"""

    claims: list[ExtractedClaim] = Field(
        min_length=1,
        description="List of all extracted claims with verification metadata",
    )


class FactCheckingResult(BaseModel):
    verified_claims: list[SingleClaimCitation] = Field(
        description="List of verified claims"
    )
    total_cost_estimate: float = Field(description="Estimated cost in USD")
    skipped_count: int = Field(description="The number of skipped claim verifications")
    quick_count: int = Field(description="The number of quick claim verifications")
    group_count: int = Field(description="The number of group claim verifications")
    thorough_count: int = Field(
        description="The number of claims for thorough verification"
    )
    red_team_count: int = Field(
        description="The number of claims for red_team verification"
    )


class VerifiedClaims(BaseModel):
    """Collection of verified claims from fact-checking"""

    claims: list[SingleClaimCitation] = Field(
        description="List of all verified claims with confidence scores"
    )


class FinalReportData(BaseModel):
    """Complete report after fact-checking and editing pipeline"""

    short_summary: str
    markdown_report: str
    follow_up_questions: list[str]
    verified_claims: VerifiedClaims
    total_claims_checked: int = Field(default=0)
    dubious_claims_count: int = Field(default=0)
    was_edited: bool = Field(
        default=False,
        description="Whether report was edited after fact-checking",
    )

    @classmethod
    def from_writer_and_verification(
        cls,
        writer_output: WriterOutput,
        verified_claims: VerifiedClaims,
        was_edited: bool = False,
    ):
        return cls(
            short_summary=writer_output.short_summary,
            markdown_report=writer_output.markdown_report,
            follow_up_questions=writer_output.follow_up_questions,
            verified_claims=verified_claims,
            total_claims_checked=len(verified_claims.claims),
            dubious_claims_count=sum(
                1
                for claim in verified_claims.claims
                if claim.confidence_score < FACT_CHECK_CONFIDENCE_THRESHOLD
            ),
            was_edited=was_edited,
        )
