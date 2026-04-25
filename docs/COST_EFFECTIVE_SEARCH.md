# Cost-Effective Search Implementation Plan

## Goals

- Add a Brave Search tool with configurable throttling and cost tracking.
- Route search queries between Brave and OpenAI WebSearch based on a UI toggle.
- Persist search mode and cost-effective toggle in session storage.
- Make Brave per-search cost configurable for future paid tiers.

## Planned Changes

### 1) Configuration

- Add `BRAVE_RATE_LIMIT_SECONDS` (default: `1.0`).
- Add `BRAVE_SEARCH_COST` (default: `0.0`).
- Extend `TOOL_COSTS` to include `brave_search`.

### 2) Brave Search Tool

- Create a new module (e.g., `brave_search_tool.py`) with a `function_tool` that:
  - Calls Brave Search API using `BRAVE_API_KEY`.
  - Applies an async throttle to enforce the rate limit.
  - Returns concise, structured summaries for the agent.
  - Records tool usage as `brave_search`.

### 3) Hybrid Search Routing

- Add a routing layer (in `research_manager.py` or a new `hybrid_search_manager.py`) that:
  - Uses OpenAI WebSearch when the toggle is OFF.
  - When ON:
    - `no_adaptive` mode: all initial searches via Brave.
    - `deep_dive` and `gap_fill` phases: 50/50 split with rounding (ceil Brave, floor OpenAI).
- Ensure routing integrates with existing search agent usage tracking.

### 4) UI + Session State

- Add a “Cost-Effective Search” toggle next to the search mode dropdown.
- Pass the toggle value into `ResearchManager.run`.
- Persist the toggle state in the `sessions` table and restore it on load.

### 5) Cost Tracking

- Track Brave tool calls using `record_tool_call` with `brave_search`.
- Make Brave per-search cost configurable via `BRAVE_SEARCH_COST`.

### 6) Validation

- Manual smoke check with a single run in each search mode.
- Confirm tool call counts and total cost changes when Brave is used.
