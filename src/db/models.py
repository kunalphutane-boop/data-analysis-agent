from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Text,
    TIMESTAMP,
    Integer,
    Float,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Fingerprint of an empty/unset business context (sha256("")[:16]). Used as the
# default cache-key component so a run with no business context behaves exactly as
# it did before this column existed. Kept in sync with
# `analysis.classifier.context_fingerprint("")`.
EMPTY_CONTEXT_HASH = "e3b0c44298fc1c14"


class Base(DeclarativeBase):
    pass


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    input_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class SessionRow(Base):
    """A named workspace the user returns to across days."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="Untitled analysis")
    # User-authored, free-text business context that grounds Conversation
    # Intelligence classification (Intent taxonomy + Outcome) in the user's domain.
    business_context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class DatasetRow(Base):
    """An uploaded CSV plus its computed profile. Belongs to a session."""

    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    filepath: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    col_count: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )


class MessageRow(Base):
    """One row per ask (a conversation turn)."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.id"), nullable=False
    )
    dataset_id: Mapped[str] = mapped_column(
        Text, ForeignKey("datasets.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False, default="turn")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    generated_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )


class ClassificationJobRow(Base):
    """A background Conversation Intelligence run over one dataset's transcript column."""

    __tablename__ = "classification_jobs"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    dataset_id: Mapped[str] = mapped_column(
        Text, ForeignKey("datasets.id"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.id"), nullable=False
    )
    text_column: Mapped[str] = mapped_column(Text, nullable=False)
    # Fingerprint of the business context this job was run with (part of the cache
    # key). A changed business context yields a new hash → a fresh classification run.
    context_hash: Mapped[str] = mapped_column(
        Text, nullable=False, default=EMPTY_CONTEXT_HASH
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    total_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    classified_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    taxonomy_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class CallLabelRow(Base):
    """One row per classified call. Idempotent by (dataset_id, text_column, row_index)."""

    __tablename__ = "call_labels"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "text_column",
            "context_hash",
            "row_index",
            name="uq_call_labels_key",
        ),
        Index(
            "ix_call_labels_dataset_column",
            "dataset_id",
            "text_column",
            "context_hash",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(
        Text, ForeignKey("classification_jobs.id"), nullable=False
    )
    dataset_id: Mapped[str] = mapped_column(
        Text, ForeignKey("datasets.id"), nullable=False
    )
    text_column: Mapped[str] = mapped_column(Text, nullable=False)
    # Business-context fingerprint this label was produced under (part of the key).
    context_hash: Mapped[str] = mapped_column(
        Text, nullable=False, default=EMPTY_CONTEXT_HASH
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    call_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )


class IntentSummaryRow(Base):
    """One narrative summary per distinct Intent for a classification run. Cached by
    the same key as the per-call labels — (dataset_id, text_column, context_hash,
    intent) — so an unchanged dataset+column+context resumes and reuses the summaries
    (no new Gemini calls), while a changed business context refreshes them."""

    __tablename__ = "intent_summaries"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "text_column",
            "context_hash",
            "intent",
            name="uq_intent_summaries_key",
        ),
        Index(
            "ix_intent_summaries_key",
            "dataset_id",
            "text_column",
            "context_hash",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(
        Text, ForeignKey("classification_jobs.id"), nullable=False
    )
    dataset_id: Mapped[str] = mapped_column(
        Text, ForeignKey("datasets.id"), nullable=False
    )
    text_column: Mapped[str] = mapped_column(Text, nullable=False)
    context_hash: Mapped[str] = mapped_column(
        Text, nullable=False, default=EMPTY_CONTEXT_HASH
    )
    intent: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
