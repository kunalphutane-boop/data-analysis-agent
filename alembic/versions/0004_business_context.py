"""business context: sessions.business_context + context-aware classification cache key

Adds a user-authored free-text business context on `sessions` and threads a
`context_hash` fingerprint of that context through `classification_jobs` and
`call_labels`, extending the idempotency key so a changed business context is a
fresh classification run (new labels) while an unchanged one still resumes.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# sha256("")[:16] — the fingerprint of an empty/unset business context, so pre-existing
# rows keep resuming exactly as before (no re-classification, no re-bill).
EMPTY_CONTEXT_HASH = "e3b0c44298fc1c14"


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "business_context", sa.Text(), nullable=False, server_default=""
        ),
    )
    op.add_column(
        "classification_jobs",
        sa.Column(
            "context_hash",
            sa.Text(),
            nullable=False,
            server_default=EMPTY_CONTEXT_HASH,
        ),
    )

    # Recreate call_labels with context_hash folded into the unique key + index.
    with op.batch_alter_table("call_labels", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                "context_hash",
                sa.Text(),
                nullable=False,
                server_default=EMPTY_CONTEXT_HASH,
            )
        )
        batch_op.drop_constraint("uq_call_labels_key", type_="unique")
        batch_op.create_unique_constraint(
            "uq_call_labels_key",
            ["dataset_id", "text_column", "context_hash", "row_index"],
        )
        batch_op.drop_index("ix_call_labels_dataset_column")
        batch_op.create_index(
            "ix_call_labels_dataset_column",
            ["dataset_id", "text_column", "context_hash"],
        )


def downgrade() -> None:
    with op.batch_alter_table("call_labels", recreate="always") as batch_op:
        batch_op.drop_index("ix_call_labels_dataset_column")
        batch_op.create_index(
            "ix_call_labels_dataset_column",
            ["dataset_id", "text_column"],
        )
        batch_op.drop_constraint("uq_call_labels_key", type_="unique")
        batch_op.create_unique_constraint(
            "uq_call_labels_key",
            ["dataset_id", "text_column", "row_index"],
        )
        batch_op.drop_column("context_hash")

    op.drop_column("classification_jobs", "context_hash")
    op.drop_column("sessions", "business_context")
