from agents import Agent

from config import DEFAULT_NUM_SEARCHES, PLANNER_MODEL
from new_models import WebSearchPlan


class PlannerAgent(Agent):
    # Initialize agent with a model, instructions and number of searches
    def __init__(
        self, model: str = PLANNER_MODEL, num_searches: int = DEFAULT_NUM_SEARCHES
    ):
        instructions = (
            "You are a helpful research assistant. Given a query, come up with a set "
            "of web searches to perform to best answer the query. Output "
            f"{num_searches} terms to query for."
        )

        super().__init__(
            name="PlannerAgent",
            instructions=instructions,
            model=model,
            output_type=WebSearchPlan,
        )
        self.num_searches = num_searches
        self.model = model
