# new_models.py - REVISED
# Uses new data types after intelligent fact-checking

from writer_agent import WriterOutput
from pydantic import BaseModel, Field
#from typing import TYPE_CHECKING
from verification_tools import SingleClaimCitation

#if TYPE_CHECKING:
#    from verification_tools import SingleClaimCitation

class VerifiedClaims(BaseModel):
    """Collection of verified claims from fact-checking"""
    claims: list["SingleClaimCitation"] = Field(
        description="List of all verified claims with confidence scores"
    )

class FinalReportData(BaseModel):
    """Complete report after fact-checking and editing pipeline"""
    short_summary: str
    markdown_report: str  # ← This is the edited version
    follow_up_questions: list[str]
    verified_claims: VerifiedClaims  # ← Changed from CitationsList
    
    # Metadata about fact-checking
    total_claims_checked: int = Field(default=0)
    dubious_claims_count: int = Field(default=0)
    was_edited: bool = Field(
        default=False,
        description="Whether report was edited after fact-checking"
    )
    
    @classmethod
    def from_writer_and_verification(
        cls,
        writer_output: WriterOutput,
        verified_claims: VerifiedClaims,
        was_edited: bool = False
    ):
        return cls(
            short_summary=writer_output.short_summary,
            markdown_report=writer_output.markdown_report,
            follow_up_questions=writer_output.follow_up_questions,
            verified_claims=verified_claims,
            total_claims_checked=len(verified_claims.claims),
            dubious_claims_count=sum(
                1 for c in verified_claims.claims 
                if c.confidence_score < 70
            ),
            was_edited=was_edited
        )
