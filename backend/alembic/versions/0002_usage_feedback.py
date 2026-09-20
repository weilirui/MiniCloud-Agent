"""add llm_usage and message_feedback tables

Revision ID: 0002_usage_feedback
Revises: 0001_initial
Create Date: 2026-09-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_usage_feedback"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("endpoint", sa.String(64), nullable=False, server_default=""),
        sa.Column("prompt_tokens", sa.Integer, nullable=True, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=True, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=True, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=True, server_default="0"),
        sa.Column("extra", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_llm_usage_session_id", "llm_usage", ["session_id"])

    op.create_table(
        "message_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("query", sa.Text, nullable=True),
        sa.Column("answer", sa.Text, nullable=True),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("tags", postgresql.JSONB, nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column("extra", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_message_feedback_session_id", "message_feedback", ["session_id"])
    op.create_index("ix_message_feedback_message_id", "message_feedback", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_message_feedback_message_id", table_name="message_feedback")
    op.drop_index("ix_message_feedback_session_id", table_name="message_feedback")
    op.drop_table("message_feedback")
    op.drop_index("ix_llm_usage_session_id", table_name="llm_usage")
    op.drop_table("llm_usage")
