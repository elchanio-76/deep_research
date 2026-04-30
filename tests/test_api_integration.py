"""Integration tests for FastAPI API endpoints.

Tests cover:
- POST /api/research/start — SSE event sequence with mocked ResearchManager.run()
- POST /api/chat — SSE chunk/complete events with mocked ResearchManager.chat()
- GET /api/sessions — list sessions from mocked pool
- GET /api/sessions/{id} — get session detail, 404 for missing
- DELETE /api/sessions/{id} — delete session, 204 on success, 404 if missing
- GET /api/sessions/{id}/cost — cost summary, 404 for missing

_Requirements: 4.1, 5.1, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2_
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.api.main import app
from src.api.dependencies import get_pool, get_research_manager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_sse_events(body: bytes) -> list[dict]:
    """Parse raw SSE response body into a list of JSON event dicts."""
    events = []
    text = body.decode("utf-8")
    for block in text.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                data = line[len("data:") :].strip()
                if data:
                    try:
                        events.append(json.loads(data))
                    except json.JSONDecodeError:
                        pass
    return events


def _make_session_row(
    session_id: uuid.UUID | None = None,
    header: str | None = "Test Header",
    initial_prompt: str = "What is AI?",
    report_markdown: str | None = "# Report\n\nContent here.",
    search_mode: str = "no_adaptive",
    cost_effective_search: bool = False,
    cost_summary: dict | None = None,
) -> dict:
    """Build a fake session row dict as returned by db_sessions.load_session."""
    if session_id is None:
        session_id = uuid.uuid4()
    if cost_summary is None:
        cost_summary = {
            "total_input_tokens": 100,
            "total_output_tokens": 50,
            "total_tool_calls": 5,
            "total_cost": 0.0012,
        }
    return {
        "id": session_id,
        "header": header,
        "initial_prompt": initial_prompt,
        "report_markdown": report_markdown,
        "search_mode": search_mode,
        "cost_effective_search": cost_effective_search,
        "usage_jsonb": None,
        "cost_summary_jsonb": json.dumps(cost_summary),
        "created_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        "last_activity_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    }


async def _async_gen(*items):
    """Helper: async generator that yields the given items."""
    for item in items:
        yield item


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_pool():
    """A MagicMock standing in for asyncpg.Pool."""
    return MagicMock()


@pytest.fixture
def mock_rm():
    """A MagicMock standing in for ResearchManager."""
    return MagicMock()


@pytest.fixture
def test_client(mock_pool, mock_rm):
    """httpx.AsyncClient with dependency overrides — no lifespan needed."""
    app.dependency_overrides[get_pool] = lambda: mock_pool
    app.dependency_overrides[get_research_manager] = lambda: mock_rm
    # Also set app.state so any direct state access works
    app.state.pool = mock_pool
    app.state.research_manager = mock_rm
    yield httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Research endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_start_sse_event_sequence(test_client, mock_rm):
    """POST /api/research/start streams progress → report → cost → complete events.

    _Requirements: 4.1, 4.2, 4.3, 4.4_
    """
    report_text = "# Final Report\n\nThis is the research."
    final_report_chunk = f"\n---\n## Final Report\n\n{report_text}"

    async def fake_run(query, search_mode, cost_effective):
        yield "Planning searches...\n"
        yield "Executing searches...\n"
        yield final_report_chunk

    mock_rm.run = fake_run
    mock_rm._cost_summary_snapshot.return_value = {
        "total_input_tokens": 200,
        "total_output_tokens": 100,
        "total_tool_calls": 3,
        "total_cost": 0.005,
    }

    async with test_client as client:
        response = await client.post(
            "/api/research/start",
            json={"query": "What is machine learning?"},
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")

    events = _parse_sse_events(response.content)
    types = [e["type"] for e in events]

    assert "progress" in types
    assert "report" in types
    assert "cost" in types
    assert "complete" in types

    # Verify ordering: progress events come before report
    report_idx = types.index("report")
    assert all(types[i] == "progress" for i in range(report_idx))

    # Verify report content
    report_event = next(e for e in events if e["type"] == "report")
    assert report_event["content"] == report_text

    # Verify cost event structure
    cost_event = next(e for e in events if e["type"] == "cost")
    assert "summary" in cost_event
    assert cost_event["summary"]["total_input_tokens"] == 200

    # complete is last
    assert types[-1] == "complete"


@pytest.mark.asyncio
async def test_research_start_progress_messages(test_client, mock_rm):
    """Progress strings from run() become progress SSE events.

    _Requirements: 4.3_
    """

    async def fake_run(query, search_mode, cost_effective):
        yield "Planning searches...\n"
        yield "Executing searches...\n"
        yield "Writing initial report...\n"
        yield "\n---\n## Final Report\n\nDone."

    mock_rm.run = fake_run
    mock_rm._cost_summary_snapshot.return_value = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tool_calls": 0,
        "total_cost": 0.0,
    }

    async with test_client as client:
        response = await client.post(
            "/api/research/start",
            json={"query": "test query"},
        )

    events = _parse_sse_events(response.content)
    progress_events = [e for e in events if e["type"] == "progress"]
    messages = [e["message"] for e in progress_events]

    assert "Planning searches..." in messages
    assert "Executing searches..." in messages
    assert "Writing initial report..." in messages


@pytest.mark.asyncio
async def test_research_start_error_event_on_exception(test_client, mock_rm):
    """If run() raises, an error SSE event is emitted.

    _Requirements: 4.5_
    """

    async def fake_run_raises(query, search_mode, cost_effective):
        yield "Starting...\n"
        raise RuntimeError("Pipeline exploded")

    mock_rm.run = fake_run_raises

    async with test_client as client:
        response = await client.post(
            "/api/research/start",
            json={"query": "test"},
        )

    events = _parse_sse_events(response.content)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert "Pipeline exploded" in error_events[0]["message"]


@pytest.mark.asyncio
async def test_research_start_invalid_body_returns_422(test_client):
    """Missing required 'query' field returns HTTP 422.

    _Requirements: 4.7_
    """
    async with test_client as client:
        response = await client.post("/api/research/start", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_research_start_invalid_search_mode_returns_422(test_client):
    """Invalid search_mode returns HTTP 422.

    _Requirements: 4.7_
    """
    async with test_client as client:
        response = await client.post(
            "/api/research/start",
            json={"query": "test", "search_mode": "invalid"},
        )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Chat endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_sse_chunk_and_complete_events(test_client, mock_rm, mock_pool):
    """POST /api/chat streams chunk events then a complete event.

    _Requirements: 5.1, 5.2, 5.3, 5.4_
    """
    session_id = uuid.uuid4()
    session_row = _make_session_row(session_id=session_id)

    async def fake_chat(message, history):
        yield "View trace: https://platform.openai.com/traces/trace?trace_id=abc"
        yield "Based on the report, "
        yield "the answer is 42."

    mock_rm.chat = fake_chat
    mock_rm.load_session = AsyncMock(
        return_value=(
            session_row["report_markdown"],
            "",
            [],
            "What is AI?",
            "no_adaptive",
            False,
        )
    )

    with patch(
        "src.api.chat.db_sessions.load_session", new=AsyncMock(return_value=session_row)
    ):
        async with test_client as client:
            response = await client.post(
                "/api/chat",
                json={
                    "session_id": str(session_id),
                    "message": "What is the main finding?",
                    "history": [],
                },
            )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")

    events = _parse_sse_events(response.content)
    types = [e["type"] for e in events]

    assert "chunk" in types
    assert types[-1] == "complete"

    chunk_events = [e for e in events if e["type"] == "chunk"]
    assert len(chunk_events) == 3
    contents = [e["content"] for e in chunk_events]
    assert any("trace" in c for c in contents)
    assert any("answer is 42" in c for c in contents)


@pytest.mark.asyncio
async def test_chat_returns_404_for_missing_session(test_client, mock_pool):
    """POST /api/chat returns 404 when session_id does not exist.

    _Requirements: 5.5, 6.3_
    """
    with patch(
        "src.api.chat.db_sessions.load_session", new=AsyncMock(return_value=None)
    ):
        async with test_client as client:
            response = await client.post(
                "/api/chat",
                json={
                    "session_id": str(uuid.uuid4()),
                    "message": "hello",
                },
            )

    assert response.status_code == 404
    assert "Session not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_chat_returns_404_when_no_report(test_client, mock_pool):
    """POST /api/chat returns 404 when session exists but has no report.

    _Requirements: 5.5_
    """
    session_id = uuid.uuid4()
    session_row = _make_session_row(session_id=session_id, report_markdown=None)

    with patch(
        "src.api.chat.db_sessions.load_session", new=AsyncMock(return_value=session_row)
    ):
        async with test_client as client:
            response = await client.post(
                "/api/chat",
                json={
                    "session_id": str(session_id),
                    "message": "hello",
                },
            )

    assert response.status_code == 404
    assert "No report" in response.json()["detail"]


@pytest.mark.asyncio
async def test_chat_error_event_on_exception(test_client, mock_rm, mock_pool):
    """If chat() raises, an error SSE event is emitted.

    _Requirements: 5.2_
    """
    session_id = uuid.uuid4()
    session_row = _make_session_row(session_id=session_id)

    async def fake_chat_raises(message, history):
        yield "Starting..."
        raise ValueError("Chat failed")

    mock_rm.chat = fake_chat_raises
    mock_rm.load_session = AsyncMock(
        return_value=(
            session_row["report_markdown"],
            "",
            [],
            "What is AI?",
            "no_adaptive",
            False,
        )
    )

    with patch(
        "src.api.chat.db_sessions.load_session", new=AsyncMock(return_value=session_row)
    ):
        async with test_client as client:
            response = await client.post(
                "/api/chat",
                json={
                    "session_id": str(session_id),
                    "message": "hello",
                },
            )

    events = _parse_sse_events(response.content)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert "Chat failed" in error_events[0]["message"]


# ---------------------------------------------------------------------------
# Session CRUD tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sessions_returns_array(test_client, mock_pool):
    """GET /api/sessions returns a JSON array of session summaries.

    _Requirements: 6.1_
    """
    session_id = uuid.uuid4()
    rows = [
        {
            "id": session_id,
            "header": "AI Research",
            "initial_prompt": "What is AI?",
            "created_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        }
    ]

    with patch(
        "src.api.sessions.db_sessions.list_sessions", new=AsyncMock(return_value=rows)
    ):
        async with test_client as client:
            response = await client.get("/api/sessions")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == str(session_id)
    assert data[0]["initial_prompt"] == "What is AI?"
    assert data[0]["header"] == "AI Research"


@pytest.mark.asyncio
async def test_list_sessions_empty(test_client, mock_pool):
    """GET /api/sessions returns empty array when no sessions exist.

    _Requirements: 6.1_
    """
    with patch(
        "src.api.sessions.db_sessions.list_sessions", new=AsyncMock(return_value=[])
    ):
        async with test_client as client:
            response = await client.get("/api/sessions")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_session_returns_full_detail(test_client, mock_pool):
    """GET /api/sessions/{id} returns full session data.

    _Requirements: 6.2_
    """
    session_id = uuid.uuid4()
    session_row = _make_session_row(session_id=session_id)
    chat_rows = [
        {"role": "user", "content": "What is AI?"},
        {"role": "assistant", "content": "AI is..."},
    ]

    with (
        patch(
            "src.api.sessions.db_sessions.load_session",
            new=AsyncMock(return_value=session_row),
        ),
        patch(
            "src.api.sessions.db_messages.fetch_chat_messages",
            new=AsyncMock(return_value=chat_rows),
        ),
    ):
        async with test_client as client:
            response = await client.get(f"/api/sessions/{session_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(session_id)
    assert data["initial_prompt"] == "What is AI?"
    assert data["report_markdown"] == "# Report\n\nContent here."
    assert data["search_mode"] == "no_adaptive"
    assert data["cost_effective"] is False
    assert len(data["chat_history"]) == 2
    assert data["chat_history"][0]["role"] == "user"
    assert "cost_summary" in data
    assert data["cost_summary"]["total_input_tokens"] == 100


@pytest.mark.asyncio
async def test_get_session_404_for_missing(test_client, mock_pool):
    """GET /api/sessions/{id} returns 404 when session does not exist.

    _Requirements: 6.3_
    """
    with patch(
        "src.api.sessions.db_sessions.load_session", new=AsyncMock(return_value=None)
    ):
        async with test_client as client:
            response = await client.get(f"/api/sessions/{uuid.uuid4()}")

    assert response.status_code == 404
    assert "Session not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_session_returns_204(test_client, mock_pool):
    """DELETE /api/sessions/{id} returns 204 when session is deleted.

    _Requirements: 6.4_
    """
    session_id = uuid.uuid4()

    with patch(
        "src.api.sessions.db_sessions.delete_session", new=AsyncMock(return_value=True)
    ):
        async with test_client as client:
            response = await client.delete(f"/api/sessions/{session_id}")

    assert response.status_code == 204
    assert response.content == b""


@pytest.mark.asyncio
async def test_delete_session_404_for_missing(test_client, mock_pool):
    """DELETE /api/sessions/{id} returns 404 when session does not exist.

    _Requirements: 6.5_
    """
    with patch(
        "src.api.sessions.db_sessions.delete_session", new=AsyncMock(return_value=False)
    ):
        async with test_client as client:
            response = await client.delete(f"/api/sessions/{uuid.uuid4()}")

    assert response.status_code == 404
    assert "Session not found" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Cost endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_cost_returns_summary(test_client, mock_pool):
    """GET /api/sessions/{id}/cost returns cost summary JSON.

    _Requirements: 7.1_
    """
    session_id = uuid.uuid4()
    session_row = _make_session_row(
        session_id=session_id,
        cost_summary={
            "total_input_tokens": 1500,
            "total_output_tokens": 800,
            "total_tool_calls": 12,
            "total_cost": 0.0847,
        },
    )

    with patch(
        "src.api.sessions.db_sessions.load_session",
        new=AsyncMock(return_value=session_row),
    ):
        async with test_client as client:
            response = await client.get(f"/api/sessions/{session_id}/cost")

    assert response.status_code == 200
    data = response.json()
    assert data["total_input_tokens"] == 1500
    assert data["total_output_tokens"] == 800
    assert data["total_tool_calls"] == 12
    assert abs(data["total_cost"] - 0.0847) < 1e-6


@pytest.mark.asyncio
async def test_get_cost_404_for_missing_session(test_client, mock_pool):
    """GET /api/sessions/{id}/cost returns 404 when session does not exist.

    _Requirements: 7.2_
    """
    with patch(
        "src.api.sessions.db_sessions.load_session", new=AsyncMock(return_value=None)
    ):
        async with test_client as client:
            response = await client.get(f"/api/sessions/{uuid.uuid4()}/cost")

    assert response.status_code == 404
    assert "Session not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_cost_defaults_when_no_cost_data(test_client, mock_pool):
    """GET /api/sessions/{id}/cost returns zero defaults when cost_summary_jsonb is null.

    _Requirements: 7.1_
    """
    session_id = uuid.uuid4()
    session_row = _make_session_row(session_id=session_id)
    session_row["cost_summary_jsonb"] = None  # no cost data stored

    with patch(
        "src.api.sessions.db_sessions.load_session",
        new=AsyncMock(return_value=session_row),
    ):
        async with test_client as client:
            response = await client.get(f"/api/sessions/{session_id}/cost")

    assert response.status_code == 200
    data = response.json()
    assert data["total_input_tokens"] == 0
    assert data["total_output_tokens"] == 0
    assert data["total_tool_calls"] == 0
    assert data["total_cost"] == 0.0
