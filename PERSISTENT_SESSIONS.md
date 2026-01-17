# Persistent Sessions Plan

## Goals
- Persist report and chat interactions to Postgres for future retrieval.
- Add session summaries and history selection to the UI.
- Keep usage and cost snapshots with each session.

## Implementation Stages

### 1) Database configuration + bootstrap
- Add `DATABASE_URL` to `.env` configuration and read it in the app.
- Create `db.py` to manage an asyncpg connection pool.
- Provide `init_db()` and `close_pool()` helpers for lifecycle.
- Add small config defaults for pool sizing in `config.py`.
- Update `README.md` with `DATABASE_URL` example.
- **Autonomous check:** run a quick `python -c` to ensure pool connects.

### 2) Schema for sessions + messages + usage
- `sessions` table: `id` (uuid), `header`, `initial_prompt`, `report_markdown`, timestamps, `usage_jsonb`, `cost_summary_jsonb`.
- `messages` table: `id` (uuid), `session_id` (fk), `role`, `content`, `message_type`, `agent_name`, `usage_jsonb`, `created_at`.
- Add `init_db()` to execute `CREATE TABLE IF NOT EXISTS` statements.
- **Autonomous check:** insert a session + message, read them back.

### 3) Persisting sessions/messages in ResearchManager
- Track `current_session_id` and a `session_active` flag.
- On `run(query)`: create a session and insert the initial user prompt.
- After report generation: store the report as an assistant message and update session fields.
- On `chat(...)`: persist each user/assistant message pair.
- Update usage + cost snapshots as part of each session update.
- **Autonomous check:** run a short script that creates a session and validates stored messages.

### 4) Session header generation
- Add a small title-summary agent to generate a one-sentence header.
- Run after the first report response and update the session header.
- **Autonomous check:** header is non-empty and stored in DB.

### 5) UI updates for session history
- Add a left-side panel with a session accordion (most recent first).
- Selecting a session loads report, chat history, and cost summary.
- Add a “New Session” action to reset UI state.
- **Autonomous check:** manual UI validation of session switching.

### 6) Validation
- Run `ruff check .`.
- Optional: run a minimal end-to-end DB script to verify persistence.
