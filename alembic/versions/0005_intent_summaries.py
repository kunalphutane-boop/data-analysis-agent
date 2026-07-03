"""per-intent summaries: intent_summaries table

Adds a `intent_summaries` table that stores one narrative summary per distinct
Intent for a classification run. Cached by the same key as `call_labels`
— (dataset_id, text_column, context_hash, intent) — so an unchanged
dataset+column+context resumes and reuses the summaries (no new Gemini calls),
while a changed business context (different context_hash) refreshes them.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "intent_summaries",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("dataset_id", sa.Text(), nullable=False),
        sa.Column("text_column", sa.Text(), nullable=False),
        sa.Column("context_hash", sa.Text(), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["classification_jobs.id"]),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_id",
            "text_column",
            "context_hash",
            "intent",
            name="uq_intent_summaries_key",
        ),
    )
    op.create_index(
        "ix_intent_summaries_key",
        "intent_summaries",
        ["dataset_id", "text_column", "context_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_intent_summaries_key", table_name="intent_summaries")
    op.drop_table("intent_summaries")
