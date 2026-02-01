import asyncio
import os
import time

import httpx
from agents import function_tool

from config import BRAVE_RATE_LIMIT_SECONDS
from usage_tracker import record_tool_call

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
MAX_BRAVE_RESULTS = 5

_brave_rate_lock = asyncio.Lock()
_last_brave_call_at = 0.0


def _get_brave_api_key() -> str | None:
    return os.getenv("BRAVE_API_KEY")


async def _enforce_brave_rate_limit() -> None:
    global _last_brave_call_at
    async with _brave_rate_lock:
        now = time.monotonic()
        elapsed = now - _last_brave_call_at
        if elapsed < BRAVE_RATE_LIMIT_SECONDS:
            await asyncio.sleep(BRAVE_RATE_LIMIT_SECONDS - elapsed)
        _last_brave_call_at = time.monotonic()


def _format_brave_results(results: list[dict]) -> str:
    if not results:
        return "No Brave results found."
    lines = ["Brave Search Results:"]
    for result in results[:MAX_BRAVE_RESULTS]:
        title = result.get("title") or "Untitled"
        url = result.get("url") or result.get("link") or ""
        description = result.get("description") or result.get("snippet") or ""
        lines.append(f"- {title}\n  URL: {url}\n  Summary: {description}")
    return "\n".join(lines)


async def _fetch_brave_results(query: str, api_key: str) -> dict:
    """Fetch raw results from Brave Search API.

    This is a separate function to allow for easier testing.
    """
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key,
    }
    params = {
        "q": query,
        "count": MAX_BRAVE_RESULTS,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(BRAVE_SEARCH_URL, params=params, headers=headers)
        response.raise_for_status()
        return response.json()


def _process_search_response(payload: dict) -> list[dict]:
    """Extract search results from API response."""
    web = payload.get("web", {}) if isinstance(payload, dict) else {}
    return web.get("results", []) if isinstance(web, dict) else []


async def _brave_web_search_impl(query: str) -> str:
    """Internal implementation of Brave web search."""
    api_key = _get_brave_api_key()
    if not api_key:
        return "Brave search unavailable: BRAVE_API_KEY is not set."

    await _enforce_brave_rate_limit()

    try:
        payload = await _fetch_brave_results(query, api_key)
    except Exception as exc:
        return f"Brave search failed: {exc}"

    results = _process_search_response(payload)
    record_tool_call("brave_search_agent", "brave_search")
    return _format_brave_results(results)


@function_tool
async def brave_web_search(query: str) -> str:
    """Search the web using Brave Search API."""
    return await _brave_web_search_impl(query)
