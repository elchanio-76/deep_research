from agents import Agent, ModelSettings

from src.agents.brave_search_tool import brave_web_search
from src.agents.search_agent import INSTRUCTIONS
from src.config.settings import SEARCH_MODEL

brave_search_agent = Agent(
    name="Brave Search Agent",
    instructions=INSTRUCTIONS,
    tools=[brave_web_search],
    model=SEARCH_MODEL,
    model_settings=ModelSettings(tool_choice="required"),
)
