"""Message-related database query functions."""

import uuid

import asyncpg


async def insert_message(
    pool: asyncpg.Pool,
    message_id: uuid.UUID,
    session_id: uuid.UUID,
    role: str,
    content: str,
    message_type: str,
    agent_name: str | None = None,
    usage_json: str | None = None,
) -> None:
    """Insert a row into the messages table."""
    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO messages (
                id, session_id, role, content, message_type, agent_name, usage_jsonb
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            message_id,
            session_id,
            role,
            content,
            message_type,
            agent_name,
            usage_json,
        )


async def fetch_chat_messages(
    pool: asyncpg.Pool,
    session_id: uuid.UUID,
) -> list[dict]:
    """Return list of {role, content} for message_type='chat', ordered by created_at."""
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT role, content
            FROM messages
            WHERE session_id = $1 AND message_type = 'chat'
            ORDER BY created_at
            """,
            session_id,
        )
    return [dict(row) for row in rows]
