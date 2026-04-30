from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

# --- Requests ---


class ResearchStartRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="Research query")
    search_mode: str = Field(
        default="no_adaptive",
        description="Search mode",
        pattern="^(no_adaptive|deep_dive|deep_dive_gap_fill)$",
    )
    cost_effective: bool = Field(
        default=False, description="Use Brave search for cost savings"
    )


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    session_id: UUID
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list)


# --- Responses ---


class SessionSummary(BaseModel):
    id: UUID
    header: Optional[str] = None
    initial_prompt: str
    created_at: datetime


class CostSummary(BaseModel):
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tool_calls: int = 0
    total_cost: float = 0.0


class SessionDetail(BaseModel):
    id: UUID
    header: Optional[str] = None
    initial_prompt: str
    report_markdown: Optional[str] = None
    cost_summary: CostSummary
    chat_history: list[ChatMessage] = Field(default_factory=list)
    search_mode: str = "no_adaptive"
    cost_effective: bool = False


# --- SSE Events ---


class SSEEvent(BaseModel):
    type: str  # "progress" | "report" | "cost" | "chunk" | "error" | "complete"


class ProgressEvent(SSEEvent):
    type: str = "progress"
    message: str


class ReportEvent(SSEEvent):
    type: str = "report"
    content: str


class CostEvent(SSEEvent):
    type: str = "cost"
    summary: CostSummary


class ChunkEvent(SSEEvent):
    type: str = "chunk"
    content: str


class ErrorEvent(SSEEvent):
    type: str = "error"
    message: str


class CompleteEvent(SSEEvent):
    type: str = "complete"
