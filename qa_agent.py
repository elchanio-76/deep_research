from agents import Agent, Runner, WebSearchTool, function_tool
from pydantic import BaseModel, Field

from quality_agent import QualityReport, quality_agent

QUALITY_COMMANDS = {"/quality", "/bias"}
QUALITY_TRIGGER_PHRASES = {
    "run bias analysis",
    "quality check",
    "evaluate research quality",
    "run quality analysis",
}

INSTRUCTIONS = (
    "You are a data analyst assistant answering questions about a report."
    "Your job is to analyze the report's context and provide the most accurate answer possible."
    "If you cannot answer the questions based on the provided context, you can search the web "
    "for additional sources."
    "If the user requests a quality or bias analysis (e.g., /quality, /bias, or phrases like "
    "'run bias analysis' or 'quality check'), call the run_quality_analysis tool."
    "When returning the quality analysis, format the answer with sections in this order: "
    "Scores, Risk Flags, Summary, Appendix."
    "In the Appendix, list evaluated sources and recommended follow-up questions."
)


class QA_Response(BaseModel):
    question: str = Field(description="The question that was asked")
    answer: str = Field(description="The answer to the question")
    sources: list[str] = Field(
        description="List of unique source URLs used to answer the question",
        max_length=10,
    )


@function_tool
async def run_quality_analysis(
    report_text: str,
    search_context: list[str],
    original_query: str | None = None,
) -> QualityReport:
    """Run quality and bias analysis on the report."""
    search_summary = (
        "\n".join(search_context) if search_context else "No search context provided."
    )
    query_text = original_query or "Unknown"

    input_text = f"""ORIGINAL QUERY:
{query_text}

REPORT:
{report_text}

SEARCH SUMMARIES:
{search_summary}
"""

    result = await Runner.run(quality_agent, input_text)
    quality_report = QualityReport.model_validate(result.final_output)
    return quality_report


def is_quality_request(message: str) -> bool:
    normalized = message.strip().lower()
    if normalized in QUALITY_COMMANDS:
        return True
    return any(phrase in normalized for phrase in QUALITY_TRIGGER_PHRASES)


qa_agent = Agent(
    name="QA agent",
    instructions=INSTRUCTIONS,
    tools=[run_quality_analysis, WebSearchTool(search_context_size="low")],
    output_type=QA_Response,
    model="gpt-4o-mini",
)
