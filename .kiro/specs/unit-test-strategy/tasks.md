# Implementation Plan: Unit Test Strategy

## Overview

Create 7 new test files under `tests/` covering pure and near-pure logic across
`src/models/domain.py`, `src/core/research_manager.py`, `src/core/usage_tracker.py`,
`src/agents/qa_agent.py`, `src/agents/brave_search_tool.py`,
`src/agents/verification_tools.py`, and `src/export/models.py`.

Each file is self-contained: it defines its own fixtures and Hypothesis strategies.
All property tests use `@settings(max_examples=100)` (project standard).
`ResearchManager` is instantiated with `MagicMock(spec=asyncpg.Pool)` — no refactoring
of production code is required.

## Tasks

- [ ] 1. Create `tests/test_unit_domain.py`
  - [ ] 1.1 Write example tests for `AgentUsage.add_tokens` and `AgentUsage.add_tool_call`
    - Test initial state (`input_tokens == 0`, `output_tokens == 0`)
    - Test single call reflects exact values passed (Requirement 1.2)
    - Test multi-call accumulation (Requirement 1.3)
    - Test zero-call idempotence (Requirement 1.5)
    - Test `add_tool_call` creates new entry with count 1 (Requirement 2.1)
    - Test `add_tool_call` called n times records count n (Requirement 2.2)
    - Test `add_tool_call(tool_name, count=k)` adds k (Requirement 2.3)
    - Test two distinct tool names maintain independent counts (Requirement 2.5)
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 2.1, 2.2, 2.3, 2.5_

  - [ ] 1.2 Write property test for `AgentUsage` token accumulation (Property 1)
    - **Property 1: AgentUsage token accumulation is additive**
    - Strategy: `token_count = st.integers(min_value=0, max_value=10_000_000)`
    - `@given(a, b, c, d)` — call `add_tokens(a, b)` then `add_tokens(c, d)`, assert `input == a+c`, `output == b+d`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 1.4**

  - [ ] 1.3 Write property test for `AgentUsage` tool-call counting (Property 2)
    - **Property 2: AgentUsage tool-call counting is exact**
    - Strategy: `name_str = st.text(min_size=1, max_size=50)`, `positive_int = st.integers(min_value=1, max_value=1000)`
    - `@given(t, n)` — call `add_tool_call(t)` n times, assert `tool_calls[t] == n`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 2.4**

  - [ ] 1.4 Write example tests for `SessionUsage.add_agent_usage` and `add_tool_call`
    - Test new agent creates `AgentUsage` entry (Requirement 3.1)
    - Test existing agent accumulates into existing entry (Requirement 3.2)
    - Test `add_tool_call` increments `total_tool_calls[tool_name]` (Requirement 4.1)
    - Test `add_tool_call` also increments `agents[agent_name].tool_calls[tool_name]` (Requirement 4.2)
    - _Requirements: 3.1, 3.2, 4.1, 4.2_

  - [ ] 1.5 Write property test for `SessionUsage` aggregate totals (Property 3)
    - **Property 3: SessionUsage totals equal sum of per-agent values**
    - Strategy: `st.lists(st.tuples(name_str, token_count, token_count), min_size=0, max_size=20)`
    - `@given(triples)` — apply all via `add_agent_usage`, assert `total_input_tokens == sum(inputs)`, `total_output_tokens == sum(outputs)`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 3.3, 3.4, 3.5**

  - [ ] 1.6 Write property test for `SessionUsage` tool-call aggregation (Property 4)
    - **Property 4: SessionUsage total_tool_calls equals sum across agents**
    - Strategy: `st.lists(st.tuples(name_str, name_str), min_size=0, max_size=30)`
    - `@given(pairs)` — apply all via `add_tool_call`, assert `total_tool_calls[tool_name]` equals sum across per-agent entries
    - `@settings(max_examples=100)`
    - **Validates: Requirements 4.3**

  - [ ] 1.7 Write example tests for `ExtractedClaim` validator
    - Test `highly_controversial` + `importance="low"` coerces to `"medium"` (Requirement 5.1)
    - Test `highly_controversial` + `importance="high"` preserves `"high"` (Requirement 5.2)
    - Test non-`highly_controversial` controversy preserves any importance value (Requirement 5.3)
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ] 1.8 Write property test for `ExtractedClaim` validator (Property 5)
    - **Property 5: ExtractedClaim validator never raises for valid enum combinations**
    - Strategies: `importance_level = st.sampled_from(["critical", "high", "medium", "low"])`, `controversy_level = st.sampled_from([...])`
    - `@given(importance, controversy)` — construct `ExtractedClaim` with all required fields, assert no `ValidationError`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 5.4**

  - [ ] 1.9 Write example tests for `FinalReportData.from_writer_and_verification`
    - Test `short_summary`, `markdown_report`, `follow_up_questions` copied unchanged (Requirement 6.1)
    - Test `total_claims_checked` equals number of claims (Requirement 6.2)
    - Test `dubious_claims_count` equals count of claims below `FACT_CHECK_CONFIDENCE_THRESHOLD` (Requirement 6.3)
    - Test `was_edited=False` is preserved (Requirement 6.4)
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ] 1.10 Write property test for `FinalReportData.dubious_claims_count` (Property 6)
    - **Property 6: FinalReportData dubious_claims_count matches threshold filter**
    - Strategy: `claim_citation = st.builds(SingleClaimCitation, confidence_score=st.integers(min_value=0, max_value=100), ...)`
    - `@given(st.lists(claim_citation, min_size=0, max_size=20))` — assert `dubious_claims_count == len([c for c in claims if c.confidence_score < FACT_CHECK_CONFIDENCE_THRESHOLD])`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 6.5**

- [ ] 2. Checkpoint — run `tests/test_unit_domain.py`
  - Ensure all tests pass, ask the user if questions arise.
  - `python -m pytest tests/test_unit_domain.py -v`

- [ ] 3. Create `tests/test_unit_research_manager.py`
  - [ ] 3.1 Add `manager` fixture using `MagicMock(spec=asyncpg.Pool)`
    - `from unittest.mock import MagicMock` + `import asyncpg`
    - `pool = MagicMock(spec=asyncpg.Pool)` — pool methods raise `AttributeError` if accidentally called
    - _Requirements: 7–12 (shared fixture)_

  - [ ] 3.2 Write example tests for `_normalize_json_payload`
    - Test `None` returns `{}` (Requirement 7.1)
    - Test dict argument returned unchanged (Requirement 7.2)
    - Test valid JSON object string returns parsed dict (Requirement 7.3)
    - Test invalid JSON string returns `{}` (Requirement 7.4)
    - Test valid JSON string decoding to non-dict (list, int) returns `{}` (Requirement 7.5)
    - Test `Mapping` (non-dict) returns plain `dict` equivalent (Requirement 7.6)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [ ] 3.3 Write property test for `_normalize_json_payload` round-trip (Property 7)
    - **Property 7: _normalize_json_payload round-trips valid JSON objects**
    - Strategy: `json_object_dict = st.dictionaries(keys=st.text(min_size=1, max_size=20), values=st.one_of(st.integers(), st.floats(allow_nan=False), st.text(), st.booleans()), max_size=10)`
    - `@given(d)` — serialize to JSON string, pass to `_normalize_json_payload`, assert result equals `json.loads(s)`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 7.7**

  - [ ] 3.4 Write example tests for `_get_search_budget`
    - Test `"no_adaptive"` returns `DEFAULT_NUM_SEARCHES` (Requirement 8.1)
    - Test `"deep_dive"` returns `DEFAULT_NUM_SEARCHES + 3` (Requirement 8.2)
    - Test `"deep_dive_gap_fill"` returns `DEFAULT_NUM_SEARCHES * 2` (Requirement 8.3)
    - _Requirements: 8.1, 8.2, 8.3_

  - [ ] 3.5 Write property test for `_get_search_budget` unknown modes (Property 8)
    - **Property 8: _get_search_budget returns DEFAULT_NUM_SEARCHES for unknown modes**
    - Strategy: `unknown_mode = st.text().filter(lambda s: s not in {"deep_dive", "deep_dive_gap_fill"})`
    - `@given(mode)` — assert `_get_search_budget(mode) == DEFAULT_NUM_SEARCHES`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 8.4**

  - [ ] 3.6 Write example tests for `_compute_brave_flags`
    - Test `cost_effective_search=False` returns all `False` (Requirement 9.1)
    - Test `cost_effective_search=True`, `phase="initial"`, `search_mode="no_adaptive"` returns all `True` (Requirement 9.2)
    - Test `cost_effective_search=True`, `phase="deep_dive"` returns `ceil(n/2)` `True` then `False` (Requirement 9.3)
    - Test `cost_effective_search=True`, `phase="gap_fill"` returns `ceil(n/2)` `True` then `False` (Requirement 9.4)
    - Test `cost_effective_search=True`, `phase="initial"`, `search_mode` not `"no_adaptive"` returns all `True` (Requirement 9.5)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ] 3.7 Write property test for `_compute_brave_flags` length invariant (Property 9)
    - **Property 9: _compute_brave_flags length equals input length**
    - Strategy: `search_list = st.lists(st.builds(WebSearchItem, query=st.text(min_size=1, max_size=50), reason=st.text(min_size=1, max_size=50)), min_size=0, max_size=20)`
    - `@given(searches, phase, cost_effective_search, search_mode)` — assert `len(_compute_brave_flags(searches, phase)) == len(searches)`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 9.6**

  - [ ] 3.8 Write example tests for `calculate_total_cost`
    - Test empty `session_usage` returns `0.0` (Requirement 10.1)
    - Test known agent with known token counts returns expected cost from `MODEL_COSTS` (Requirement 10.2)
    - Test tool calls add `TOOL_COSTS[tool_name] * count` (Requirement 10.3)
    - Test unknown agent name (not in `AGENT_MODEL_MAP`) is skipped without exception (Requirement 10.4)
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ] 3.9 Write property test for `calculate_total_cost` non-negativity (Property 10)
    - **Property 10: calculate_total_cost is non-negative for all valid inputs**
    - Strategy: `non_neg_tokens = st.integers(min_value=0, max_value=10_000_000)`; build `SessionUsage` with arbitrary known-agent token counts
    - `@given(...)` — assert `calculate_total_cost() >= 0.0`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 10.5**

  - [ ] 3.10 Write example tests for `_format_cost_summary_from_snapshot`
    - Test `None` returns string containing `"No cost data available"` (Requirement 11.1)
    - Test empty dict `{}` returns string containing `"No cost data available"` (Requirement 11.2)
    - Test valid snapshot dict includes all four values (Requirement 11.3)
    - Test `total_cost` is formatted to 4 decimal places (Requirement 11.4)
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [ ] 3.11 Write example tests for `reset_session_state`
    - Populate all fields, call `reset_session_state()`, assert each field is reset:
      `report=None`, `search_results=[]`, `last_query=None`, fresh `SessionUsage()`,
      `current_session_id=None`, `cost=0.0`, `input_tokens=0`, `output_tokens=0`,
      `search_mode=SEARCH_MODE_DEFAULT`
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

- [ ] 4. Checkpoint — run `tests/test_unit_research_manager.py`
  - Ensure all tests pass, ask the user if questions arise.
  - `python -m pytest tests/test_unit_research_manager.py -v`

- [ ] 5. Create `tests/test_unit_usage_tracker.py`
  - [ ] 5.1 Add `autouse` fixture to reset `ContextVar` before and after each test
    - Call `set_session_usage(None)` in setup and teardown to prevent cross-test contamination
    - _Requirements: 13 (shared fixture)_

  - [ ] 5.2 Write example tests for `set_session_usage` / `get_session_usage`
    - Test round-trip: `set_session_usage(su)` then `get_session_usage()` returns same object (Requirement 13.1)
    - Test `set_session_usage(None)` makes `get_session_usage()` return `None` (Requirement 13.2)
    - _Requirements: 13.1, 13.2_

  - [ ] 5.3 Write example tests for `record_agent_usage` and `record_tool_call`
    - Test `record_agent_usage` with bound session delegates to `session_usage.add_agent_usage` (Requirement 13.3)
    - Test `record_agent_usage` with no bound session returns without raising (Requirement 13.4)
    - Test `record_tool_call` with bound session delegates to `session_usage.add_tool_call` (Requirement 13.5)
    - Test `record_tool_call` with no bound session returns without raising (Requirement 13.6)
    - _Requirements: 13.3, 13.4, 13.5, 13.6_

- [ ] 6. Checkpoint — run `tests/test_unit_usage_tracker.py`
  - Ensure all tests pass, ask the user if questions arise.
  - `python -m pytest tests/test_unit_usage_tracker.py -v`

- [ ] 7. Create `tests/test_unit_qa_agent.py`
  - [ ] 7.1 Write example tests for `is_quality_request`
    - Test `"/quality"` returns `True` (Requirement 14.1)
    - Test `"/bias"` returns `True` (Requirement 14.2)
    - Test message containing `"run bias analysis"` returns `True` (Requirement 14.3)
    - Test message containing `"quality check"` returns `True` (Requirement 14.3)
    - Test non-matching message returns `False` (Requirement 14.4)
    - Test `"  /quality  "` (leading/trailing whitespace) returns `True` (Requirement 14.5)
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

  - [ ] 7.2 Write property test for `is_quality_request` non-matching strings (Property 14)
    - **Property 14: is_quality_request returns False for non-matching strings**
    - Strategy: `ALL_KNOWN = QUALITY_COMMANDS | QUALITY_TRIGGER_PHRASES`; `non_quality_str = st.text().filter(lambda s: not any(phrase in s.strip().lower() for phrase in ALL_KNOWN) and s.strip().lower() not in ALL_KNOWN)`
    - `@given(s)` — assert `is_quality_request(s) == False`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 14.6**

- [ ] 8. Checkpoint — run `tests/test_unit_qa_agent.py`
  - Ensure all tests pass, ask the user if questions arise.
  - `python -m pytest tests/test_unit_qa_agent.py -v`

- [ ] 9. Create `tests/test_unit_brave_search_tool.py`
  - [ ] 9.1 Write example tests for `_format_brave_results`
    - Test empty list returns `"No Brave results found."` (Requirement 15.1)
    - Test list with more than `MAX_BRAVE_RESULTS` items includes at most `MAX_BRAVE_RESULTS` results (Requirement 15.3)
    - Test result missing `"title"` key substitutes `"Untitled"` (Requirement 15.4)
    - _Requirements: 15.1, 15.3, 15.4_

  - [ ] 9.2 Write property test for `_format_brave_results` field inclusion (Property 15)
    - **Property 15: _format_brave_results includes all fields for each result**
    - Strategy: `brave_result = st.fixed_dictionaries({"title": st.text(min_size=1, max_size=100), "url": st.text(min_size=1, max_size=200), "description": st.text(min_size=0, max_size=300)})`; `result_list = st.lists(brave_result, min_size=1, max_size=MAX_BRAVE_RESULTS)`
    - `@given(results)` — assert each result's title, url, and description appear in the returned string
    - `@settings(max_examples=100)`
    - **Validates: Requirements 15.2**

  - [ ] 9.3 Write example tests for `_process_search_response`
    - Test valid API response dict returns `payload["web"]["results"]` (Requirement 15.5)
    - Test dict missing `"web"` key returns `[]` (Requirement 15.6)
    - Test non-dict value returns `[]` (Requirement 15.7)
    - _Requirements: 15.5, 15.6, 15.7_

- [ ] 10. Checkpoint — run `tests/test_unit_brave_search_tool.py`
  - Ensure all tests pass, ask the user if questions arise.
  - `python -m pytest tests/test_unit_brave_search_tool.py -v`

- [ ] 11. Create `tests/test_unit_verification_tools.py`
  - [ ] 11.1 Write example tests for `parse_verification_result`
    - Test dict containing `"verified_claims"` returns a list of `SingleClaimCitation` objects (Requirement 16.1)
    - Test dict without `"verified_claims"` returns a single `SingleClaimCitation` object (Requirement 16.2)
    - Test group result with n claims returns list of length n (Requirement 16.3)
    - _Requirements: 16.1, 16.2, 16.3_

- [ ] 12. Checkpoint — run `tests/test_unit_verification_tools.py`
  - Ensure all tests pass, ask the user if questions arise.
  - `python -m pytest tests/test_unit_verification_tools.py -v`

- [ ] 13. Create `tests/test_unit_export_models.py`
  - [ ] 13.1 Write example tests for `MetadataHeader.derive_title`
    - Test non-empty header returns header unchanged (Requirement 17.1)
    - Test `None` header with prompt ≤ 120 chars returns prompt unchanged (Requirement 17.2)
    - Test `None` header with prompt > 120 chars returns first 120 chars + `"…"` (Requirement 17.3)
    - _Requirements: 17.1, 17.2, 17.3_

  - [ ] 13.2 Write property test for `derive_title` with non-empty header (Property 11)
    - **Property 11: derive_title returns header unchanged for any non-empty header**
    - Strategy: `non_empty_str = st.text(min_size=1, max_size=300)`
    - `@given(h, initial_prompt)` — assert `MetadataHeader.derive_title(h, initial_prompt) == h`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 17.4**

  - [ ] 13.3 Write property test for `derive_title` with short prompts (Property 12)
    - **Property 12: derive_title returns prompt unchanged for short prompts**
    - Strategy: `short_str = st.text(min_size=0, max_size=120)`
    - `@given(s)` — assert `MetadataHeader.derive_title(None, s) == s`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 17.5**

  - [ ] 13.4 Write example tests for `ExportResult.filename_for`
    - Test `ExportFormat.markdown` returns string ending in `".md"` (Requirement 17.6)
    - Test `ExportFormat.pdf` returns string ending in `".pdf"` (Requirement 17.7)
    - Test `ExportFormat.docx` returns string ending in `".docx"` (Requirement 17.8)
    - _Requirements: 17.6, 17.7, 17.8_

  - [ ] 13.5 Write property test for `filename_for` session_id inclusion (Property 13)
    - **Property 13: filename_for always contains the session_id**
    - Strategy: `uuid_str = st.uuids().map(str)`, `export_fmt = st.sampled_from(list(ExportFormat))`
    - `@given(session_id, fmt)` — assert `session_id in ExportResult.filename_for(session_id, fmt)`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 17.9**

- [ ] 14. Checkpoint — run `tests/test_unit_export_models.py`
  - Ensure all tests pass, ask the user if questions arise.
  - `python -m pytest tests/test_unit_export_models.py -v`

- [ ] 15. Final checkpoint — run the full new test suite
  - Run all 7 new test files together and confirm all pass:
    ```
    python -m pytest tests/test_unit_domain.py tests/test_unit_research_manager.py \
        tests/test_unit_usage_tracker.py tests/test_unit_qa_agent.py \
        tests/test_unit_brave_search_tool.py tests/test_unit_verification_tools.py \
        tests/test_unit_export_models.py -v
    ```
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- All property tests use `@settings(max_examples=100)` — project standard
- Property test docstrings follow the convention: `# Feature: unit-test-strategy, Property N: <text>`
- `ResearchManager` is instantiated with `MagicMock(spec=asyncpg.Pool)` — no production code changes needed
- `usage_tracker` ContextVar is reset before and after each test via an `autouse` fixture
- No `conftest.py` additions needed — all fixtures are local to each test file
