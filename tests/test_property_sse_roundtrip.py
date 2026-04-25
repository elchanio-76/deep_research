"""
Property 1: SSE event formatting round-trip.
Feature: fastapi-backend-refactor, Property 1: SSE event formatting round-trip

**Validates: Requirements 4.6, 8.5, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7**
"""

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from src.streaming.sse import (
    format_chunk,
    format_complete,
    format_cost,
    format_error,
    format_progress,
    format_report,
)


@given(msg=st.text())
@settings(max_examples=100)
def test_format_progress_roundtrip(msg):
    """**Validates: Requirements 9.1**
    format_progress produces valid JSON with type='progress' and matching message.
    """
    parsed = json.loads(format_progress(msg))
    assert parsed["type"] == "progress"
    assert parsed["message"] == msg


@given(content=st.text())
@settings(max_examples=100)
def test_format_report_roundtrip(content):
    """**Validates: Requirements 9.2**
    format_report produces valid JSON with type='report' and matching content.
    """
    parsed = json.loads(format_report(content))
    assert parsed["type"] == "report"
    assert parsed["content"] == content


@given(summary=st.dictionaries(st.text(), st.text()))
@settings(max_examples=100)
def test_format_cost_roundtrip(summary):
    """**Validates: Requirements 9.3**
    format_cost produces valid JSON with type='cost' and matching summary.
    """
    parsed = json.loads(format_cost(summary))
    assert parsed["type"] == "cost"
    assert parsed["summary"] == summary


@given(content=st.text())
@settings(max_examples=100)
def test_format_chunk_roundtrip(content):
    """**Validates: Requirements 9.4**
    format_chunk produces valid JSON with type='chunk' and matching content.
    """
    parsed = json.loads(format_chunk(content))
    assert parsed["type"] == "chunk"
    assert parsed["content"] == content


@given(msg=st.text())
@settings(max_examples=100)
def test_format_error_roundtrip(msg):
    """**Validates: Requirements 9.5**
    format_error produces valid JSON with type='error' and matching message.
    """
    parsed = json.loads(format_error(msg))
    assert parsed["type"] == "error"
    assert parsed["message"] == msg


def test_format_complete_roundtrip():
    """**Validates: Requirements 9.6**
    format_complete produces valid JSON with only the 'type' key set to 'complete'.
    """
    parsed = json.loads(format_complete())
    assert parsed["type"] == "complete"
    assert len(parsed) == 1
