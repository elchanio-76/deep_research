"""
Property 3: Invalid request bodies produce HTTP 422.
Feature: fastapi-backend-refactor, Property 3: Invalid request rejection

**Validates: Requirements 4.7, 10.6**
"""

import asyncio
from unittest.mock import MagicMock

import httpx
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.api.main import app

# ---------------------------------------------------------------------------
# Pre-populate app.state so dependencies resolve without a real DB.
# This avoids triggering the lifespan (which needs a real Postgres connection).
# FastAPI validates the request body before calling the handler, but it still
# resolves dependencies in parallel — so state must be present.
# ---------------------------------------------------------------------------
app.state.pool = MagicMock()
app.state.research_manager = MagicMock()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_SEARCH_MODES = ["no_adaptive", "deep_dive", "deep_dive_gap_fill"]


async def _post(path: str, body: dict) -> httpx.Response:
    """POST to the app using ASGITransport (no lifespan needed)."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(path, json=body)


def _assert_422(response: httpx.Response) -> None:
    assert (
        response.status_code == 422
    ), f"Expected 422, got {response.status_code}: {response.text}"
    data = response.json()
    assert "detail" in data, f"No 'detail' key in response: {data}"


# ---------------------------------------------------------------------------
# /api/research/start — invalid bodies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_start_missing_query():
    """**Validates: Requirements 4.7, 10.6**
    Missing required 'query' field returns HTTP 422.
    """
    response = await _post("/api/research/start", {})
    _assert_422(response)


@pytest.mark.asyncio
async def test_research_start_empty_query():
    """**Validates: Requirements 4.7, 10.6**
    Empty string 'query' (violates min_length=1) returns HTTP 422.
    """
    response = await _post("/api/research/start", {"query": ""})
    _assert_422(response)


@pytest.mark.asyncio
async def test_research_start_invalid_search_mode():
    """**Validates: Requirements 4.7, 10.6**
    Invalid 'search_mode' value returns HTTP 422.
    """
    response = await _post(
        "/api/research/start",
        {"query": "test", "search_mode": "invalid_mode"},
    )
    _assert_422(response)


@pytest.mark.asyncio
async def test_research_start_wrong_type_cost_effective():
    """**Validates: Requirements 4.7, 10.6**
    Non-boolean string for 'cost_effective' that can't be coerced returns HTTP 422.
    """
    response = await _post(
        "/api/research/start",
        {"query": "test", "cost_effective": "not-a-bool"},
    )
    _assert_422(response)


@pytest.mark.asyncio
async def test_research_start_empty_body():
    """**Validates: Requirements 4.7, 10.6**
    Completely empty body returns HTTP 422.
    """
    response = await _post("/api/research/start", {})
    _assert_422(response)


@pytest.mark.asyncio
async def test_research_start_extra_fields_only():
    """**Validates: Requirements 4.7, 10.6**
    Body with only extra/unknown fields (no required fields) returns HTTP 422.
    """
    response = await _post(
        "/api/research/start",
        {"unknown_field": "value", "another": 123},
    )
    _assert_422(response)


# ---------------------------------------------------------------------------
# /api/chat — invalid bodies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_missing_session_id():
    """**Validates: Requirements 4.7, 10.6**
    Missing 'session_id' returns HTTP 422.
    """
    response = await _post("/api/chat", {"message": "hello"})
    _assert_422(response)


@pytest.mark.asyncio
async def test_chat_invalid_uuid_session_id():
    """**Validates: Requirements 4.7, 10.6**
    Invalid UUID string for 'session_id' returns HTTP 422.
    """
    response = await _post(
        "/api/chat",
        {"session_id": "not-a-valid-uuid", "message": "hello"},
    )
    _assert_422(response)


@pytest.mark.asyncio
async def test_chat_missing_message():
    """**Validates: Requirements 4.7, 10.6**
    Missing required 'message' field returns HTTP 422.
    """
    response = await _post(
        "/api/chat",
        {"session_id": "123e4567-e89b-12d3-a456-426614174000"},
    )
    _assert_422(response)


@pytest.mark.asyncio
async def test_chat_empty_message():
    """**Validates: Requirements 4.7, 10.6**
    Empty string 'message' (violates min_length=1) returns HTTP 422.
    """
    response = await _post(
        "/api/chat",
        {"session_id": "123e4567-e89b-12d3-a456-426614174000", "message": ""},
    )
    _assert_422(response)


@pytest.mark.asyncio
async def test_chat_invalid_role_in_history():
    """**Validates: Requirements 4.7, 10.6**
    Invalid 'role' in history items returns HTTP 422.
    """
    response = await _post(
        "/api/chat",
        {
            "session_id": "123e4567-e89b-12d3-a456-426614174000",
            "message": "hello",
            "history": [{"role": "admin", "content": "hi"}],
        },
    )
    _assert_422(response)


@pytest.mark.asyncio
async def test_chat_empty_body():
    """**Validates: Requirements 4.7, 10.6**
    Completely empty body returns HTTP 422.
    """
    response = await _post("/api/chat", {})
    _assert_422(response)


# ---------------------------------------------------------------------------
# Property-based tests — hypothesis generates invalid payloads
# ---------------------------------------------------------------------------


@given(
    search_mode=st.text().filter(lambda s: s not in VALID_SEARCH_MODES),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_research_start_invalid_search_mode_property(search_mode):
    """**Validates: Requirements 4.7, 10.6**
    Property: any search_mode not in the allowed set produces HTTP 422.
    """
    response = asyncio.get_event_loop().run_until_complete(
        _post(
            "/api/research/start", {"query": "test query", "search_mode": search_mode}
        )
    )
    _assert_422(response)


@given(
    role=st.text().filter(lambda r: r not in ["user", "assistant"]),
    content=st.text(),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_chat_invalid_role_property(role, content):
    """**Validates: Requirements 4.7, 10.6**
    Property: any role not in {'user', 'assistant'} in history produces HTTP 422.
    """
    response = asyncio.get_event_loop().run_until_complete(
        _post(
            "/api/chat",
            {
                "session_id": "123e4567-e89b-12d3-a456-426614174000",
                "message": "hello",
                "history": [{"role": role, "content": content}],
            },
        )
    )
    _assert_422(response)
