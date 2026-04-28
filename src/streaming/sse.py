"""SSE event formatting and async stream adapters."""

import json

from sse_starlette import EventSourceResponse
from starlette.requests import Request


# ---------------------------------------------------------------------------
# Pure format functions — each returns a JSON string
# ---------------------------------------------------------------------------


def format_event(event_type: str, **payload) -> str:
    """Format a JSON SSE event: {"type": event_type, ...payload}"""
    return json.dumps({"type": event_type, **payload})


def format_progress(message: str) -> str:
    return format_event("progress", message=message)


def format_report(content: str) -> str:
    return format_event("report", content=content)


def format_cost(summary: dict) -> str:
    return format_event("cost", summary=summary)


def format_chunk(content: str) -> str:
    return format_event("chunk", content=content)


def format_error(message: str) -> str:
    return format_event("error", message=message)


def format_complete() -> str:
    return format_event("complete")


def format_session_id(session_id: str) -> str:
    return format_event("session_id", session_id=session_id)


# ---------------------------------------------------------------------------
# Async generators — wrap ResearchManager generators as SSE event streams
# ---------------------------------------------------------------------------

_FINAL_REPORT_PREFIX = "\n---\n## Final Report\n\n"


async def research_event_stream(
    request: Request, rm, query: str, search_mode: str, cost_effective: bool
):
    """Wrap ResearchManager.run() yields into typed SSE events."""
    try:
        async for chunk in rm.run(query, search_mode, cost_effective):
            if await request.is_disconnected():
                break
            if chunk.startswith("View trace: https://"):
                yield format_progress(chunk.strip())
            elif chunk.startswith(_FINAL_REPORT_PREFIX):
                markdown = chunk[len(_FINAL_REPORT_PREFIX) :]
                yield format_report(markdown)
                yield format_cost(rm._cost_summary_snapshot())
                if rm.current_session_id is not None:
                    yield format_session_id(str(rm.current_session_id))
                yield format_complete()
            elif chunk.strip() == "Research complete!":
                # complete is already emitted after the report yield; skip
                pass
            else:
                stripped = chunk.strip()
                if stripped:
                    yield format_progress(stripped)
    except Exception as e:
        yield format_error(str(e))


async def chat_event_stream(request: Request, rm, message: str, history):
    """Wrap ResearchManager.chat() yields into typed SSE events."""
    try:
        first = True
        async for chunk in rm.chat(message, history):
            if await request.is_disconnected():
                break
            if first:
                # First yield is the trace URL
                yield format_chunk(chunk)
                first = False
            else:
                yield format_chunk(chunk)
        yield format_complete()
    except Exception as e:
        yield format_error(str(e))


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def create_sse_response(generator, request: Request) -> EventSourceResponse:
    return EventSourceResponse(generator, ping=15)
