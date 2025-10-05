from agents import Agent, WebSearchTool
from pydantic import BaseModel, Field

INSTRUCTIONS = """You are a SKEPTICAL fact-checking assistant. Your default stance is caution.

For each factual claim in the report, follow this rigorous process:

1. CLAIM EXTRACTION: Extract the specific factual claim

2. ADVERSARIAL SEARCH: Actively search for BOTH:
   - Sources that support the claim
   - Sources that contradict or cast doubt on the claim
   
3. SOURCE QUALITY ASSESSMENT:
   - Check publication date (recent sources > 2 years old are preferred)
   - Identify source type (peer-reviewed > official gov > news > blog)
   - Check for potential conflicts of interest
   - Verify source credibility and reputation

4. CONTROVERSY CHECK:
   - Is this claim disputed among experts?
   - Are there competing interpretations?
   - Does the claim involve ongoing debates?

5. CONFIDENCE SCORING (BE CONSERVATIVE):
   - 90-100: Multiple recent peer-reviewed sources + no credible contradictions + expert consensus
   - 70-89: Several authoritative sources + minimal contradictions + general agreement
   - 50-69: Mixed evidence OR single authoritative source OR some expert disagreement
   - 30-49: Limited evidence OR significant contradictions OR highly disputed
   - 0-29: No reliable sources OR mostly contradicted OR speculative

6. DEFAULT TO SKEPTICISM:
   - If uncertain between two scores, choose the LOWER one
   - Controversial topics should rarely exceed 70
   - Claims about predictions/future events should rarely exceed 60
   - If you find contradictory evidence, confidence MUST be ≤60

Generate APA citations for ALL sources (supporting AND contradicting).

EXAMPLES OF PROPER CONFIDENCE SCORES:

Example 1 - HIGH CONFIDENCE (95):
Claim: "Water boils at 100°C at sea level atmospheric pressure"
- 5 peer-reviewed physics sources confirm
- No contradictions found
- Scientific consensus for 100+ years
- Not controversial

Example 2 - MODERATE CONFIDENCE (60):
Claim: "Coffee consumption reduces risk of type 2 diabetes by 20%"
- 3 medical studies support, 1 study shows no effect
- Effect size varies across studies (15-25%)
- Observational studies, not randomized trials
- Causation unclear (correlation vs causation)

Example 3 - LOW CONFIDENCE (40):
Claim: "Remote work increases productivity by 15%"
- 2 company blogs support, 1 academic study contradicts
- Highly dependent on industry and individual
- Data is mostly pre-2020, context changed
- No consensus among experts

Example 4 - VERY LOW CONFIDENCE (20):
Claim: "AI will achieve human-level intelligence by 2030"
- Prediction, not current fact
- Wide range of expert opinions (2025-2100+)
- No empirical basis for specific date
- Highly speculative"""

class CitationData(BaseModel):
    claim: str = Field(description = "The factual claim extracted from the report")
    citations: list[str] = Field(description = "APA format citations")
    is_verified: bool = Field(description = "Whether claim is verified")
    confidence_score: int = Field(description = "Confidence score of verdict(0-100)", 
                                  ge=0, 
                                  le=100
                                  )
    contradictions: list[str] = Field(default=[], description="Sources that contradict this claim")
    source_count: int = Field(description="Number of supporting sources found")
    contradiction_count: int = Field(description="Number of contradicting sources found")
    source_quality: str = Field(description="peer-reviewed|official|mainstream|questionable")
    is_controversial: bool = Field(description="Is this claim disputed among experts?")
    recency_score: str = Field(description="recent (<2yr)|moderate (2-5yr)|dated (>5yr)")
    
    confidence_score: int = Field(..., ge=0, le=100)
    confidence_rationale: str = Field(description="Explain why this confidence score was assigned")
    
    def to_llm_string(self) -> str:
        """Generate a structured string representation for LLM consumption."""
        lines = [
            f"CLAIM: {self.claim}",
            f"VERIFICATION STATUS: {'VERIFIED' if self.is_verified else 'UNVERIFIED'}",
            f"CONFIDENCE SCORE: {self.confidence_score}/100",
            "",
            "SUPPORTING CITATIONS:"
        ]
        
        if self.citations:
            for i, citation in enumerate(self.citations, 1):
                lines.append(f"  [{i}] {citation}")
        else:
            lines.append("  None")
        
        if self.contradictions:
            lines.append("")
            lines.append("CONTRADICTORY SOURCES:")
            for i, contradiction in enumerate(self.contradictions, 1):
                lines.append(f"  [{i}] {contradiction}")
        
        return "\n".join(lines)

class CitationsList(BaseModel):
    citations: list[CitationData] = Field(description = "List of Citation Data for each claim")

citation_agent = Agent(
    name="Citation agent",
    instructions=INSTRUCTIONS,
    tools=[WebSearchTool(search_context_size="medium")],
    output_type=CitationsList,
    model="gpt-4o-mini"
)

citation_agent_tool = citation_agent.as_tool(tool_name="fact_checker",tool_description="Fact-check the report and provide citations")