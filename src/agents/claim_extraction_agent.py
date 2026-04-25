# claim_extraction_agent.py

from agents import Agent

from src.config.settings import CLAIM_EXTRACTOR_MODEL
from src.models.domain import ExtractedClaims

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


claim_extractor = Agent(
    name="Claim Extractor",
    instructions=EXTRACTION_INSTRUCTIONS,
    model=CLAIM_EXTRACTOR_MODEL,
    output_type=ExtractedClaims,
)
