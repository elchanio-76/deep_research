from agents import Agent, ModelSettings

from brave_search_tool import brave_web_search
from config import SEARCH_MODEL
from search_agent import INSTRUCTIONS

brave_search_agent = Agent(
    name="Brave Search Agent",
    instructions=INSTRUCTIONS,
    tools=[brave_web_search],
    model=SEARCH_MODEL,
    model_settings=ModelSettings(tool_choice="required"),
)
