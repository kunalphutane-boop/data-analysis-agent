"""conversation intelligence: classification_jobs, call_labels

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "classification_jobs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("dataset_id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("text_column", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("total_calls", sa.Integer(), nullable=False),
        sa.Column("classified_calls", sa.Integer(), nullable=False),
        sa.Column("taxonomy_json", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "call_labels",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("dataset_id", sa.Text(), nullable=False),
        sa.Column("text_column", sa.Text(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("call_id", sa.Text(), nullable=True),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["classification_jobs.id"]),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_id", "text_column", "row_index", name="uq_call_labels_key"
        ),
    )
    op.create_index(
        "ix_call_labels_dataset_column",
        "call_labels",
        ["dataset_id", "text_column"],
    )


def downgrade() -> None:
    op.drop_index("ix_call_labels_dataset_column", table_name="call_labels")
    op.drop_table("call_labels")
    op.drop_table("classification_jobs")
