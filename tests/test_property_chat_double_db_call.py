"""Property-based tests for the double DB call bug in POST /chat.

Bug: src/api/chat.py calls db_sessions.load_session once for guard checks,
then calls rm.load_session() which internally calls db_sessions.load_session
again — resulting in two DB round-trips for the same session row per request.

**Validates: Requirements 1.1, 1.2**
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from hypothesis import given, settings
from hypothesis import strategies as st

from src.api.chat import chat
from src.config.settings import SEARCH_MODE_DEFAULT
from src.core.research_manager import ResearchManager
from src.models.api import ChatRequest
from src.models.domain import SessionUsage


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

search_mode_st = st.sampled_from(["no_adaptive", "deep_dive", "deep_dive_gap_fill"])
cost_effective_st = st.booleans()
report_markdown_st = st.text(min_size=1, max_size=500)


# ---------------------------------------------------------------------------
# Property 1: Bug Condition — Double DB Call on Valid Chat Request
#
# CRITICAL: This test MUST FAIL on unfixed code — failure confirms the bug exists.
# The test encodes the expected (correct) behavior: exactly 1 DB call per request.
# It will pass after the fix is applied.
#
# **Validates: Requirements 1.1, 1.2**
# ---------------------------------------------------------------------------


@given(
    report_markdown=report_markdown_st,
    search_mode=search_mode_st,
    cost_effective_search=cost_effective_st,
)
@settings(max_examples=20)
@pytest.mark.asyncio
async def test_property_bug_condition_single_db_call(
    report_markdown, search_mode, cost_effective_search
):
    """Property 1: Bug Condition — db_sessions.load_session called exactly once per valid POST /chat.

    On UNFIXED code this test FAILS because the handler calls load_session once
    for the guard check and rm.load_session() calls it a second time internally,
    resulting in call_count == 2.

    On FIXED code this test PASSES because the prefetched row is passed through
    to rm.load_session(), eliminating the redundant DB call.

    **Validates: Requirements 1.1, 1.2**
    """
    session_id = uuid.uuid4()
    session_row = {
        "id": session_id,
        "initial_prompt": "test query",
        "search_mode": search_mode,
        "cost_effective_search": cost_effective_search,
        "report_markdown": report_markdown,
        "header": "Test Session",
        "usage_jsonb": None,
        "cost_summary_jsonb": None,
    }

    # Patch db_sessions.load_session at the source module level so ALL callers
    # (both chat.py and research_manager.py) hit the same mock, letting us count
    # the total number of DB calls across the entire request lifecycle.
    with patch("src.db.sessions.load_session", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = session_row

        # Build a ResearchManager with a mock pool.
        # We do NOT mock rm.load_session — we let it run its real implementation
        # so that its internal db_sessions.load_session call is counted.
        # We DO mock rm.chat to avoid real LLM calls.
        mock_pool = MagicMock()
        rm = ResearchManager(pool=mock_pool)

        # Mock db_messages.fetch_chat_messages to avoid real DB calls from
        # rm.load_session's message fetch (not the call we're counting).
        with patch(
            "src.db.messages.fetch_chat_messages", new_callable=AsyncMock
        ) as mock_fetch_msgs:
            mock_fetch_msgs.return_value = []

            # Mock rm.chat to avoid real LLM calls while still being an async generator.
            async def fake_chat(message, history):
                yield "test response"

            rm.chat = fake_chat

            # Build the request body.
            body = ChatRequest(
                session_id=session_id,
                message="test question",
                history=[],
            )

            # Mock the Starlette Request object.
            mock_request = MagicMock()
            mock_request.is_disconnected = AsyncMock(return_value=False)

            # Call the chat handler directly (bypasses FastAPI dependency injection).
            response = await chat(
                body=body,
                request=mock_request,
                rm=rm,
                pool=mock_pool,
            )

            # Consume the SSE stream so the async generator inside runs to completion
            # and all db_sessions.load_session calls are made before we assert.
            if hasattr(response, "body_iterator"):
                async for _ in response.body_iterator:
                    pass

            # Assert db_sessions.load_session was called exactly once.
            # On UNFIXED code this will be 2 (once in guard check, once inside
            # rm.load_session), causing this assertion to FAIL — confirming the bug.
            assert mock_load.call_count == 1, (
                f"Expected db_sessions.load_session to be called exactly 1 time, "
                f"but it was called {mock_load.call_count} times. "
                f"Counterexample: session_row with "
                f"report_markdown={report_markdown!r}, "
                f"search_mode={search_mode!r}, "
                f"cost_effective_search={cost_effective_search!r}"
            )


# ---------------------------------------------------------------------------
# Hypothesis strategies for preservation tests
# ---------------------------------------------------------------------------

# usage_jsonb can be None or a dict (serialised as JSON string in real DB,
# but load_session receives the already-decoded dict from asyncpg)
usage_jsonb_st = st.one_of(
    st.none(),
    st.fixed_dictionaries({}),
)

# report_markdown: either None/empty (no report) or non-empty text
report_markdown_nonempty_st = st.text(min_size=1, max_size=200)
report_markdown_empty_st = st.one_of(st.none(), st.just(""))

session_row_st = st.fixed_dictionaries(
    {
        "initial_prompt": st.text(min_size=1, max_size=100),
        "search_mode": st.one_of(
            st.none(),
            st.sampled_from(["no_adaptive", "deep_dive", "deep_dive_gap_fill"]),
        ),
        "cost_effective_search": st.booleans(),
        "usage_jsonb": usage_jsonb_st,
        "cost_summary_jsonb": st.none(),
        "report_markdown": report_markdown_nonempty_st,
        "header": st.text(min_size=0, max_size=80),
    }
)


def _make_full_session_row(session_id: uuid.UUID, row_overrides: dict) -> dict:
    """Merge generated fields with required DB row fields."""
    base = {
        "id": session_id,
        "initial_prompt": "test query",
        "search_mode": "no_adaptive",
        "cost_effective_search": False,
        "usage_jsonb": None,
        "cost_summary_jsonb": None,
        "report_markdown": "# Report",
        "header": "Test Session",
    }
    base.update(row_overrides)
    return base


# ---------------------------------------------------------------------------
# Property 2a: Hydration state preservation
#
# For any valid session row dict, calling rm.load_session(session_id_str) with
# a DB mock returning that row sets all six hydration fields correctly.
# This establishes the baseline on UNFIXED code.
#
# **Validates: Requirements 3.3, 3.5**
# ---------------------------------------------------------------------------


@given(
    search_mode=st.one_of(
        st.none(),
        st.sampled_from(["no_adaptive", "deep_dive", "deep_dive_gap_fill"]),
    ),
    cost_effective_search=st.booleans(),
    usage_jsonb=usage_jsonb_st,
    report_markdown=st.one_of(st.none(), st.just(""), report_markdown_nonempty_st),
)
@settings(max_examples=30)
@pytest.mark.asyncio
async def test_preservation_hydration_state(
    search_mode, cost_effective_search, usage_jsonb, report_markdown
):
    """Property 2a: rm.load_session hydrates all six fields correctly from DB row.

    Establishes baseline on UNFIXED code: the six hydration fields are set
    correctly after calling rm.load_session(session_id_str) with a mocked DB.

    **Validates: Requirements 3.3, 3.5**
    """
    session_id = uuid.uuid4()
    session_id_str = str(session_id)

    session_row = _make_full_session_row(
        session_id,
        {
            "search_mode": search_mode,
            "cost_effective_search": cost_effective_search,
            "usage_jsonb": usage_jsonb,
            "report_markdown": report_markdown,
        },
    )

    mock_pool = MagicMock()

    with patch("src.db.sessions.load_session", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = session_row

        with patch(
            "src.db.messages.fetch_chat_messages", new_callable=AsyncMock
        ) as mock_fetch_msgs:
            mock_fetch_msgs.return_value = []

            rm = ResearchManager(pool=mock_pool)
            await rm.load_session(session_id_str)

    # 1. current_session_id
    assert rm.current_session_id == uuid.UUID(session_id_str), (
        f"current_session_id mismatch: {rm.current_session_id!r} != "
        f"{uuid.UUID(session_id_str)!r}"
    )

    # 2. last_query
    assert (
        rm.last_query == session_row["initial_prompt"]
    ), f"last_query mismatch: {rm.last_query!r} != {session_row['initial_prompt']!r}"

    # 3. search_mode (falls back to SEARCH_MODE_DEFAULT when None)
    expected_search_mode = session_row["search_mode"] or SEARCH_MODE_DEFAULT
    assert (
        rm.search_mode == expected_search_mode
    ), f"search_mode mismatch: {rm.search_mode!r} != {expected_search_mode!r}"

    # 4. cost_effective_search
    assert rm.cost_effective_search == session_row.get(
        "cost_effective_search", False
    ), (
        f"cost_effective_search mismatch: {rm.cost_effective_search!r} != "
        f"{session_row.get('cost_effective_search', False)!r}"
    )

    # 5. session_usage is a valid SessionUsage instance
    assert isinstance(
        rm.session_usage, SessionUsage
    ), f"session_usage is not a SessionUsage instance: {type(rm.session_usage)!r}"

    # 6. report is set (not None) when report_markdown is non-empty, None otherwise
    if session_row.get("report_markdown"):
        assert (
            rm.report is not None
        ), "report should be set when report_markdown is non-empty, but got None"
    else:
        assert rm.report is None, (
            f"report should be None when report_markdown is empty/None, "
            f"but got {rm.report!r}"
        )


# ---------------------------------------------------------------------------
# Property 2b: Gradio path preservation
#
# rm.load_session without prefetched_row still calls db_sessions.load_session
# exactly once (Gradio path must not be broken by the fix).
#
# **Validates: Requirement 3.5**
# ---------------------------------------------------------------------------


@given(
    search_mode=st.one_of(
        st.none(),
        st.sampled_from(["no_adaptive", "deep_dive", "deep_dive_gap_fill"]),
    ),
    cost_effective_search=st.booleans(),
    report_markdown=report_markdown_nonempty_st,
)
@settings(max_examples=20)
@pytest.mark.asyncio
async def test_preservation_gradio_path_single_db_call(
    search_mode, cost_effective_search, report_markdown
):
    """Property 2b: rm.load_session (no prefetched_row) calls db_sessions.load_session exactly once.

    Ensures the Gradio thin-client path continues to issue exactly one DB call
    when no prefetched row is supplied.

    **Validates: Requirement 3.5**
    """
    session_id = uuid.uuid4()
    session_id_str = str(session_id)

    session_row = _make_full_session_row(
        session_id,
        {
            "search_mode": search_mode,
            "cost_effective_search": cost_effective_search,
            "report_markdown": report_markdown,
        },
    )

    mock_pool = MagicMock()

    with patch("src.db.sessions.load_session", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = session_row

        with patch(
            "src.db.messages.fetch_chat_messages", new_callable=AsyncMock
        ) as mock_fetch_msgs:
            mock_fetch_msgs.return_value = []

            rm = ResearchManager(pool=mock_pool)
            await rm.load_session(session_id_str)

    assert mock_load.call_count == 1, (
        f"Expected db_sessions.load_session to be called exactly 1 time on the "
        f"Gradio path, but it was called {mock_load.call_count} times. "
        f"Counterexample: search_mode={search_mode!r}, "
        f"cost_effective_search={cost_effective_search!r}, "
        f"report_markdown={report_markdown!r}"
    )


# ---------------------------------------------------------------------------
# Property 2c: Missing session → HTTP 404 "Session not found"
#
# When db_sessions.load_session returns None, the chat handler raises HTTP 404
# with detail "Session not found".
#
# **Validates: Requirement 3.1**
# ---------------------------------------------------------------------------


@given(
    search_mode=st.one_of(
        st.none(),
        st.sampled_from(["no_adaptive", "deep_dive", "deep_dive_gap_fill"]),
    ),
    cost_effective_search=st.booleans(),
    report_markdown=report_markdown_nonempty_st,
)
@settings(max_examples=20)
@pytest.mark.asyncio
async def test_preservation_missing_session_404(
    search_mode, cost_effective_search, report_markdown
):
    """Property 2c: Missing session → HTTP 404 with detail 'Session not found'.

    When db_sessions.load_session returns None, the chat handler must raise
    HTTPException(status_code=404, detail='Session not found').

    **Validates: Requirement 3.1**
    """
    session_id = uuid.uuid4()
    mock_pool = MagicMock()
    rm = ResearchManager(pool=mock_pool)

    with patch("src.db.sessions.load_session", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = None  # session does not exist

        body = ChatRequest(
            session_id=session_id,
            message="test question",
            history=[],
        )
        mock_request = MagicMock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await chat(
                body=body,
                request=mock_request,
                rm=rm,
                pool=mock_pool,
            )

    assert (
        exc_info.value.status_code == 404
    ), f"Expected HTTP 404, got {exc_info.value.status_code}"
    assert (
        exc_info.value.detail == "Session not found"
    ), f"Expected detail 'Session not found', got {exc_info.value.detail!r}"


# ---------------------------------------------------------------------------
# Property 2d: Session with no report → HTTP 404 "No report available"
#
# When the session exists but report_markdown is None or "", the chat handler
# raises HTTP 404 with detail "No report available for this session".
#
# **Validates: Requirement 3.2**
# ---------------------------------------------------------------------------


@given(
    search_mode=st.one_of(
        st.none(),
        st.sampled_from(["no_adaptive", "deep_dive", "deep_dive_gap_fill"]),
    ),
    cost_effective_search=st.booleans(),
    report_markdown=report_markdown_empty_st,
)
@settings(max_examples=20)
@pytest.mark.asyncio
async def test_preservation_no_report_404(
    search_mode, cost_effective_search, report_markdown
):
    """Property 2d: Session with no report → HTTP 404 'No report available for this session'.

    When db_sessions.load_session returns a row with report_markdown=None or "",
    the chat handler must raise HTTPException(status_code=404,
    detail='No report available for this session').

    **Validates: Requirement 3.2**
    """
    session_id = uuid.uuid4()
    mock_pool = MagicMock()
    rm = ResearchManager(pool=mock_pool)

    session_row = _make_full_session_row(
        session_id,
        {
            "search_mode": search_mode,
            "cost_effective_search": cost_effective_search,
            "report_markdown": report_markdown,  # None or ""
        },
    )

    with patch("src.db.sessions.load_session", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = session_row

        body = ChatRequest(
            session_id=session_id,
            message="test question",
            history=[],
        )
        mock_request = MagicMock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await chat(
                body=body,
                request=mock_request,
                rm=rm,
                pool=mock_pool,
            )

    assert (
        exc_info.value.status_code == 404
    ), f"Expected HTTP 404, got {exc_info.value.status_code}"
    assert exc_info.value.detail == "No report available for this session", (
        f"Expected detail 'No report available for this session', "
        f"got {exc_info.value.detail!r}"
    )
