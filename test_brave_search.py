"""Unit tests for Brave Search tool and agent."""

import asyncio
import os
from unittest import mock

import pytest
from agents import Agent, ModelSettings

# Import modules under test
import brave_search_tool as bst_module
from brave_search_tool import (
    BRAVE_SEARCH_URL,
    MAX_BRAVE_RESULTS,
    _enforce_brave_rate_limit,
    _format_brave_results,
    _get_brave_api_key,
    _brave_web_search_impl,
    _process_search_response,
    brave_web_search,
)
from brave_search_agent import brave_search_agent, INSTRUCTIONS


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_rate_limit_state():
    """Reset the global rate limit state before each test."""
    bst_module._last_brave_call_at = 0.0
    yield
    bst_module._last_brave_call_at = 0.0


@pytest.fixture
def mock_session_usage():
    """Mock session usage for tracking tool calls."""
    with mock.patch("usage_tracker.get_session_usage") as mock_get:
        mock_usage = mock.MagicMock()
        mock_get.return_value = mock_usage
        yield mock_usage


@pytest.fixture
def mock_env_api_key():
    """Set a mock BRAVE_API_KEY environment variable."""
    with mock.patch.dict(os.environ, {"BRAVE_API_KEY": "test-api-key"}):
        yield


@pytest.fixture
def mock_env_no_api_key():
    """Ensure BRAVE_API_KEY is not set."""
    with mock.patch.dict(os.environ, {}, clear=True):
        with mock.patch.object(os, "getenv", return_value=None):
            yield


@pytest.fixture
def sample_brave_response():
    """Return a sample Brave API response."""
    return {
        "web": {
            "results": [
                {
                    "title": "Test Result 1",
                    "url": "https://example.com/1",
                    "description": "This is the first test result.",
                },
                {
                    "title": "Test Result 2",
                    "url": "https://example.com/2",
                    "description": "This is the second test result.",
                },
                {
                    "title": "Test Result 3",
                    "link": "https://example.com/3",
                    "snippet": "This is the third test result using alternate fields.",
                },
            ]
        }
    }


@pytest.fixture
def mock_fetch_brave_results():
    """Mock _fetch_brave_results for API calls."""
    with mock.patch("brave_search_tool._fetch_brave_results") as mock_fetch:
        yield mock_fetch


# =============================================================================
# Tests for _get_brave_api_key
# =============================================================================


class TestGetBraveApiKey:
    """Tests for the _get_brave_api_key function."""

    def test_returns_api_key_when_set(self):
        """Should return the API key when BRAVE_API_KEY is set."""
        with mock.patch.dict(os.environ, {"BRAVE_API_KEY": "my-secret-key"}):
            result = _get_brave_api_key()
            assert result == "my-secret-key"

    def test_returns_none_when_not_set(self):
        """Should return None when BRAVE_API_KEY is not set."""
        with mock.patch.dict(os.environ, {}, clear=True):
            result = _get_brave_api_key()
            assert result is None


# =============================================================================
# Tests for _enforce_brave_rate_limit
# =============================================================================


class TestEnforceBraveRateLimit:
    """Tests for the _enforce_brave_rate_limit function."""

    @pytest.mark.asyncio
    async def test_no_delay_on_first_call(self):
        """Should not delay on the first API call."""
        with mock.patch("brave_search_tool.BRAVE_RATE_LIMIT_SECONDS", 1.0):
            start = asyncio.get_event_loop().time()
            await _enforce_brave_rate_limit()
            elapsed = asyncio.get_event_loop().time() - start
            assert elapsed < 0.1  # Should be nearly instant

    @pytest.mark.asyncio
    async def test_enforces_rate_limit(self):
        """Should enforce rate limit between consecutive calls."""
        with mock.patch("brave_search_tool.BRAVE_RATE_LIMIT_SECONDS", 0.5):
            await _enforce_brave_rate_limit()
            start = asyncio.get_event_loop().time()
            await _enforce_brave_rate_limit()
            elapsed = asyncio.get_event_loop().time() - start
            assert elapsed >= 0.5  # Should wait at least 0.5 seconds

    @pytest.mark.asyncio
    async def test_no_delay_after_sufficient_time(self):
        """Should not delay if sufficient time has passed."""
        with mock.patch("brave_search_tool.BRAVE_RATE_LIMIT_SECONDS", 10.0):
            await _enforce_brave_rate_limit()
            # Simulate time passing
            bst_module._last_brave_call_at -= 15.0
            start = asyncio.get_event_loop().time()
            await _enforce_brave_rate_limit()
            elapsed = asyncio.get_event_loop().time() - start
            assert elapsed < 0.1  # Should be nearly instant


# =============================================================================
# Tests for _format_brave_results
# =============================================================================


class TestFormatBraveResults:
    """Tests for the _format_brave_results function."""

    def test_empty_results(self):
        """Should return a message when no results are found."""
        result = _format_brave_results([])
        assert result == "No Brave results found."

    def test_single_result(self):
        """Should format a single result correctly."""
        results = [{"title": "Test", "url": "https://test.com", "description": "Desc"}]
        result = _format_brave_results(results)
        assert "Brave Search Results:" in result
        assert "Test" in result
        assert "https://test.com" in result
        assert "Desc" in result

    def test_multiple_results(self):
        """Should format multiple results correctly."""
        results = [
            {"title": "Title 1", "url": "https://1.com", "description": "Desc 1"},
            {"title": "Title 2", "url": "https://2.com", "description": "Desc 2"},
        ]
        result = _format_brave_results(results)
        assert "Title 1" in result
        assert "Title 2" in result
        assert "https://1.com" in result
        assert "https://2.com" in result

    def test_alternate_fields(self):
        """Should handle 'link' and 'snippet' as fallback fields."""
        results = [
            {"title": "Test", "link": "https://test.com", "snippet": "Snippet text"}
        ]
        result = _format_brave_results(results)
        assert "https://test.com" in result
        assert "Snippet text" in result

    def test_missing_fields(self):
        """Should handle missing fields gracefully."""
        results = [{}]
        result = _format_brave_results(results)
        assert "Untitled" in result
        assert "URL:" in result
        assert "Summary:" in result

    def test_limits_to_max_results(self):
        """Should limit results to MAX_BRAVE_RESULTS."""
        results = [
            {
                "title": f"Title {i}",
                "url": f"https://{i}.com",
                "description": f"Desc {i}",
            }
            for i in range(MAX_BRAVE_RESULTS + 5)
        ]
        result = _format_brave_results(results)
        # Count how many titles appear
        title_count = result.count("Title ")
        assert title_count == MAX_BRAVE_RESULTS


# =============================================================================
# Tests for _process_search_response
# =============================================================================


class TestProcessSearchResponse:
    """Tests for the _process_search_response function."""

    def test_extracts_results_from_valid_response(self):
        """Should extract results from a valid API response."""
        payload = {
            "web": {
                "results": [
                    {"title": "Result 1", "url": "https://1.com"},
                    {"title": "Result 2", "url": "https://2.com"},
                ]
            }
        }
        results = _process_search_response(payload)
        assert len(results) == 2
        assert results[0]["title"] == "Result 1"

    def test_handles_empty_results(self):
        """Should return empty list when web.results is empty."""
        payload = {"web": {"results": []}}
        results = _process_search_response(payload)
        assert results == []

    def test_handles_missing_web_key(self):
        """Should return empty list when web key is missing."""
        payload = {"other": "data"}
        results = _process_search_response(payload)
        assert results == []

    def test_handles_missing_results_key(self):
        """Should return empty list when results key is missing."""
        payload = {"web": {"other": "data"}}
        results = _process_search_response(payload)
        assert results == []

    def test_handles_non_dict_payload(self):
        """Should return empty list when payload is not a dict."""
        results = _process_search_response("not a dict")
        assert results == []

    def test_handles_non_dict_web(self):
        """Should return empty list when web is not a dict."""
        payload = {"web": "not a dict"}
        results = _process_search_response(payload)
        assert results == []


# =============================================================================
# Tests for _brave_web_search_impl (internal implementation)
# =============================================================================


class TestBraveWebSearchImpl:
    """Tests for the _brave_web_search_impl function."""

    @pytest.mark.asyncio
    async def test_returns_error_when_no_api_key(self, mock_env_no_api_key):
        """Should return error message when API key is not set."""
        result = await _brave_web_search_impl("test query")
        assert "Brave search unavailable" in result
        assert "BRAVE_API_KEY is not set" in result

    @pytest.mark.asyncio
    async def test_successful_search(
        self,
        mock_env_api_key,
        mock_fetch_brave_results,
        sample_brave_response,
        mock_session_usage,
    ):
        """Should successfully perform a search and return formatted results."""
        mock_fetch_brave_results.return_value = sample_brave_response

        result = await _brave_web_search_impl("test query")

        # Verify API was called correctly
        mock_fetch_brave_results.assert_called_once_with("test query", "test-api-key")

        # Verify result formatting
        assert "Brave Search Results:" in result
        assert "Test Result 1" in result
        assert "https://example.com/1" in result
        assert "Test Result 3" in result

        # Verify tool call was recorded
        mock_session_usage.add_tool_call.assert_called_once_with(
            "brave_search_agent", "brave_search", 1
        )

    @pytest.mark.asyncio
    async def test_api_error_handling(
        self, mock_env_api_key, mock_fetch_brave_results, mock_session_usage
    ):
        """Should handle API errors gracefully."""
        mock_fetch_brave_results.side_effect = Exception("Connection error")

        result = await _brave_web_search_impl("test query")

        assert "Brave search failed" in result
        assert "Connection error" in result
        # Tool call should not be recorded on failure
        mock_session_usage.add_tool_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_web_results(
        self, mock_env_api_key, mock_fetch_brave_results, mock_session_usage
    ):
        """Should handle response with empty web results."""
        mock_fetch_brave_results.return_value = {"web": {"results": []}}

        result = await _brave_web_search_impl("test query")

        assert "No Brave results found" in result
        # Tool call should still be recorded even with empty results
        mock_session_usage.add_tool_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_malformed_response(
        self, mock_env_api_key, mock_fetch_brave_results, mock_session_usage
    ):
        """Should handle malformed API responses."""
        mock_fetch_brave_results.return_value = {"not_web": {}}

        result = await _brave_web_search_impl("test query")

        assert "No Brave results found" in result

    @pytest.mark.asyncio
    async def test_rate_limit_enforced(
        self, mock_env_api_key, mock_fetch_brave_results, sample_brave_response
    ):
        """Should enforce rate limiting between consecutive searches."""
        mock_fetch_brave_results.return_value = sample_brave_response

        with mock.patch("brave_search_tool.BRAVE_RATE_LIMIT_SECONDS", 0.3):
            start = asyncio.get_event_loop().time()
            await _brave_web_search_impl("query 1")
            await _brave_web_search_impl("query 2")
            elapsed = asyncio.get_event_loop().time() - start

            assert elapsed >= 0.3  # Should wait at least 0.3 seconds
            assert mock_fetch_brave_results.call_count == 2


# =============================================================================
# Tests for brave_search_agent
# =============================================================================


class TestBraveSearchAgent:
    """Tests for the brave_search_agent configuration."""

    def test_agent_is_agent_instance(self):
        """Should be an instance of Agent."""
        assert isinstance(brave_search_agent, Agent)

    def test_agent_name(self):
        """Should have the correct name."""
        assert brave_search_agent.name == "Brave Search Agent"

    def test_agent_has_instructions(self):
        """Should have instructions set."""
        assert brave_search_agent.instructions == INSTRUCTIONS
        assert "research assistant" in INSTRUCTIONS.lower()
        assert "search the web" in INSTRUCTIONS.lower()

    def test_agent_has_brave_web_search_tool(self):
        """Should have the brave_web_search tool."""
        tool_names = [t.name for t in brave_search_agent.tools]
        assert "brave_web_search" in tool_names

    def test_agent_model_settings(self):
        """Should have tool_choice set to required."""
        assert isinstance(brave_search_agent.model_settings, ModelSettings)
        assert brave_search_agent.model_settings.tool_choice == "required"

    def test_agent_uses_search_model(self):
        """Should use the SEARCH_MODEL from config."""
        from config import SEARCH_MODEL

        assert brave_search_agent.model == SEARCH_MODEL


# =============================================================================
# Integration-style tests
# =============================================================================


class TestBraveSearchIntegration:
    """Integration tests for Brave Search components."""

    @pytest.mark.asyncio
    async def test_full_search_flow(
        self, mock_env_api_key, mock_fetch_brave_results, mock_session_usage
    ):
        """Test the complete search flow from agent tool call to result."""
        mock_fetch_brave_results.return_value = {
            "web": {
                "results": [
                    {
                        "title": "Integration Test",
                        "url": "https://integration.test",
                        "description": "Integration test result",
                    }
                ]
            }
        }

        # Call the internal implementation directly
        result = await _brave_web_search_impl("integration test query")

        # Verify the complete flow
        assert "Integration Test" in result
        assert "https://integration.test" in result
        mock_session_usage.add_tool_call.assert_called_once_with(
            "brave_search_agent", "brave_search", 1
        )

    def test_agent_tool_is_function_tool(self):
        """Verify the agent's tool is a FunctionTool."""
        from agents import FunctionTool

        tool_functions = [
            t for t in brave_search_agent.tools if t.name == "brave_web_search"
        ]
        assert len(tool_functions) == 1
        assert isinstance(tool_functions[0], FunctionTool)


# =============================================================================
# Configuration tests
# =============================================================================


class TestConfiguration:
    """Tests for configuration values related to Brave Search."""

    def test_max_results_constant(self):
        """Should have reasonable MAX_BRAVE_RESULTS value."""
        assert isinstance(MAX_BRAVE_RESULTS, int)
        assert MAX_BRAVE_RESULTS > 0
        assert MAX_BRAVE_RESULTS <= 20  # Reasonable upper limit

    def test_brave_search_url(self):
        """Should use the correct Brave Search API URL."""
        assert BRAVE_SEARCH_URL == "https://api.search.brave.com/res/v1/web/search"

    def test_rate_limit_config_exists(self):
        """Should have BRAVE_RATE_LIMIT_SECONDS in config."""
        from config import BRAVE_RATE_LIMIT_SECONDS

        assert isinstance(BRAVE_RATE_LIMIT_SECONDS, float)
        assert BRAVE_RATE_LIMIT_SECONDS >= 0

    def test_brave_search_cost_in_tool_costs(self):
        """Should have brave_search in TOOL_COSTS."""
        from config import TOOL_COSTS

        assert "brave_search" in TOOL_COSTS


# =============================================================================
# FunctionTool wrapper tests
# =============================================================================


class TestFunctionToolWrapper:
    """Tests for the FunctionTool wrapper behavior."""

    def test_brave_web_search_is_function_tool(self):
        """brave_web_search should be a FunctionTool instance."""
        from agents import FunctionTool

        assert isinstance(brave_web_search, FunctionTool)

    def test_brave_web_search_has_correct_name(self):
        """FunctionTool should have the correct name."""
        assert brave_web_search.name == "brave_web_search"

    def test_brave_web_search_has_description(self):
        """FunctionTool should have a description from docstring."""
        assert brave_web_search.description is not None
        assert "search" in brave_web_search.description.lower()

    def test_internal_impl_is_callable(self):
        """The internal implementation function should be callable."""
        assert callable(_brave_web_search_impl)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
