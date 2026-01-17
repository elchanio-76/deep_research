from agents import Agent
from pydantic import BaseModel, Field

from config import SESSION_TITLE_MODEL

INSTRUCTIONS = (
    "You generate a concise, one-sentence session title summarizing the user's "
    "initial research prompt. Keep it under 12 words and avoid punctuation-heavy output."
)


class SessionTitle(BaseModel):
    title: str = Field(description="One-sentence session title for the prompt")


session_title_agent = Agent(
    name="Session title agent",
    instructions=INSTRUCTIONS,
    output_type=SessionTitle,
    model=SESSION_TITLE_MODEL,
)
