# Design Document: Unit Test Strategy

## Overview

This document defines the design for the unit test suite covering the project's core
pure and near-pure logic. The goal is to establish a consistent, maintainable test
structure that gives high confidence in the correctness of domain models, orchestration
helpers, and utility functions — without touching external services (database, LLM APIs,
HTTP).

The suite uses **pytest** as the test runner, **Hypothesis** for property-based tests,
and **pytest-asyncio** for async methods. All tests live under `tests/` and follow the
naming and fixture conventions already established in the project.

### Scope

| Module | Functions / Methods Under Test |
|---|---|
| `src/models/domain.py` | `AgentUsage.add_tokens`, `AgentUsage.add_tool_call`, `SessionUsage.add_agent_usage`, `SessionUsage.add_tool_call`, `ExtractedClaim` validator, `FinalReportData.from_writer_and_verification` |
| `src/core/research_manager.py` | `_normalize_json_payload`, `_get_search_budget`, `_compute_brave_flags`, `calculate_total_cost`, `_format_cost_summary_from_snapshot`, `reset_session_state` |
| `src/core/usage_tracker.py` | `set_session_usage`, `get_session_usage`, `record_agent_usage`, `record_tool_call` |
| `src/agents/qa_agent.py` | `is_quality_request` |
| `src/agents/brave_search_tool.py` | `_format_brave_results`, `_process_search_response` |
| `src/agents/verification_tools.py` | `parse_verification_result` |
| `src/export/models.py` | `MetadataHeader.derive_title`, `ExportResult.filename_for` |

### Out of Scope

- Any method that calls `Runner.run(...)` (LLM API)
- Any method that calls `asyncpg` (database)
- Any method that calls `httpx` or other HTTP clients
- `src/models/api.py` (already covered by `test_property_dto_validation.py`)
- `src/export/` renderers (already covered by `test_property_export_renderers.py`)

---

## Architecture

The test suite is purely additive — no production code is modified. The architecture
follows the existing project conventions:

```
tests/
├── __init__.py                        (already exists)
├── test_unit_domain.py                (NEW — Requirements 1–6)
├── test_unit_research_manager.py      (NEW — Requirements 7–12)
├── test_unit_usage_tracker.py         (NEW — Requirement 13)
├── test_unit_qa_agent.py              (NEW — Requirement 14)
├── test_unit_brave_search_tool.py     (NEW — Requirement 15)
├── test_unit_verification_tools.py    (NEW — Requirement 16)
└── test_unit_export_models.py         (NEW — Requirement 17)
```

One test file per module under test. This mirrors the existing pattern
(`test_unit_export_router.py`, `test_unit_export_service.py`, etc.).

---

## Components and Interfaces

### ResearchManager Instantiation

`ResearchManager.__init__` requires an `asyncpg.Pool`. For pure method tests, the pool
is never called, so a `MagicMock()` is sufficient:

```python
from unittest.mock import MagicMock
import asyncpg
from src.core.research_manager import ResearchManager

@pytest.fixture
def manager() -> ResearchManager:
    pool = MagicMock(spec=asyncpg.Pool)
    return ResearchManager(pool)
```

This fixture is defined once per test file that needs it (no shared conftest needed
given the small number of files).

### Async Method Handling

`usage_tracker` functions are synchronous. `ResearchManager` methods under test are
also synchronous. No `pytest-asyncio` is needed for this suite. If a future requirement
adds async methods, the existing `@pytest.mark.asyncio` pattern from
`test_api_integration.py` applies.

### Hypothesis Configuration

All property tests use `@settings(max_examples=100)` to match the project convention
established in `test_property_export_renderers.py` and `test_property_dto_validation.py`.

---

## Data Models

### Hypothesis Strategies

The following strategies are defined locally in each test file (not in a shared module,
to keep each file self-contained and readable):

**`test_unit_domain.py`**

```python
# Non-negative integers for token counts
token_count = st.integers(min_value=0, max_value=10_000_000)

# Positive integers for tool call counts
positive_int = st.integers(min_value=1, max_value=1000)

# Non-empty strings for tool/agent names
name_str = st.text(min_size=1, max_size=50)

# Valid ExtractedClaim field values
importance_level = st.sampled_from(["critical", "high", "medium", "low"])
controversy_level = st.sampled_from([
    "uncontroversial", "somewhat_controversial", "highly_controversial"
])

# SingleClaimCitation with random confidence scores (for FinalReportData tests)
claim_citation = st.builds(
    SingleClaimCitation,
    claim=st.text(min_size=1, max_size=100),
    confidence_score=st.integers(min_value=0, max_value=100),
    is_verified=st.booleans(),
    verification_strategy=st.just("quick"),
    supporting_citations=st.just([]),
    contradicting_citations=st.just([]),
    confidence_rationale=st.just("test"),
    search_queries_used=st.just([]),
)
```

**`test_unit_research_manager.py`**

```python
# Valid JSON object dicts (serialised to string for round-trip test)
json_object_dict = st.dictionaries(
    keys=st.text(min_size=1, max_size=20),
    values=st.one_of(st.integers(), st.floats(allow_nan=False), st.text(), st.booleans()),
    max_size=10,
)

# Unrecognised search mode strings
unknown_mode = st.text().filter(
    lambda s: s not in {"deep_dive", "deep_dive_gap_fill"}
)

# WebSearchItem list for _compute_brave_flags
web_search_item = st.builds(
    WebSearchItem,
    query=st.text(min_size=1, max_size=50),
    reason=st.text(min_size=1, max_size=50),
)
search_list = st.lists(web_search_item, min_size=0, max_size=20)

# Non-negative token counts for calculate_total_cost
non_neg_tokens = st.integers(min_value=0, max_value=10_000_000)
```

**`test_unit_qa_agent.py`**

```python
# Strings that contain none of the known commands or trigger phrases
ALL_KNOWN = QUALITY_COMMANDS | QUALITY_TRIGGER_PHRASES

non_quality_str = st.text().filter(
    lambda s: not any(phrase in s.strip().lower() for phrase in ALL_KNOWN)
               and s.strip().lower() not in ALL_KNOWN
)
```

**`test_unit_brave_search_tool.py`**

```python
# Result dicts with all required fields present
brave_result = st.fixed_dictionaries({
    "title": st.text(min_size=1, max_size=100),
    "url": st.text(min_size=1, max_size=200),
    "description": st.text(min_size=0, max_size=300),
})
result_list = st.lists(brave_result, min_size=1, max_size=MAX_BRAVE_RESULTS)
```

**`test_unit_export_models.py`**

```python
# Non-empty strings for derive_title header property
non_empty_str = st.text(min_size=1, max_size=300)

# Short strings (<=120 chars) for derive_title prompt property
short_str = st.text(min_size=0, max_size=120)

# UUID strings for filename_for property
uuid_str = st.uuids().map(str)

# All ExportFormat values
export_fmt = st.sampled_from(list(ExportFormat))
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid
executions of a system — essentially, a formal statement about what the system should
do. Properties serve as the bridge between human-readable specifications and
machine-verifiable correctness guarantees.*

### Property Reflection

Before listing properties, redundancy is eliminated:

- Requirements 3.3 and 3.4 (total_input_tokens invariant, total_output_tokens invariant)
  are both covered by Requirement 3.5 (the general sequence property). One property test
  covers all three.
- Requirements 17.1–17.3 (derive_title examples) are subsumed by Properties 10 and 11.
  Only the truncation edge case (>120 chars) needs a standalone example test.
- Requirements 1.3, 1.5 (multi-call accumulation, zero idempotence) are subsumed by
  Property 1 — Hypothesis will generate those inputs naturally.

---

### Property 1: AgentUsage token accumulation is additive

*For any* two pairs of non-negative integers `(a, b)` and `(c, d)`, calling
`add_tokens(a, b)` then `add_tokens(c, d)` on a fresh `AgentUsage` SHALL produce
`input_tokens == a + c` and `output_tokens == b + d`.

**Validates: Requirements 1.4**

---

### Property 2: AgentUsage tool-call counting is exact

*For any* non-empty string `t` and positive integer `n`, calling `add_tool_call(t)`
exactly `n` times on a fresh `AgentUsage` SHALL produce `tool_calls[t] == n`.

**Validates: Requirements 2.4**

---

### Property 3: SessionUsage totals equal sum of per-agent values

*For any* sequence of `(agent_name, input_tokens, output_tokens)` triples applied via
`add_agent_usage`, the `SessionUsage` `total_input_tokens` SHALL equal the sum of all
input values and `total_output_tokens` SHALL equal the sum of all output values.

**Validates: Requirements 3.3, 3.4, 3.5**

---

### Property 4: SessionUsage total_tool_calls equals sum across agents

*For any* sequence of `(agent_name, tool_name)` pairs applied via `add_tool_call`, the
`SessionUsage` `total_tool_calls[tool_name]` SHALL equal the sum of that tool's count
across all per-agent `AgentUsage` entries.

**Validates: Requirements 4.3**

---

### Property 5: ExtractedClaim validator never raises for valid enum combinations

*For any* valid `ImportanceLevel` and `ControversyLevel` value, constructing an
`ExtractedClaim` with those values SHALL succeed without raising a `ValidationError`.

**Validates: Requirements 5.4**

---

### Property 6: FinalReportData dubious_claims_count matches threshold filter

*For any* list of `SingleClaimCitation` objects with arbitrary `confidence_score` values
(0–100), `FinalReportData.from_writer_and_verification` SHALL produce a
`dubious_claims_count` equal to
`len([c for c in claims if c.confidence_score < FACT_CHECK_CONFIDENCE_THRESHOLD])`.

**Validates: Requirements 6.5**

---

### Property 7: _normalize_json_payload round-trips valid JSON objects

*For any* dict serialisable to a JSON object string, passing that JSON string to
`_normalize_json_payload` SHALL return a dict equal to `json.loads(s)`.

**Validates: Requirements 7.7**

---

### Property 8: _get_search_budget returns DEFAULT_NUM_SEARCHES for unknown modes

*For any* string that is not `"deep_dive"` or `"deep_dive_gap_fill"`,
`_get_search_budget` SHALL return `DEFAULT_NUM_SEARCHES`.

**Validates: Requirements 8.4**

---

### Property 9: _compute_brave_flags length equals input length

*For any* list of `WebSearchItem` objects, any phase string, and any combination of
`cost_effective_search` and `search_mode` settings, the list returned by
`_compute_brave_flags` SHALL have the same length as the input list.

**Validates: Requirements 9.6**

---

### Property 10: calculate_total_cost is non-negative for all valid inputs

*For any* combination of non-negative token counts for known agents and non-negative
tool-call counts, `calculate_total_cost` SHALL return a value `>= 0.0`.

**Validates: Requirements 10.5**

---

### Property 11: derive_title returns header unchanged for any non-empty header

*For any* non-empty string `h` and any `initial_prompt`, `MetadataHeader.derive_title(h,
initial_prompt)` SHALL return `h` unchanged.

**Validates: Requirements 17.4**

---

### Property 12: derive_title returns prompt unchanged for short prompts

*For any* string `s` of length ≤ 120, `MetadataHeader.derive_title(None, s)` SHALL
return `s` unchanged.

**Validates: Requirements 17.5**

---

### Property 13: filename_for always contains the session_id

*For any* session ID string and any `ExportFormat` value, `ExportResult.filename_for`
SHALL return a string that contains the session ID as a substring.

**Validates: Requirements 17.9**

---

### Property 14: is_quality_request returns False for non-matching strings

*For any* string that does not contain any known quality command or trigger phrase,
`is_quality_request` SHALL return `False`.

**Validates: Requirements 14.6**

---

### Property 15: _format_brave_results includes all fields for each result

*For any* non-empty list of result dicts (up to `MAX_BRAVE_RESULTS`) each containing
`title`, `url`, and `description`, `_format_brave_results` SHALL include each result's
title, URL, and description in the returned string.

**Validates: Requirements 15.2**

---

## Error Handling

### Hypothesis Shrinking

Hypothesis automatically shrinks failing examples to minimal counterexamples. No
additional error handling is needed in the tests themselves.

### ResearchManager with MagicMock Pool

The `MagicMock(spec=asyncpg.Pool)` pool will raise `AttributeError` if any pool method
is accidentally called during a pure method test. This is intentional — it acts as a
guard against accidentally testing methods that touch the database.

### ContextVar Isolation

`usage_tracker` uses a module-level `ContextVar`. Tests that call `set_session_usage`
must reset it after the test to avoid cross-test contamination. Each test that sets the
ContextVar should call `set_session_usage(None)` in a `finally` block or use a pytest
fixture with teardown.

### ExtractedClaim Construction

`ExtractedClaim` has several required fields with constraints (`min_length`, `max_length`
on strings, Literal types for enums). The Hypothesis strategy must supply all required
fields with valid values to avoid `ValidationError` from unrelated constraints.

---

## Testing Strategy

### Dual Testing Approach

Each requirement is covered by a combination of:

- **Example tests** (`test_*` functions with concrete inputs): verify specific known
  behaviours, edge cases, and error conditions.
- **Property tests** (`@given` + `@settings(max_examples=100)`): verify universal
  invariants across a wide input space.

### Test Naming Convention

```
test_<requirement_area>_<behaviour>
```

Examples:
- `test_agent_usage_add_tokens_accumulates` (example)
- `test_property_agent_usage_token_accumulation_additive` (property)
- `test_normalize_json_payload_returns_empty_for_none` (example)
- `test_property_normalize_json_payload_round_trips_valid_json` (property)

Property tests are prefixed with `test_property_` to make them visually distinct and
consistent with the existing `test_property_*.py` file naming convention.

### Fixtures

Each test file defines its own fixtures locally. No shared `conftest.py` additions are
needed. The primary fixture pattern:

```python
@pytest.fixture
def manager() -> ResearchManager:
    """ResearchManager with a MagicMock pool for pure method tests."""
    return ResearchManager(MagicMock(spec=asyncpg.Pool))
```

For `usage_tracker` tests, a fixture handles ContextVar cleanup:

```python
@pytest.fixture(autouse=True)
def reset_context_var():
    """Ensure ContextVar is cleared before and after each test."""
    set_session_usage(None)
    yield
    set_session_usage(None)
```

### Async Methods

None of the methods in scope are async. `pytest-asyncio` is not needed for this suite.

### Property-Based Testing Library

**Hypothesis** is used (already installed). Each property test:
- Uses `@given(...)` with strategies defined at the top of the file
- Uses `@settings(max_examples=100)` (project standard)
- Includes a docstring comment referencing the design property:
  `# Feature: unit-test-strategy, Property N: <property_text>`

### Coverage Targets

- All 17 requirements must have at least one passing test.
- All 15 correctness properties must have a corresponding `@given` test.
- No coverage target is set for lines/branches — the goal is behavioural correctness,
  not line coverage.

### What Is Explicitly Not Tested

- Methods calling `Runner.run(...)` — would require LLM API access
- Methods calling `asyncpg` pool methods — would require a live database
- Methods calling `httpx` — would require HTTP access
- `_enforce_brave_rate_limit` — depends on `asyncio.sleep` and wall-clock time
- `_fetch_brave_results` — makes HTTP calls
- `send_email`, `write_report`, `plan_searches`, `perform_searches` — all call external
  services
- `run()` and `chat()` generator methods — orchestration, not pure logic

### Running the Tests

```bash
# Run all new unit tests
python -m pytest tests/test_unit_domain.py tests/test_unit_research_manager.py \
    tests/test_unit_usage_tracker.py tests/test_unit_qa_agent.py \
    tests/test_unit_brave_search_tool.py tests/test_unit_verification_tools.py \
    tests/test_unit_export_models.py -v

# Run a single file
python -m pytest tests/test_unit_domain.py -v

# Run only property tests
python -m pytest tests/ -k "property" -v
```
