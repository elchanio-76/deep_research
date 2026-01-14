from agents import Agent, Runner, function_tool

from config import QUALITY_AGENT_MAX_SEARCHES, QUALITY_MODEL
from new_models import QualityReport
from search_agent import search_agent

QUALITY_INSTRUCTIONS = """You are a research quality and bias analysis assistant.

Evaluate the report and search context for research quality and bias signals.
Score each criterion on a 1-5 scale (1 = low, 5 = excellent).

Primary criteria:
- Source diversity
- Credibility tiers
- Recency
- Author expertise

Meta-scores (derived from the primary criteria and available evidence):
- Geographic balance
- Political balance
- Stance distribution

Use the quality_web_search tool if needed to validate credibility, recency, or author expertise.
Provide at most 3 targeted queries in a single tool call.

Output requirements:
- Populate all scores and meta-scores with integer values from 1 to 5.
- Provide concise, actionable risk flags.
- Summarize the main findings in 1-3 short paragraphs.
- Include an appendix listing evaluated sources and follow-up questions.
"""


@function_tool
async def quality_web_search(queries: list[str]) -> list[dict[str, str]]:
    """Run up to three targeted searches for quality analysis."""
    limited_queries = queries[:QUALITY_AGENT_MAX_SEARCHES]
    results: list[dict[str, str]] = []

    for query in limited_queries:
        search_input = (
            f"Search term: {query}\n"
            "Reason for searching: Research quality and bias analysis."
        )
        try:
            result = await Runner.run(search_agent, search_input)
            summary = str(result.final_output)
        except Exception as exc:
            summary = f"Search failed: {exc}"

        results.append({"query": query, "summary": summary})

    return results


quality_agent = Agent(
    name="Quality & Bias Analysis Agent",
    instructions=QUALITY_INSTRUCTIONS,
    tools=[quality_web_search],
    model=QUALITY_MODEL,
    output_type=QualityReport,
)
