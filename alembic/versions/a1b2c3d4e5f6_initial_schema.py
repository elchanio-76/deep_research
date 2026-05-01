"""Initial schema: sessions and messages tables.

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("header", sa.Text(), nullable=True),
        sa.Column("initial_prompt", sa.Text(), nullable=False),
        sa.Column("report_markdown", sa.Text(), nullable=True),
        sa.Column(
            "search_mode",
            sa.Text(),
            nullable=False,
            server_default="no_adaptive",
        ),
        sa.Column(
            "cost_effective_search",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("usage_jsonb", postgresql.JSONB(), nullable=True),
        sa.Column("cost_summary_jsonb", postgresql.JSONB(), nullable=True),
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("message_type", sa.Text(), nullable=False),
        sa.Column("agent_name", sa.Text(), nullable=True),
        sa.Column("usage_jsonb", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "idx_sessions_last_activity",
        "sessions",
        [sa.text("last_activity_at DESC")],
    )
    op.create_index(
        "idx_messages_session_id",
        "messages",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_messages_session_id", table_name="messages")
    op.drop_index("idx_sessions_last_activity", table_name="sessions")
    op.drop_table("messages")
    op.drop_table("sessions")
