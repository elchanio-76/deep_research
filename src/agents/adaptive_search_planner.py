from agents import Agent

from src.config.settings import ADAPTIVE_SEARCH_MODEL
from src.models.domain import AdaptiveSearchPlan

INSTRUCTIONS = (
    "You are an adaptive search planner that proposes follow-up searches after an initial "
    "search phase. You must respect the remaining search budget and choose deep-dive and "
    "gap-filling searches. Gap-filling should address missing subtopics, source diversity, "
    "and recency gaps. Return only searches that fit within the remaining budget."
)


adaptive_search_planner = Agent(
    name="Adaptive search planner",
    instructions=INSTRUCTIONS,
    output_type=AdaptiveSearchPlan,
    model=ADAPTIVE_SEARCH_MODEL,
)
