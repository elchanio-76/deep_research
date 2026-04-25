"""Session management endpoints — GET/DELETE /sessions."""

import json
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Response

import src.db.messages as db_messages
import src.db.sessions as db_sessions
from src.api.dependencies import get_pool
from src.models.api import CostSummary, SessionDetail, SessionSummary, ChatMessage

router = APIRouter()


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(pool: asyncpg.Pool = Depends(get_pool)):
    """Return all sessions ordered by last activity descending."""
    rows = await db_sessions.list_sessions(pool)
    return [SessionSummary(**row) for row in rows]


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: UUID,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Return full session data including report, cost summary, and chat history."""
    row = await db_sessions.load_session(pool, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    cost_data = {}
    if row.get("cost_summary_jsonb"):
        raw = row["cost_summary_jsonb"]
        cost_data = json.loads(raw) if isinstance(raw, str) else raw

    chat_rows = await db_messages.fetch_chat_messages(pool, session_id)
    chat_history = [
        ChatMessage(role=m["role"], content=m["content"]) for m in chat_rows
    ]

    return SessionDetail(
        id=row["id"],
        header=row.get("header"),
        initial_prompt=row["initial_prompt"],
        report_markdown=row.get("report_markdown"),
        cost_summary=CostSummary(**cost_data),
        chat_history=chat_history,
        search_mode=row.get("search_mode", "no_adaptive"),
        cost_effective=row.get("cost_effective_search", False),
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: UUID,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Delete a session and its messages. Returns 204 on success, 404 if not found."""
    deleted = await db_sessions.delete_session(pool, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return Response(status_code=204)


@router.get("/sessions/{session_id}/cost", response_model=CostSummary)
async def get_session_cost(
    session_id: UUID,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Return the cost summary for a session."""
    row = await db_sessions.load_session(pool, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    cost_data = {}
    if row.get("cost_summary_jsonb"):
        raw = row["cost_summary_jsonb"]
        cost_data = json.loads(raw) if isinstance(raw, str) else raw

    return CostSummary(**cost_data)
