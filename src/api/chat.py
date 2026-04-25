"""Chat endpoint — POST /chat."""

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette import EventSourceResponse

import src.db.sessions as db_sessions
from src.api.dependencies import get_pool, get_research_manager
from src.core.research_manager import ResearchManager
from src.models.api import ChatRequest
from src.streaming.sse import chat_event_stream

router = APIRouter()


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    rm: ResearchManager = Depends(get_research_manager),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Start a Q&A chat session against a previously generated research report.

    Loads the session from the database, hydrates ResearchManager state,
    and streams the answer back as SSE chunk events. Quality/bias analysis
    routing (/quality, /bias) is handled transparently inside rm.chat().
    """
    session = await db_sessions.load_session(pool, body.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.get("report_markdown"):
        raise HTTPException(
            status_code=404, detail="No report available for this session"
        )

    # Hydrate ResearchManager state from the loaded session row
    await rm.load_session(str(body.session_id))

    history = [(msg.role, msg.content) for msg in body.history]

    return EventSourceResponse(
        chat_event_stream(request, rm, body.message, history),
        ping=15,
    )
