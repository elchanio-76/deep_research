"""Unit tests for SSE event formatting functions.

Tests each format_*() function with known inputs and edge cases.
_Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_
"""

import json

from src.streaming.sse import (
    format_chunk,
    format_complete,
    format_cost,
    format_error,
    format_progress,
    format_report,
)


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------


def test_format_progress_structure():
    result = json.loads(format_progress("Planning searches..."))
    assert result == {"type": "progress", "message": "Planning searches..."}


def test_format_report_structure():
    result = json.loads(format_report("# Report\n\nContent"))
    assert result == {"type": "report", "content": "# Report\n\nContent"}


def test_format_cost_structure():
    summary = {"total_input_tokens": 100, "total_cost": 0.01}
    result = json.loads(format_cost(summary))
    assert result == {"type": "cost", "summary": summary}


def test_format_chunk_structure():
    result = json.loads(format_chunk("partial answer"))
    assert result == {"type": "chunk", "content": "partial answer"}


def test_format_error_structure():
    result = json.loads(format_error("Something went wrong"))
    assert result == {"type": "error", "message": "Something went wrong"}


def test_format_complete_structure():
    result = json.loads(format_complete())
    assert result == {"type": "complete"}
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_format_progress_empty_string():
    result = json.loads(format_progress(""))
    assert result["type"] == "progress"
    assert result["message"] == ""


def test_format_report_special_characters():
    content = "# Report\n\n```python\nprint('hello')\n```\n\n> Quote with \"quotes\""
    result = json.loads(format_report(content))
    assert result["content"] == content


def test_format_cost_empty_dict():
    result = json.loads(format_cost({}))
    assert result == {"type": "cost", "summary": {}}


def test_format_chunk_large_payload():
    large = "x" * 100_000
    result = json.loads(format_chunk(large))
    assert result["content"] == large


def test_format_error_unicode():
    msg = "Error: 日本語テスト 🔥"
    result = json.loads(format_error(msg))
    assert result["message"] == msg


def test_format_complete_no_extra_keys():
    result = json.loads(format_complete())
    assert set(result.keys()) == {"type"}
