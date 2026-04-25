"""
Property 2: Request DTO validation accepts valid inputs and rejects invalid inputs.
Feature: fastapi-backend-refactor, Property 2: DTO Validation

**Validates: Requirements 10.1, 10.2, 10.6**
"""

import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from src.models.api import ChatRequest, ResearchStartRequest

VALID_SEARCH_MODES = ["no_adaptive", "deep_dive", "deep_dive_gap_fill"]

# ---------------------------------------------------------------------------
# ResearchStartRequest — valid inputs accepted
# ---------------------------------------------------------------------------


@given(
    query=st.text(min_size=1),
    search_mode=st.sampled_from(VALID_SEARCH_MODES),
    cost_effective=st.booleans(),
)
@settings(max_examples=100)
def test_research_start_request_valid(query, search_mode, cost_effective):
    """**Validates: Requirements 10.1, 10.2**
    Valid ResearchStartRequest inputs are accepted without ValidationError.
    """
    req = ResearchStartRequest(
        query=query, search_mode=search_mode, cost_effective=cost_effective
    )
    assert req.query == query
    assert req.search_mode == search_mode
    assert req.cost_effective == cost_effective


# ---------------------------------------------------------------------------
# ResearchStartRequest — invalid inputs rejected
# ---------------------------------------------------------------------------


def test_research_start_request_empty_query_rejected():
    """**Validates: Requirements 10.1, 10.6**
    Empty query raises ValidationError.
    """
    with pytest.raises(ValidationError):
        ResearchStartRequest(query="")


@given(search_mode=st.text().filter(lambda s: s not in VALID_SEARCH_MODES))
@settings(max_examples=100)
def test_research_start_request_invalid_search_mode_rejected(search_mode):
    """**Validates: Requirements 10.2, 10.6**
    Invalid search_mode raises ValidationError.
    """
    with pytest.raises(ValidationError):
        ResearchStartRequest(query="test query", search_mode=search_mode)


def test_research_start_request_missing_query_rejected():
    """**Validates: Requirements 10.1, 10.6**
    Missing required query field raises ValidationError.
    """
    with pytest.raises(ValidationError):
        ResearchStartRequest()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ChatRequest — valid inputs accepted
# ---------------------------------------------------------------------------


@given(
    session_id=st.uuids(),
    message=st.text(min_size=1),
    history=st.lists(
        st.fixed_dictionaries(
            {
                "role": st.sampled_from(["user", "assistant"]),
                "content": st.text(),
            }
        ),
        max_size=10,
    ),
)
@settings(max_examples=100)
def test_chat_request_valid(session_id, message, history):
    """**Validates: Requirements 10.1, 10.2**
    Valid ChatRequest inputs are accepted without ValidationError.
    """
    req = ChatRequest(session_id=session_id, message=message, history=history)
    assert req.session_id == session_id
    assert req.message == message


# ---------------------------------------------------------------------------
# ChatRequest — invalid inputs rejected
# ---------------------------------------------------------------------------


def test_chat_request_empty_message_rejected():
    """**Validates: Requirements 10.1, 10.6**
    Empty message raises ValidationError.
    """
    with pytest.raises(ValidationError):
        ChatRequest(session_id=uuid.uuid4(), message="")


@given(
    role=st.text().filter(lambda r: r not in ["user", "assistant"]),
    content=st.text(),
)
@settings(max_examples=100)
def test_chat_request_invalid_role_rejected(role, content):
    """**Validates: Requirements 10.2, 10.6**
    Invalid role in history raises ValidationError.
    """
    with pytest.raises(ValidationError):
        ChatRequest(
            session_id=uuid.uuid4(),
            message="hello",
            history=[{"role": role, "content": content}],
        )


def test_chat_request_missing_session_id_rejected():
    """**Validates: Requirements 10.1, 10.6**
    Missing session_id raises ValidationError.
    """
    with pytest.raises(ValidationError):
        ChatRequest(message="hello")  # type: ignore[call-arg]


def test_chat_request_invalid_uuid_rejected():
    """**Validates: Requirements 10.6**
    Invalid UUID string for session_id raises ValidationError.
    """
    with pytest.raises(ValidationError):
        ChatRequest(session_id="not-a-uuid", message="hello")
