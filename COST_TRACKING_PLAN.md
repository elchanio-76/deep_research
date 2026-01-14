# COST_TRACKING_PLAN.md

## Goal
Introduce structured, per-session usage tracking with a `SessionUsage` model, per-agent token counts, per-tool call counts, and a cost lookup using hardcoded model/tool rates. Expose a UI field showing the current totals.

## Scope
- Add `SessionUsage` and `AgentUsage` to `new_models.py`.
- Add model/tool costs to `config.py` (already present: `MODEL_COSTS`, `TOOL_COSTS`).
- Track usage across all agents and web search tool calls.
- Provide a UI markdown/text field for cost summary.

## Plan
1. **Define usage models**
   - Add `AgentUsage` with `input_tokens`, `output_tokens`, and `tool_calls` dict.
   - Add `SessionUsage` with per-agent map plus total token and tool call aggregates.
   - Provide helper methods to increment agent usage and tool call counts.

2. **Add a usage tracker hook**
   - Use a lightweight module (contextvar-based) to hold the active `SessionUsage`.
   - Expose `set_session_usage`, `get_session_usage`, `record_agent_usage`, `record_tool_call`.

3. **Initialize session usage per run**
   - In `ResearchManager.run`, initialize `SessionUsage` at the start of the run.
   - Ensure the tracker points at the current session for `run` and `chat`.

4. **Track agent token usage everywhere**
   - Update `ResearchManager.update_usage_stats` to accept `agent_name` and record usage.
   - Call it for all `Runner.run(...)` calls in the pipeline.
   - In verification and quality tools, use `record_agent_usage` after `Runner.run`.

5. **Track tool call usage (WebSearchTool)**
   - Increment `tool_calls["web_search"]` when WebSearchTool is used.
   - Locations: `ResearchManager.search`, `quality_web_search`, verification tools.

6. **Compute total cost from costs lookup**
   - Add a helper in `ResearchManager` to compute total cost using:
     - `MODEL_COSTS` per 1M tokens
     - `TOOL_COSTS` per tool call
   - Return totals (no per-agent breakdown in output).

7. **Expose cost summary in UI**
   - Add a text/markdown output field for cost info.
   - Include: total input tokens, total output tokens, total tool calls, total running cost.
   - Update after `run` completes and via a simple refresh action for chat.

8. **Validation**
   - Run `ruff check .` to ensure lint consistency.
   - Spot-check that WebSearch calls increment tool usage.
