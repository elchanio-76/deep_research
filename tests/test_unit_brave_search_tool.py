"""
Unit tests for src/agents/brave_search_tool.py.

Covers Requirements 15.1–15.7 and Property 15.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from src.agents.brave_search_tool import (
    MAX_BRAVE_RESULTS,
    _format_brave_results,
    _process_search_response,
)

# ---------------------------------------------------------------------------
# Example tests for _format_brave_results — Requirements 15.1, 15.3, 15.4
# ---------------------------------------------------------------------------


def test_format_brave_results_empty_list_returns_no_results_message():
    # Requirement 15.1
    result = _format_brave_results([])
    assert result == "No Brave results found."


def test_format_brave_results_single_result_includes_fields():
    # Sanity check: a single well-formed result is rendered correctly.
    results = [
        {"title": "My Title", "url": "https://example.com", "description": "A summary"}
    ]
    output = _format_brave_results(results)
    assert "My Title" in output
    assert "https://example.com" in output
    assert "A summary" in output


def test_format_brave_results_truncates_to_max_brave_results():
    # Requirement 15.3 — list longer than MAX_BRAVE_RESULTS is capped.
    results = [
        {
            "title": f"Title {i}",
            "url": f"https://example.com/{i}",
            "description": f"Desc {i}",
        }
        for i in range(MAX_BRAVE_RESULTS + 5)
    ]
    output = _format_brave_results(results)
    # Titles beyond the cap must not appear.
    for i in range(MAX_BRAVE_RESULTS):
        assert f"Title {i}" in output
    for i in range(MAX_BRAVE_RESULTS, MAX_BRAVE_RESULTS + 5):
        assert f"Title {i}" not in output


def test_format_brave_results_exactly_max_brave_results_items():
    # Requirement 15.3 — exactly MAX_BRAVE_RESULTS items are all included.
    results = [
        {"title": f"T{i}", "url": f"https://x.com/{i}", "description": f"D{i}"}
        for i in range(MAX_BRAVE_RESULTS)
    ]
    output = _format_brave_results(results)
    for i in range(MAX_BRAVE_RESULTS):
        assert f"T{i}" in output


def test_format_brave_results_missing_title_substitutes_untitled():
    # Requirement 15.4 — result without "title" key falls back to "Untitled".
    results = [{"url": "https://example.com", "description": "Some description"}]
    output = _format_brave_results(results)
    assert "Untitled" in output


def test_format_brave_results_none_title_substitutes_untitled():
    # Requirement 15.4 — result with title=None also falls back to "Untitled".
    results = [{"title": None, "url": "https://example.com", "description": "desc"}]
    output = _format_brave_results(results)
    assert "Untitled" in output


def test_format_brave_results_missing_url_does_not_raise():
    # Graceful handling: missing "url" key should not raise.
    results = [{"title": "No URL", "description": "desc"}]
    output = _format_brave_results(results)
    assert "No URL" in output


def test_format_brave_results_missing_description_does_not_raise():
    # Graceful handling: missing "description" key should not raise.
    results = [{"title": "No Desc", "url": "https://example.com"}]
    output = _format_brave_results(results)
    assert "No Desc" in output


# ---------------------------------------------------------------------------
# Property test for _format_brave_results — Property 15 / Requirement 15.2
# ---------------------------------------------------------------------------

# Strategy: dicts with all three required fields present and non-empty title/url.
_brave_result = st.fixed_dictionaries(
    {
        "title": st.text(min_size=1, max_size=100),
        "url": st.text(min_size=1, max_size=200),
        "description": st.text(min_size=0, max_size=300),
    }
)
_result_list = st.lists(_brave_result, min_size=1, max_size=MAX_BRAVE_RESULTS)


@given(results=_result_list)
@settings(max_examples=100)
def test_property_format_brave_results_includes_all_fields(results: list[dict]):
    """
    # Feature: unit-test-strategy, Property 15:
    # _format_brave_results includes all fields for each result.

    For any non-empty list of result dicts (up to MAX_BRAVE_RESULTS) each
    containing title, url, and description, _format_brave_results SHALL
    include each result's title, URL, and description in the returned string.
    """
    output = _format_brave_results(results)
    for r in results:
        assert r["title"] in output, f"title {r['title']!r} missing from output"
        assert r["url"] in output, f"url {r['url']!r} missing from output"
        # description may be empty string — only check when non-empty
        if r["description"]:
            assert (
                r["description"] in output
            ), f"description {r['description']!r} missing from output"


# ---------------------------------------------------------------------------
# Example tests for _process_search_response — Requirements 15.5, 15.6, 15.7
# ---------------------------------------------------------------------------


def test_process_search_response_valid_payload_returns_results():
    # Requirement 15.5 — well-formed API response returns the results list.
    expected = [{"title": "A", "url": "https://a.com"}]
    payload = {"web": {"results": expected}}
    assert _process_search_response(payload) == expected


def test_process_search_response_empty_results_list():
    # Requirement 15.5 — valid structure but empty results list.
    payload = {"web": {"results": []}}
    assert _process_search_response(payload) == []


def test_process_search_response_missing_web_key_returns_empty_list():
    # Requirement 15.6 — dict without "web" key returns [].
    assert _process_search_response({"other": "data"}) == []


def test_process_search_response_empty_dict_returns_empty_list():
    # Requirement 15.6 — empty dict returns [].
    assert _process_search_response({}) == []


def test_process_search_response_non_dict_returns_empty_list():
    # Requirement 15.7 — non-dict input returns [].
    assert _process_search_response("not a dict") == []  # type: ignore[arg-type]


def test_process_search_response_none_returns_empty_list():
    # Requirement 15.7 — None input returns [].
    assert _process_search_response(None) == []  # type: ignore[arg-type]


def test_process_search_response_list_input_returns_empty_list():
    # Requirement 15.7 — list input returns [].
    assert _process_search_response([{"web": {"results": []}}]) == []  # type: ignore[arg-type]


def test_process_search_response_web_value_not_dict_returns_empty_list():
    # Edge case: "web" key present but its value is not a dict.
    assert _process_search_response({"web": "unexpected"}) == []
