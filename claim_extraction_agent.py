# claim_extraction_agent.py

from typing import Literal
from agents import Agent
from pydantic import BaseModel, Field, field_validator, ConfigDict

EXTRACTION_INSTRUCTIONS = """Extract factual claims from the report with rich metadata.

For each claim, assess:
1. IMPORTANCE: How central is this to the report's thesis?
   - critical: Core argument/conclusion
   - high: Key supporting evidence
   - medium: Supporting detail
   - low: Background/context

2. CONTROVERSY LEVEL: How likely is this to be disputed?
   - uncontroversial: Widely accepted fact (e.g., historical dates, definitions)
   - somewhat-controversial: Some debate exists
   - highly-controversial: Significant disagreement among experts
   
3. VERIFIABILITY: How easy to fact-check?
   - easily-verifiable: Clear, specific, objective (dates, numbers, events)
   - moderately-verifiable: Requires expert sources
   - hard-to-verify: Subjective, predictive, or speculative

4. CLAIM TYPE:
   - statistical: Numbers, percentages, quantities
   - historical: Past events, dates
   - scientific: Research findings, causal claims
   - predictive: Future forecasts
   - definitional: What something means
   - opinion: Subjective assessment (may not need verification)"""


# Define types as module-level constants for reuse
ImportanceLevel = Literal["critical", "high", "medium", "low"]
ControversyLevel = Literal["uncontroversial", "somewhat_controversial", "highly_controversial"]
VerifiabilityLevel = Literal["easily_verifiable", "moderately_verifiable", "hard_to_verify"]
ClaimType = Literal["statistical", "historical", "scientific", "predictive", "definitional", "opinion"]

class ExtractedClaim(BaseModel):
    """A factual claim extracted from a research report with metadata for verification planning"""
    
    model_config = ConfigDict(
        use_enum_values=True,
        validate_assignment=True,
    )
    
    claim_text: str = Field(
        min_length=10,
        max_length=500,
        description="The factual claim extracted from the report"
    )
    
    context: str = Field(
        max_length=1000,
        description="Surrounding context from the report"
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
    
    claim_type: ClaimType = Field(
        description="The category of claim being made"
    )
    
    semantic_topic: str = Field(
        min_length=3,
        max_length=50,
        description="Main topic/domain (e.g., 'climate science', 'economics')"
    )
    
    @field_validator('importance')
    @classmethod
    def validate_importance_controversy(cls, v: str, info) -> str:
        """Ensure highly controversial claims are not marked as low importance"""
        if info.data.get('controversy_level') == 'highly_controversial' and v == 'low':
            # Auto-correct instead of raising error (be lenient with LLM)
            return 'medium'
        return v

class ExtractedClaims(BaseModel):
    """Collection of claims extracted from a report"""
    
    claims: list[ExtractedClaim] = Field(
        min_length=1,
        description="List of all extracted claims with verification metadata"
    )

claim_extractor = Agent(
    name="Claim Extractor",
    instructions=EXTRACTION_INSTRUCTIONS,
    model="gpt-5-mini",
    output_type=ExtractedClaims
)
