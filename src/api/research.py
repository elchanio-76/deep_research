from fastapi import APIRouter, Depends, Request
from sse_starlette import EventSourceResponse

from src.api.dependencies import get_research_manager
from src.core.research_manager import ResearchManager
from src.models.api import ResearchStartRequest
from src.streaming.sse import research_event_stream

router = APIRouter()


@router.post("/research/start")
async def start_research(
    body: ResearchStartRequest,
    request: Request,
    rm: ResearchManager = Depends(get_research_manager),
):
    return EventSourceResponse(
        research_event_stream(
            request, rm, body.query, body.search_mode, body.cost_effective
        ),
        ping=15,
    )
