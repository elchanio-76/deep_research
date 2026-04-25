from typing import Literal

from agents import Agent
from pydantic import BaseModel, Field

from src.config.settings import FACT_CHECK_PLANNER_MODEL
from src.models.domain import FactCheckingResult
from src.agents.verification_tools import (
    group_verify,
    quick_verify,
    red_team_verify,
    skip_verification,
    thorough_verify,
)

PLANNER_INSTRUCTIONS = """You are an intelligent fact-checking strategist.

Given a list of claims from a report, you must:

1. ANALYZE each claim's characteristics
2. GROUP semantically related claims that can be verified together
3. DECIDE verification strategy for each claim/group
4. EXECUTE verification by calling appropriate tools

VERIFICATION STRATEGIES:

1. SKIP (skip_verification):
   - Use for: Obvious facts, definitions, or very low importance
   - Examples: "Water is wet", "Napoleon died in 1821"
   - Saves: ~$0.01 per claim
   
2. QUICK (quick_verify):
   - Use for: Moderately important, uncontroversial claims
   - One search, basic verification
   - Examples: Recent historical events, basic statistics
   - Cost: ~$0.015 per claim
   
3. GROUP (group_verify):
   - Use for: Multiple related claims on same topic
   - Efficient verification of 2-4 claims together
   - Examples: Multiple stats from same study, related historical facts
   - Cost: ~$0.02 per group
   
4. THOROUGH (thorough_verify):
   - Use for: Important or somewhat controversial claims
   - Multiple searches, deep analysis
   - Examples: Key findings, significant statistics
   - Cost: ~$0.04 per claim
   
5. RED_TEAM (red_team_verify):
   - Use for: Critical AND highly controversial claims
   - **SINGLE TOOL CALL that does BOTH:**
     * Stage 1: Thorough verification automatically
     * Stage 2: Adversarial red team challenge
   - Examples: Politically charged claims, disputed science, predictions
   - Cost: ~$0.06 per claim
   - **Important**: You only need to call red_team_verify ONCE per claim.
     It handles the full two-stage process internally.

DECISION RULES:

- SKIP if: importance=low AND controversy=uncontroversial AND verifiability=easily-verifiable
- QUICK if: importance=medium AND controversy=uncontroversial
- GROUP if: 2+ claims share semantic_topic AND importance≤high
- THOROUGH if: importance=high OR importance=critical OR controversy=somewhat-controversial
- RED_TEAM if: importance=critical AND controversy=highly-controversial
  * Just call red_team_verify once - it will do thorough + adversarial internally

PROCESS:
1. Analyze all claims
2. Identify grouping opportunities (semantic similarity)
3. For each claim/group, choose strategy
4. Call the appropriate verification tool
5. Continue until all claims processed

BE STRATEGIC: Optimize for accuracy on important claims while minimizing cost on trivial claims."""


class VerificationPlan(BaseModel):
    claim_id: int = Field(
        description="The number of the claim, used for reference and grouping"
    )
    strategy: Literal["skip", "quick", "group", "thorough", "red_team"] = Field(
        description="skip|quick|group|thorough|red_team"
    )
    reasoning: str = Field(description="Why this strategy was chosen")
    group_members: list[int] = Field(
        default=[], description="Other claim IDs in group (if grouped)"
    )


fact_check_planner = Agent(
    name="Fact Check Planner",
    instructions=PLANNER_INSTRUCTIONS,
    tools=[
        skip_verification,
        quick_verify,
        group_verify,
        thorough_verify,
        red_team_verify,
    ],
    model=FACT_CHECK_PLANNER_MODEL,
    output_type=FactCheckingResult,
)
