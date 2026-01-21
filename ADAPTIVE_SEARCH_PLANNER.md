# Adaptive Search Planner Plan

## Goals
- Provide selectable search depth for initial report generation.
- Support three modes: No Adaptive, Deep Dive, Deep Dive + Gap-Filling.
- Persist mode per session for reload and continuity.

## Implementation Stages

### 1) Search mode config + persistence
- Add search mode constants and default in `config.py`.
- Add `search_mode` column to `sessions` table via `ALTER TABLE` in `init_db()`.
- Store `search_mode` on session creation and load it on session reload.
- **Test:** create a session with `search_mode` and query it back.

### 2) Adaptive planning models + agent
- Add Pydantic models for multi-phase search planning (`SearchPhasePlan`, `AdaptiveSearchPlan`).
- Create `adaptive_search_planner.py` agent to select deep-dive topics and gap-fill items.
- Enforce hard total budget per mode (standard, standard+3, standard*2).
- **Test:** call the planner with mock inputs and assert total searches ≤ budget.

### 3) ResearchManager orchestration
- Update `run()` to accept `search_mode` and pass it to planning.
- Execute initial search plan; optionally run adaptive phase(s) based on mode.
- Merge search results, update usage, and continue report pipeline unchanged.
- **Test:** ensure search counts match mode caps in a dry-run script.

### 4) UI selection (dropdown)
- Add a dropdown in the UI for search mode with default “No Adaptive”.
- Pass selected mode into `run()` and persist to the session.
- Load stored mode when selecting previous sessions.
- **Test:** create a session, reload it, verify dropdown reflects stored value.

### 5) Validation
- Run `ruff check .`.
- Optional: run a short DB script to confirm mode persistence.
