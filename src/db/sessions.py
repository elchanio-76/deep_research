import uuid

import asyncpg


async def create_session(
    pool: asyncpg.Pool,
    session_id: uuid.UUID,
    initial_prompt: str,
    search_mode: str,
    cost_effective_search: bool,
    usage_json: str,
    cost_json: str,
) -> None:
    """Insert a new session row and its initial user message."""
    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO sessions (
                id,
                header,
                initial_prompt,
                report_markdown,
                search_mode,
                cost_effective_search,
                usage_jsonb,
                cost_summary_jsonb
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            session_id,
            None,
            initial_prompt,
            None,
            search_mode,
            cost_effective_search,
            usage_json,
            cost_json,
        )
        await connection.execute(
            """
            INSERT INTO messages (
                id, session_id, role, content, message_type, agent_name, usage_jsonb
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            uuid.uuid4(),
            session_id,
            "user",
            initial_prompt,
            "report",
            None,
            None,
        )


async def update_session(
    pool: asyncpg.Pool,
    session_id: uuid.UUID,
    header: str | None = None,
    report_markdown: str | None = None,
    search_mode: str | None = None,
    usage_json: str | None = None,
    cost_json: str | None = None,
) -> None:
    """Update mutable fields on an existing session row."""
    async with pool.acquire() as connection:
        await connection.execute(
            """
            UPDATE sessions
            SET updated_at = NOW(),
                last_activity_at = NOW(),
                header = COALESCE($2, header),
                report_markdown = COALESCE($3, report_markdown),
                search_mode = COALESCE($4, search_mode),
                usage_jsonb = COALESCE($5::jsonb, usage_jsonb),
                cost_summary_jsonb = COALESCE($6::jsonb, cost_summary_jsonb)
            WHERE id = $1
            """,
            session_id,
            header,
            report_markdown,
            search_mode,
            usage_json,
            cost_json,
        )


async def list_sessions(pool: asyncpg.Pool) -> list[dict]:
    """Return a list of {id, header, initial_prompt, created_at} ordered by last activity."""
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT id, header, initial_prompt, created_at
            FROM sessions
            ORDER BY last_activity_at DESC
            """
        )
    return [dict(row) for row in rows]


async def load_session(pool: asyncpg.Pool, session_id: uuid.UUID) -> dict | None:
    """Return the full session row as a dict, or None if not found."""
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT id,
                   header,
                   initial_prompt,
                   report_markdown,
                   search_mode,
                   cost_effective_search,
                   usage_jsonb,
                   cost_summary_jsonb,
                   created_at,
                   updated_at,
                   last_activity_at
            FROM sessions
            WHERE id = $1
            """,
            session_id,
        )
    if row is None:
        return None
    return dict(row)


async def delete_session(pool: asyncpg.Pool, session_id: uuid.UUID) -> bool:
    """Delete a session and its cascaded messages. Returns True if the row existed."""
    async with pool.acquire() as connection:
        result = await connection.execute(
            "DELETE FROM sessions WHERE id = $1",
            session_id,
        )
    # asyncpg returns a string like "DELETE 1" or "DELETE 0"
    return result.endswith("1")
