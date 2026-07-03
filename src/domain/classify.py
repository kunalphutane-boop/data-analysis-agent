"""Conversation Intelligence orchestrator (Phase 4).

Starts a classify job (creates the job row + kicks off an in-process background task),
reads progress/results for polling, and streams the labelled CSV. The heavy lifting
(taxonomy derivation + batched Gemini classification + incremental persistence) lives
in `src/analysis/classifier.py`. Idempotent/resumable: a re-run for the same
dataset + column skips already-labelled rows and reuses the derived taxonomy.
"""
from __future__ import annotations

import asyncio
import io
import json
import threading
from datetime import datetime, timezone

import pandas as pd

from analysis import classifier, loader
from db.models import CallLabelRow, ClassificationJobRow, DatasetRow, SessionRow
from db.session import create_db_session


class NotFoundError(Exception):
    pass


class BadColumnError(Exception):
    pass


class NotReadyError(Exception):
    pass


def _dataset_columns(dataset: DatasetRow) -> list[str]:
    profile = json.loads(dataset.profile_json)
    return [c["name"] for c in profile.get("columns", [])]


def _spawn_job(job_id: str) -> None:
    """Run the async classifier in a daemon thread with its own event loop, so the
    HTTP request returns immediately and SQLite writes stay off the request thread."""

    def _worker() -> None:
        asyncio.run(classifier.run_classification(job_id))

    threading.Thread(target=_worker, name=f"classify-{job_id}", daemon=True).start()


def start_job(dataset_id: str, text_column: str, *, spawn: bool = True) -> dict:
    """Create a classification job for a dataset's transcript column and kick it off.

    Returns the initial job envelope. Idempotent/resumable — reuses existing labels
    and taxonomy for the same (dataset_id, text_column).
    """
    with create_db_session() as session:
        dataset = session.get(DatasetRow, dataset_id)
        if dataset is None:
            raise NotFoundError(f"Dataset {dataset_id} not found.")
        if text_column not in _dataset_columns(dataset):
            raise BadColumnError(f"Column {text_column!r} is not in the dataset.")

        # Fingerprint the session's business context into the job's cache key, so a
        # changed context is a fresh classification run (fresh, context-aware labels).
        session_row = session.get(SessionRow, dataset.session_id)
        business_context = (session_row.business_context or "") if session_row else ""
        context_hash = classifier.context_fingerprint(business_context)

        job = ClassificationJobRow(
            dataset_id=dataset_id,
            session_id=dataset.session_id,
            text_column=text_column,
            context_hash=context_hash,
            status="pending",
            total_calls=int(dataset.row_count),
            classified_calls=0,
        )
        session.add(job)
        session.flush()
        data = {
            "job_id": job.id,
            "dataset_id": dataset_id,
            "text_column": text_column,
            "status": job.status,
            "total_calls": job.total_calls,
            "classified_calls": job.classified_calls,
        }
    if spawn:
        _spawn_job(data["job_id"])
    return data


def _elapsed_seconds(started_at: datetime, updated_at: datetime, status: str) -> float:
    end = updated_at if status in ("done", "error") else datetime.now(timezone.utc)
    start = started_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return round(max(0.0, (end - start).total_seconds()), 1)


def get_progress(job_id: str) -> dict:
    with create_db_session() as session:
        job = session.get(ClassificationJobRow, job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found.")
        total = job.total_calls or 0
        classified = job.classified_calls or 0
        percent = round(100.0 * classified / total, 1) if total else 0.0
        return {
            "job_id": job.id,
            "status": job.status,
            "total_calls": total,
            "classified_calls": classified,
            "percent": percent,
            "elapsed_seconds": _elapsed_seconds(job.started_at, job.updated_at, job.status),
            "input_tokens": job.input_tokens,
            "output_tokens": job.output_tokens,
            "cost_usd": job.cost_usd,
            "error": job.error,
        }


def _pcts(counts: list[int], total: int) -> list[float]:
    """Percentages rounded to 1 decimal that sum to exactly 100.0 (largest remainder)."""
    if total <= 0:
        return [0.0 for _ in counts]
    raw = [100.0 * c / total for c in counts]
    floored = [round(x, 1) for x in raw]
    # Correct residual drift onto the largest-count buckets so the sum hits 100.0.
    drift = round(100.0 - sum(floored), 1)
    if abs(drift) >= 0.05 and counts:
        order = sorted(range(len(counts)), key=lambda i: counts[i], reverse=True)
        step = 0.1 if drift > 0 else -0.1
        i = 0
        remaining = int(round(abs(drift) / 0.1))
        while remaining > 0 and order:
            idx = order[i % len(order)]
            floored[idx] = round(floored[idx] + step, 1)
            remaining -= 1
            i += 1
    return floored


def _load_labels(
    session, dataset_id: str, text_column: str, context_hash: str
) -> list[CallLabelRow]:
    return (
        session.query(CallLabelRow)
        .filter(
            CallLabelRow.dataset_id == dataset_id,
            CallLabelRow.text_column == text_column,
            CallLabelRow.context_hash == context_hash,
        )
        .all()
    )


def _aggregate(labels: list[CallLabelRow]) -> dict:
    total = len(labels)
    intent_counts: dict[str, int] = {}
    outcome_counts: dict[str, int] = {"Positive": 0, "Neutral": 0, "Negative": 0}
    cross: dict[str, dict[str, int]] = {}
    for lbl in labels:
        intent_counts[lbl.intent] = intent_counts.get(lbl.intent, 0) + 1
        outcome_counts[lbl.outcome] = outcome_counts.get(lbl.outcome, 0) + 1
        bucket = cross.setdefault(
            lbl.intent, {"positive": 0, "neutral": 0, "negative": 0}
        )
        bucket[lbl.outcome.lower()] = bucket.get(lbl.outcome.lower(), 0) + 1

    intents = list(intent_counts.keys())
    intent_pcts = _pcts([intent_counts[i] for i in intents], total)
    intent_breakdown = [
        {"intent": i, "count": intent_counts[i], "pct": p}
        for i, p in zip(intents, intent_pcts)
    ]

    outcomes = [o for o in ("Positive", "Neutral", "Negative")]
    outcome_pcts = _pcts([outcome_counts[o] for o in outcomes], total)
    outcome_breakdown = [
        {"outcome": o, "count": outcome_counts[o], "pct": p}
        for o, p in zip(outcomes, outcome_pcts)
    ]

    cross_tab = []
    for intent in intents:
        c = cross[intent]
        row_total = c["positive"] + c["neutral"] + c["negative"]
        cross_tab.append(
            {
                "intent": intent,
                "positive": c["positive"],
                "neutral": c["neutral"],
                "negative": c["negative"],
                "total": row_total,
            }
        )

    return {
        "total_calls": total,
        "intent_breakdown": intent_breakdown,
        "outcome_breakdown": outcome_breakdown,
        "cross_tab": cross_tab,
    }


def get_results(job_id: str) -> dict:
    with create_db_session() as session:
        job = session.get(ClassificationJobRow, job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found.")
        labels = _load_labels(session, job.dataset_id, job.text_column, job.context_hash)
        agg = _aggregate(labels)
        taxonomy = json.loads(job.taxonomy_json) if job.taxonomy_json else []
        return {
            "job_id": job.id,
            "status": job.status,
            "total_calls": agg["total_calls"],
            "taxonomy": taxonomy,
            "intent_breakdown": agg["intent_breakdown"],
            "outcome_breakdown": agg["outcome_breakdown"],
            "cross_tab": agg["cross_tab"],
            "input_tokens": job.input_tokens,
            "output_tokens": job.output_tokens,
            "cost_usd": job.cost_usd,
        }


def export_labelled_csv(job_id: str) -> tuple[str, str]:
    """Return (csv_text, download_filename). Original columns + Intent + Outcome,
    one row per input row in input order. Raises NotReadyError if the job isn't done."""
    with create_db_session() as session:
        job = session.get(ClassificationJobRow, job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found.")
        if job.status != "done":
            raise NotReadyError("The classification job is not finished yet.")
        dataset = session.get(DatasetRow, job.dataset_id)
        if dataset is None:
            raise NotFoundError("Dataset file not found.")
        filepath = dataset.filepath
        filename = dataset.filename
        by_index = {
            lbl.row_index: (lbl.intent, lbl.outcome)
            for lbl in _load_labels(
                session, job.dataset_id, job.text_column, job.context_hash
            )
        }

    df = loader.load_dataframe(filepath)
    intents = []
    outcomes = []
    for row_index in range(len(df)):
        intent, outcome = by_index.get(
            row_index, (classifier.UNCLASSIFIED_INTENT, classifier.DEFAULT_OUTCOME)
        )
        intents.append(intent)
        outcomes.append(outcome)
    out = df.copy()
    out["Intent"] = intents
    out["Outcome"] = outcomes

    buf = io.StringIO()
    out.to_csv(buf, index=False)
    stem = filename[:-4] if filename.lower().endswith(".csv") else filename
    return buf.getvalue(), f"{stem}_labelled.csv"
