# verification_tools.py - COMPLETE REFACTORED VERSION
"""
Verification tools for fact-checking claims with different strategies.
Agents are defined at module level for reusability across tools and future workflows.
"""

from typing import Literal, Optional
from agents import Agent, function_tool, WebSearchTool, ModelSettings, Runner
from pydantic import BaseModel, Field
import json

# ========================================
# UNIFIED OUTPUT MODELS
# ========================================

class SingleClaimCitation(BaseModel):
    """Unified verification result for a single claim"""
    
    claim: str = Field(description="The claim being verified")
    
    search_queries_used: list[str] = Field(
        default=[],
        description="Web searches performed for this claim"
    )
    
    supporting_citations: list[str] = Field(
        default=[],
        description="APA format citations supporting the claim"
    )
    
    contradicting_citations: list[str] = Field(
        default=[],
        description="APA format citations contradicting the claim"
    )
    
    confidence_score: int = Field(
        description="Confidence score (0-100)",
        ge=0,
        le=100
    )
    
    confidence_rationale: str = Field(
        description="Detailed reasoning for the confidence score"
    )
    
    is_verified: bool = Field(
        description="Whether the claim is verified as accurate"
    )
    
    verification_strategy: Literal["skipped", "quick", "thorough", "red_teamed", "grouped"] = Field(
        description="Strategy used for verification"
    )
    
    # Optional fields for strategy-specific metadata
    red_team_critiques: Optional[list[str]] = Field(
        default=None,
        description="Logical critiques from red team (if red_teamed)"
    )
    
    grouped_with: Optional[list[str]] = Field(
        default=None,
        description="Other claims verified in same group (if grouped)"
    )


class GroupVerificationResult(BaseModel):
    """Result of verifying multiple related claims together"""
    
    verified_claims: list[SingleClaimCitation] = Field(
        description="Verification results for each claim in the group"
    )


# ========================================
# REUSABLE VERIFICATION AGENTS
# ========================================

# Quick Verifier - Single search, fast assessment
quick_verifier_agent = Agent(
    name="Quick Verifier",
    instructions="""Quickly verify this claim with ONE web search.
    
    Provide:
    - The claim being verified
    - Search queries used
    - Supporting citations (if found)
    - Contradicting citations (if found)
    - Confidence score (0-100)
    - Clear rationale for the score
    - Verification status (true/false)
    
    Be efficient but thorough.""",
    tools=[WebSearchTool(search_context_size="low")],
    model="gpt-4o-mini",
    output_type=SingleClaimCitation
)


# Thorough Verifier - Multiple searches, deep analysis
thorough_verifier_agent = Agent(
    name="Thorough Verifier",
    instructions="""Thoroughly verify this claim:
    
    Process:
    1. Search for supporting evidence (use web search)
    2. Search for contradicting evidence (use web search again)
    3. Assess source quality and recency
    4. Determine confidence score
    
    Use web search tool 2-3 times for comprehensive verification.
    Be thorough and skeptical in your assessment.
    
    Output all required fields including:
    - All search queries used
    - Supporting and contradicting citations
    - Detailed confidence rationale""",
    tools=[WebSearchTool(search_context_size="medium")],
    model="gpt-4o-mini",
    output_type=SingleClaimCitation,
    model_settings=ModelSettings(tool_choice="required")
)


# Red Team Challenger - Adversarial verification
red_team_challenger_agent = Agent(
    name="Red Team Challenger",
    instructions="""You are a skeptical red team agent challenging an initial verification.
    
    Your mission:
    1. Search aggressively for contradicting evidence
    2. Find alternative interpretations  
    3. Identify logical flaws in the initial assessment
    4. Provide additional contradicting citations if found
    5. Lower confidence score if appropriate (never increase it)
    6. List specific critiques in red_team_critiques field
    
    Be adversarial and thorough. Your role is to prevent overconfidence.
    
    Output a COMPLETE SingleClaimCitation with:
    - Original claim (unchanged)
    - All original citations PLUS any new ones you find
    - Updated confidence score (same or lower, NEVER higher)
    - Red team critiques in the red_team_critiques field
    - Rationale incorporating both initial and red team findings""",
    tools=[WebSearchTool(search_context_size="medium")],
    model="gpt-4o-mini",
    output_type=SingleClaimCitation
)


# Group Verifier - Efficient verification of related claims
group_verifier_agent = Agent(
    name="Group Verifier",
    instructions="""Verify multiple related claims efficiently.
    
    Since these claims share a topic, you can:
    1. Make 2-3 searches for the shared topic
    2. Use findings to assess all claims
    3. Return individual verification for EACH claim
    
    For each claim, provide:
    - Full SingleClaimCitation structure
    - Appropriate confidence based on evidence
    - Note which claims were verified together (grouped_with field)
    
    Be efficient but don't compromise accuracy.""",
    tools=[WebSearchTool(search_context_size="medium")],
    model="gpt-4o-mini",
    output_type=GroupVerificationResult
)


# ========================================
# VERIFICATION TOOL FUNCTIONS
# ========================================

@function_tool
async def skip_verification(claim: str, reason: str) -> dict:
    """Skip verification for obviously true or unimportant claims
    
    Args:
        claim: The claim to skip verification for
        reason: Why verification is being skipped
    
    Returns:
        SingleClaimCitation with high default confidence
    """
    return SingleClaimCitation(
        claim=claim,
        search_queries_used=[],
        supporting_citations=[],
        contradicting_citations=[],
        confidence_score=95,
        confidence_rationale=f"Verification skipped: {reason}",
        is_verified=True,
        verification_strategy="skipped"
    ).model_dump()


@function_tool
async def quick_verify(claim: str, claim_context: str) -> dict:
    """Light verification - single web search, quick assessment
    
    Args:
        claim: The claim to verify
        claim_context: Context from the report
    
    Returns:
        SingleClaimCitation with quick verification results
    """
    
    input_text = f"""Claim: {claim}
Context: {claim_context}

Verification strategy: quick"""
    
    try:
        result = await Runner.run(quick_verifier_agent, input_text)
        output = result.final_output
        output.verification_strategy = "quick"
        return output.model_dump()
    except Exception as e:
        print(f"Quick verification failed: {e}")
        return SingleClaimCitation(
            claim=claim,
            confidence_score=0,
            is_verified=False,
            verification_strategy="quick",
            supporting_citations=[],
            contradicting_citations=[],
            confidence_rationale=f"Quick verification failed: {str(e)}",
            search_queries_used=[]
        ).model_dump()


@function_tool
async def thorough_verify(claim: str, claim_context: str, background_research: str) -> dict:
    """Deep verification - multiple searches, cross-referencing
    
    Args:
        claim: The claim to verify thoroughly
        claim_context: Context from the report
        background_research: Background research summaries
    
    Returns:
        SingleClaimCitation with thorough verification results
    """
    
    input_text = f"""Claim: {claim}
Context: {claim_context}
Background: {background_research}

Verification strategy: thorough"""
    
    try:
        result = await Runner.run(thorough_verifier_agent, input_text)
        output = result.final_output
        output.verification_strategy = "thorough"
        return output.model_dump()
    except Exception as e:
        print(f"Thorough verification failed: {e}")
        return SingleClaimCitation(
            claim=claim,
            confidence_score=0,
            is_verified=False,
            verification_strategy="thorough",
            supporting_citations=[],
            contradicting_citations=[],
            confidence_rationale=f"Thorough verification failed: {str(e)}",
            search_queries_used=[]
        ).model_dump()


@function_tool
async def red_team_verify(
    claim: str,
    claim_context: str,
    background_research: str
) -> dict:
    """Two-stage adversarial verification - thorough check THEN red team challenge
    
    This tool automatically:
    1. Performs thorough verification (multiple searches, deep analysis)
    2. Red teams the result (adversarial challenge)
    3. Returns final red-teamed verification
    
    Use for critical AND highly controversial claims where overconfidence is risky.
    
    Args:
        claim: The claim to verify with red teaming
        claim_context: Context from the report
        background_research: Background research summaries
    
    Returns:
        SingleClaimCitation with red_teamed strategy and critiques
    """
    
    # STAGE 1: Thorough verification using reusable agent
    print(f"Red team stage 1/2: Thorough verification for '{claim[:50]}...'")
    
    thorough_input = f"""Claim: {claim}
Context: {claim_context}
Background: {background_research}

Verification strategy: thorough (first stage of red team verification)"""
    
    try:
        thorough_result = await Runner.run(thorough_verifier_agent, thorough_input)
        initial = thorough_result.final_output
        initial.verification_strategy = "thorough"
    except Exception as e:
        print(f"Red team verification failed at stage 1: {e}")
        return SingleClaimCitation(
            claim=claim,
            confidence_score=0,
            is_verified=False,
            verification_strategy="red_teamed",
            supporting_citations=[],
            contradicting_citations=[],
            confidence_rationale=f"Thorough verification failed: {str(e)}",
            search_queries_used=[],
            red_team_critiques=[f"Verification error: {str(e)}"]
        ).model_dump()
    
    # STAGE 2: Red team challenge using reusable agent
    print(f"Red team stage 2/2: Adversarial challenge for '{claim[:50]}...'")
    
    red_team_input = f"""INITIAL THOROUGH VERIFICATION TO CHALLENGE:
{initial.model_dump_json(indent=2)}

Your task: Challenge this verification aggressively.
- Search for contradicting evidence
- Find flaws in the reasoning
- Lower confidence if you find problems
- Add your critiques to red_team_critiques field

Remember: You can only LOWER or MAINTAIN the confidence score, never increase it."""
    
    try:
        red_team_result = await Runner.run(red_team_challenger_agent, red_team_input)
        final = red_team_result.final_output
        final.verification_strategy = "red_teamed"
        
        # CRITICAL: Ensure confidence doesn't increase
        final.confidence_score = min(final.confidence_score, initial.confidence_score)
        
        # Merge search queries from both stages
        final.search_queries_used = list(set(
            initial.search_queries_used + final.search_queries_used
        ))
        
        print(f"Red team complete: {initial.confidence_score} → {final.confidence_score}")
        
        return final.model_dump()
        
    except Exception as e:
        print(f"Red team verification failed at stage 2: {e}")
        # Return initial result with red team error note
        initial.verification_strategy = "red_teamed"
        initial.red_team_critiques = [f"Red team challenge failed: {str(e)}"]
        return initial.model_dump()


@function_tool
async def group_verify(claims: list[str], shared_context: str, semantic_topic: str) -> dict:
    """Verify 2-3 related claims together efficiently
    
    IMPORTANT: Limited to max 3 claims to prevent JSON output truncation.
    
    Args:
        claims: List of 2-3 related claims (will be limited if more provided)
        shared_context: Shared context for all claims
        semantic_topic: The common topic/domain
    
    Returns:
        GroupVerificationResult with verified claims
    """
    
    # CRITICAL: Limit group size to prevent JSON truncation
    original_count = len(claims)
    if len(claims) > 3:
        print(f"⚠️  Group has {len(claims)} claims, limiting to first 3 to prevent output truncation")
        claims = claims[:3]
    
    # Limit context length as well
    context_limit = 500
    if len(shared_context) > context_limit:
        shared_context = shared_context[:context_limit] + "..."
    
    claims_text = "\n".join([f"{i+1}. {c[:200]}" for i, c in enumerate(claims)])  # Limit claim length
    
    input_text = f"""RELATED CLAIMS (Topic: {semantic_topic}):
{claims_text}

Context: {shared_context}

Verify using 2-3 searches. For each claim be CONCISE:
- Keep rationale under 150 words
- Max 3 supporting citations
- Max 2 contradicting citations"""
    
    try:
        result = await Runner.run(group_verifier_agent, input_text)
        
        # Ensure all claims have correct metadata
        for claim_result in result.final_output.verified_claims:
            claim_result.verification_strategy = "grouped"
            claim_result.grouped_with = claims
        
        verified_count = len(result.final_output.verified_claims)
        if verified_count < len(claims):
            print(f"⚠️  Group verification returned {verified_count}/{len(claims)} claims")
        
        return {"verified_claims": [c.model_dump() for c in result.final_output.verified_claims]}
        
    except Exception as e:
        error_str = str(e)
        print(f"❌ Group verification error: {error_str[:200]}")
        
        # Detect JSON truncation errors
        if any(keyword in error_str for keyword in ["JSON", "EOF", "parse", "truncat"]):
            print("🔄 JSON truncation detected, falling back to individual quick verifications")
            
            # Fallback: Verify each claim individually using quick_verify
            individual_results = []
            for claim in claims:
                try:
                    quick_result = await Runner.run(
                        quick_verifier_agent,
                        f"Claim: {claim}\nContext: {shared_context[:200]}"
                    )
                    output = quick_result.final_output
                    output.verification_strategy = "grouped"  # Mark as originally intended for group
                    output.grouped_with = claims
                    individual_results.append(output)
                except Exception as inner_e:
                    print(f"⚠️  Fallback verification also failed for claim: {claim[:50]}...")
                    # Create placeholder with medium confidence
                    individual_results.append(
                        SingleClaimCitation(
                            claim=claim,
                            confidence_score=50,
                            is_verified=False,
                            verification_strategy="grouped",
                            supporting_citations=[],
                            contradicting_citations=[],
                            confidence_rationale=f"Group verification failed, fallback also failed: {str(inner_e)[:100]}",
                            search_queries_used=[]
,
                            grouped_with=claims
                        )
                    )
            
            print(f"✓ Fallback complete: {len(individual_results)}/{len(claims)} claims verified individually")
            return {"verified_claims": [c.model_dump() for c in individual_results]}
        
        # For non-truncation errors, return low-confidence placeholders
        print("💀 Non-truncation error, returning low-confidence placeholders")
        failed_results = [
            SingleClaimCitation(
                claim=claim,
                confidence_score=0,
                is_verified=False,
                verification_strategy="grouped",
                supporting_citations=[],
                contradicting_citations=[],
                confidence_rationale=f"Group verification failed: {error_str[:100]}",
                search_queries_used=[],
                grouped_with=claims
            )
            for claim in claims
        ]
        return {"verified_claims": [c.model_dump() for c in failed_results]}


# ========================================
# HELPER FUNCTIONS
# ========================================

def parse_verification_result(result: dict) -> list[SingleClaimCitation] | SingleClaimCitation:
    """Parse any verification result into SingleClaimCitation(s)
    
    This handles both single results and group results uniformly.
    
    Args:
        result: Dict from any verification tool
    
    Returns:
        Single citation or list of citations
    """
    if "verified_claims" in result:
        # Group result - return list
        return [SingleClaimCitation(**c) for c in result["verified_claims"]]
    else:
        # Single result
        return SingleClaimCitation(**result)


# ========================================
# EXPORTS
# ========================================

__all__ = [
    # Models
    "SingleClaimCitation",
    "GroupVerificationResult",
    
    # Agents (for reuse in complex workflows)
    "quick_verifier_agent",
    "thorough_verifier_agent",
    "red_team_challenger_agent",
    "group_verifier_agent",
    
    # Tool functions
    "skip_verification",
    "quick_verify",
    "thorough_verify",
    "red_team_verify",
    "group_verify",
    
    # Helpers
    "parse_verification_result",
]
