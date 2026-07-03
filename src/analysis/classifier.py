"""Async batch classifier for Conversation Intelligence (Phase 4).

Runs OUTSIDE the pandas sandbox (it legitimately needs network to reach Gemini).
Flow: derive a fixed Intent taxonomy once (sampled), then classify the remaining
un-labelled rows in batches with bounded concurrency, coerce/validate the labels,
persist them incrementally (idempotent upsert keyed by (dataset_id, text_column,
row_index)), and update the classification_jobs progress/tokens/cost as each batch
completes. Reuses the same Gemini client, pricing, and structlog observability as
the ask graph (see spec/agent.md).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import random
import re
import time
from pathlib import Path

import pandas as pd

from analysis import loader
from config.settings import get_settings
from db.models import (
    CallLabelRow,
    ClassificationJobRow,
    DatasetRow,
    IntentSummaryRow,
    SessionRow,
)
from db.session import create_db_session
from llm import pricing
from llm.client import LLMClient
from observability.events import get_logger

_PROMPTS = Path(__file__).parent.parent / "prompts"
_log = get_logger("classifier")

# The canonical lending-call fallback taxonomy (spec/capabilities/conversation_intelligence.md).
BASE_TAXONOMY: list[str] = [
    "Loan enquiry",
    "EMI/Payment",
    "Account balance/Statement",
    "Verification/Registration",
    "Branch/Timing",
    "Complaint/Escalation",
    "Other/Unclear",
]

VALID_OUTCOMES = {"Positive", "Neutral", "Negative"}
NO_TRANSCRIPT_INTENT = "No transcript"
UNCLASSIFIED_INTENT = "Unclassified"
DEFAULT_OUTCOME = "Neutral"

# Normalised column names that look like a per-call id (metadata only).
_CALL_ID_HINTS = {
    "callid",
    "diallednumber",
    "dialednumber",
    "phonenumber",
    "phone",
    "callerid",
    "id",
}


def _prompt(name: str) -> str:
    return (_PROMPTS / f"{name}.md").read_text(encoding="utf-8").strip()


def context_fingerprint(business_context: str | None) -> str:
    """Stable 16-hex fingerprint of a (normalised) business context. An empty/unset
    context maps to `EMPTY_CONTEXT_HASH` so it resumes exactly as before this feature.
    Part of the classification cache key — a changed context ⇒ a fresh run."""
    normalized = (business_context or "").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _with_business_context(system: str, business_context: str) -> str:
    """Append the user's business context to a classification system prompt so both
    the taxonomy derivation and per-call judgments are grounded in their domain."""
    if not business_context.strip():
        return system
    return (
        f"{system}\n\n"
        "## BUSINESS CONTEXT (authored by the user — tailor intents & outcomes to it)\n"
        f"{business_context.strip()}"
    )


def _default_client():
    """Build the classification client. Forces the low-cost AGENT_CLASSIFY_MODEL
    (default gemini-2.5-flash-lite) rather than the ask graph's model, per spec.
    Falls back to the auto-detected LLMClient when no Gemini key is present."""
    s = get_settings()
    if s.gemini_api_key:
        from llm.providers.gemini import GeminiProvider

        return GeminiProvider(api_key=s.gemini_api_key, model=s.classify_model)
    return LLMClient()


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```[a-zA-Z0-9]*\n(.*)\n```$", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _parse_json_array(text: str) -> list:
    cleaned = _strip_code_fences(text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array")
    return data


def is_blank(value) -> bool:
    """True for NaN / None / empty / whitespace-only transcripts."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def coerce_outcome(outcome) -> str:
    """Any value outside {Positive, Neutral, Negative} -> Neutral."""
    if isinstance(outcome, str) and outcome.strip() in VALID_OUTCOMES:
        return outcome.strip()
    return DEFAULT_OUTCOME


def coerce_intent(intent, taxonomy: list[str]) -> str:
    """An out-of-taxonomy intent falls back to the catch-all (Other/Unclear)."""
    if isinstance(intent, str) and intent.strip() in taxonomy:
        return intent.strip()
    return "Other/Unclear" if "Other/Unclear" in taxonomy else taxonomy[-1]


def detect_call_id_column(columns: list[str]) -> str | None:
    for col in columns:
        norm = re.sub(r"[^a-z0-9]", "", str(col).lower())
        if norm in _CALL_ID_HINTS:
            return col
    return None


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit]


def normalise_taxonomy(raw: list, force_base: bool = True) -> list[str]:
    """Build a clean taxonomy list with `Other/Unclear` last and no duplicates.

    With `force_base` (the default — no business context) the full generic lending
    base set is always kept, so behaviour is unchanged. When a business context is
    supplied (`force_base=False`) the model's context-tailored labels are used as-is
    (falling back to the base set only if it returned nothing), so intents actually
    reflect the user's domain rather than the generic defaults.
    """
    result: list[str] = []
    if force_base:
        result = [t for t in BASE_TAXONOMY if t != "Other/Unclear"]
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, str):
                continue
            label = item.strip()
            if label and label not in result and label != "Other/Unclear":
                result.append(label)
    if not result:
        result = [t for t in BASE_TAXONOMY if t != "Other/Unclear"]
    result.append("Other/Unclear")
    return result


# --- Transient-error retry (shared by every Gemini call) ----------------------

# Substrings (matched case-insensitively against the exception type + message) that mark
# a TRANSIENT provider error worth retrying with backoff: Gemini "high demand" 503s, rate
# limiting, and deadline/timeout/connection blips. Anything else (auth, permission, invalid
# request) is treated as non-transient and surfaced immediately.
_TRANSIENT_MARKERS: tuple[str, ...] = (
    "503",
    "unavailable",
    "429",
    "resource_exhausted",
    "resource exhausted",
    "rate limit",
    "ratelimit",
    "quota",
    "deadline",
    "timeout",
    "timed out",
    "connection",
    "temporarily",
    "overloaded",
    "high demand",
    "try again",
    "500",
    "internal error",
    "502",
    "504",
    "service unavailable",
)


def _is_transient_error(exc: BaseException) -> bool:
    """True if `exc` looks like a retryable transient provider error (throttling/network),
    False for genuinely fatal ones (auth/permission/invalid request)."""
    blob = f"{type(exc).__name__} {exc}".lower()
    return any(marker in blob for marker in _TRANSIENT_MARKERS)


def _call_with_retry(
    client: LLMClient, user: str, *, system: str | None, label: str
) -> tuple[str, int, int]:
    """Call `client.call_with_usage` with exponential backoff + jitter on TRANSIENT
    provider errors (503/UNAVAILABLE, 429/RESOURCE_EXHAUSTED, deadline/timeout/connection).
    Non-transient errors are re-raised immediately (never retried). Runs synchronously in a
    worker thread, so `time.sleep` here does not block the event loop."""
    s = get_settings()
    attempts = max(1, s.classify_retry_max_attempts)
    base = max(0.0, s.classify_retry_base_delay)
    cap = max(base, s.classify_retry_max_delay)
    for attempt in range(attempts):
        try:
            return client.call_with_usage(user, system=system)
        except Exception as exc:  # noqa: BLE001 - classify transient vs fatal below
            if not _is_transient_error(exc) or attempt == attempts - 1:
                raise
            delay = min(cap, base * (2**attempt)) + random.uniform(0, base)
            _log.warning(
                "gemini_transient_retry",
                label=label,
                attempt=attempt,
                next_attempt=attempt + 1,
                delay_s=round(delay, 2),
                error=str(exc),
            )
            time.sleep(delay)
    # Unreachable: the loop either returns or raises on the final attempt.
    raise RuntimeError("retry loop exited without returning")  # pragma: no cover


# --- Gemini calls (module-level so tests can wrap/count them) -----------------

def derive_taxonomy(
    client: LLMClient, sample_texts: list[str], business_context: str = ""
) -> tuple[list[str], int, int]:
    """Derive the fixed Intent taxonomy from a sample of transcripts. When a business
    context is supplied it is injected into the prompt and the taxonomy is tailored to
    that domain (rather than forced to the generic base set). Falls back to the base
    lending set on any failure. Returns (taxonomy, input_tokens, output_tokens)."""
    force_base = not business_context.strip()
    if not sample_texts:
        return list(BASE_TAXONOMY), 0, 0
    listing = "\n".join(f"- {t}" for t in sample_texts)
    user = (
        "Here is a sample of call transcripts. Derive the fixed Intent taxonomy.\n\n"
        f"Sample transcripts:\n{listing}"
    )
    system = _with_business_context(_prompt("derive_taxonomy"), business_context)
    try:
        text, it, ot = _call_with_retry(
            client, user, system=system, label="derive_taxonomy"
        )
        raw = _parse_json_array(text)
        return normalise_taxonomy(raw, force_base=force_base), it, ot
    except Exception as exc:  # never fail the job on taxonomy derivation
        # Transient throttling that exhausted retries lands here too: fall back to the
        # generic base taxonomy and keep going (context-mode still proceeds).
        _log.warning(
            "taxonomy_derivation_fallback_base",
            error=str(exc),
            transient=_is_transient_error(exc),
        )
        return list(BASE_TAXONOMY), 0, 0


def classify_batch(
    client: LLMClient,
    taxonomy: list[str],
    batch: list[tuple[int, str]],
    business_context: str = "",
) -> tuple[dict[int, tuple[str, str]], int, int]:
    """Classify one batch of (call_index, transcript). Retry once on malformed JSON;
    rows still missing after that are left out (caller marks them Unclassified/Neutral).
    When a business context is supplied it is injected so per-call intent + outcome
    judgments use it. Returns ({call_index: (intent, outcome)}, input_tokens, output_tokens)."""
    payload = [{"call_index": idx, "transcript": text} for idx, text in batch]
    user = (
        "Taxonomy (choose intent from this list only):\n"
        + json.dumps(taxonomy, ensure_ascii=False)
        + "\n\nTranscripts to classify (JSON array of {call_index, transcript}):\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n\nReturn a JSON array with one object per transcript."
    )
    system = _with_business_context(_prompt("classify_calls"), business_context)

    total_it = total_ot = 0
    for attempt in range(2):  # initial + one retry for MALFORMED JSON
        # The network call itself is retried (transient 503/429/timeout) inside
        # _call_with_retry. If that exhausts its retries — or hits a non-transient error —
        # it raises here; we stop and let the caller mark the batch Unclassified/Neutral
        # (never re-running the full backoff cycle a second time for a dead endpoint).
        try:
            text, it, ot = _call_with_retry(
                client, user, system=system, label="classify_batch"
            )
        except Exception as exc:
            _log.warning(
                "classify_batch_call_failed",
                attempt=attempt,
                transient=_is_transient_error(exc),
                error=str(exc),
            )
            break
        total_it += it
        total_ot += ot
        try:
            arr = _parse_json_array(text)
        except Exception as exc:
            _log.warning("classify_batch_parse_failed", attempt=attempt, error=str(exc))
            continue
        out: dict[int, tuple[str, str]] = {}
        for item in arr:
            if not isinstance(item, dict) or "call_index" not in item:
                continue
            try:
                idx = int(item["call_index"])
            except (TypeError, ValueError):
                continue
            intent = coerce_intent(item.get("intent"), taxonomy)
            outcome = coerce_outcome(item.get("outcome"))
            out[idx] = (intent, outcome)
        if out:
            return out, total_it, total_ot
    # Every attempt exhausted: signal fallback so a degraded run is visible without failing.
    _log.warning("classify_batch_fallback_unclassified", batch_size=len(batch))
    return {}, total_it, total_ot


# --- Per-intent summaries (Gemini call per distinct intent) --------------------

# Sentinel intents that are not worth (and don't make sense) sending to Gemini for a
# narrative — they get a deterministic canned summary instead (still non-empty).
_SENTINEL_INTENTS = {NO_TRANSCRIPT_INTENT, UNCLASSIFIED_INTENT}


def _canned_summary(intent: str, count: int, pct: float) -> str:
    """A deterministic, no-LLM summary for sentinel intents (No transcript / Unclassified)."""
    if intent == NO_TRANSCRIPT_INTENT:
        return (
            f"{count} calls ({pct:.1f}%) had no transcript text to analyse, so they were "
            "labelled without an LLM call and default to a Neutral outcome. These are blank "
            "or missing recordings rather than a real customer intent."
        )
    if intent == UNCLASSIFIED_INTENT:
        return (
            f"{count} calls ({pct:.1f}%) could not be reliably classified into the taxonomy "
            "(the model's response was malformed after a retry) and default to Neutral. "
            "Re-running classification may resolve them."
        )
    return f"{count} calls ({pct:.1f}%) in this category."


def _format_outcome_dist(outcome_counts: dict[str, int]) -> str:
    return (
        f"Positive={outcome_counts.get('Positive', 0)}, "
        f"Neutral={outcome_counts.get('Neutral', 0)}, "
        f"Negative={outcome_counts.get('Negative', 0)}"
    )


def summarise_intent(
    client: LLMClient,
    intent: str,
    count: int,
    pct: float,
    outcome_counts: dict[str, int],
    samples: list[str],
    business_context: str = "",
) -> tuple[str, int, int]:
    """Generate a concise narrative summary for ONE intent category via a single Gemini
    call. Grounded in the intent's count/share, its Outcome distribution, a representative
    sample of transcripts, and the session's business context. Never raises — falls back
    to a short deterministic summary on any failure. Returns (summary, input_tokens,
    output_tokens)."""
    listing = "\n".join(f"- {t}" for t in samples) if samples else "(no sample transcripts)"
    user = (
        f"Intent category: {intent}\n"
        f"Calls in this intent: {count} ({pct:.1f}% of all classified calls)\n"
        f"Outcome distribution: {_format_outcome_dist(outcome_counts)}\n\n"
        "Representative sample of transcripts classified into this intent:\n"
        f"{listing}\n\n"
        "Write the 2-4 sentence summary for this intent now."
    )
    system = _with_business_context(_prompt("summarise_intent"), business_context)
    try:
        text, it, ot = _call_with_retry(
            client, user, system=system, label="summarise_intent"
        )
        summary = _strip_code_fences(text).strip()
        if not summary:
            raise ValueError("empty summary")
        return summary, it, ot
    except Exception as exc:  # never fail the job on a summary
        _log.warning("intent_summary_failed", intent=intent, error=str(exc))
        return (
            f"{count} calls ({pct:.1f}%) classified as {intent}. "
            f"Outcome mix — {_format_outcome_dist(outcome_counts)}.",
            0,
            0,
        )


# --- Persistence helpers ------------------------------------------------------

def _labelled_row_indices(
    session, dataset_id: str, text_column: str, context_hash: str
) -> set[int]:
    rows = (
        session.query(CallLabelRow.row_index)
        .filter(
            CallLabelRow.dataset_id == dataset_id,
            CallLabelRow.text_column == text_column,
            CallLabelRow.context_hash == context_hash,
        )
        .all()
    )
    return {r[0] for r in rows}


def _load_labels_for_key(
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


def _upsert_labels(session, job_id, dataset_id, text_column, context_hash, labels):
    """labels: list of (row_index, call_id, intent, outcome). Skips keys already present
    for this (dataset, text_column, context_hash)."""
    existing = _labelled_row_indices(session, dataset_id, text_column, context_hash)
    written = 0
    for row_index, call_id, intent, outcome in labels:
        if row_index in existing:
            continue
        session.add(
            CallLabelRow(
                job_id=job_id,
                dataset_id=dataset_id,
                text_column=text_column,
                context_hash=context_hash,
                row_index=row_index,
                call_id=call_id,
                intent=intent,
                outcome=outcome,
            )
        )
        existing.add(row_index)
        written += 1
    return written


def _existing_summary_intents(
    session, dataset_id: str, text_column: str, context_hash: str
) -> set[str]:
    rows = (
        session.query(IntentSummaryRow.intent)
        .filter(
            IntentSummaryRow.dataset_id == dataset_id,
            IntentSummaryRow.text_column == text_column,
            IntentSummaryRow.context_hash == context_hash,
        )
        .all()
    )
    return {r[0] for r in rows}


async def generate_intent_summaries(
    job_id: str,
    dataset_id: str,
    text_column: str,
    context_hash: str,
    transcripts: list,
    business_context: str,
    client: LLMClient,
    settings,
    totals: dict,
) -> None:
    """After per-call labels are persisted, generate one concise narrative summary per
    distinct Intent (a single Gemini call each — there are only ~6-12 intents) and cache
    it keyed by (dataset_id, text_column, context_hash, intent). Idempotent/resumable:
    intents that already have a cached summary are skipped, so an unchanged run resumes
    with no new Gemini calls. Rolls summary tokens/cost into the job's accounting."""
    with create_db_session() as session:
        label_rows = [
            (lbl.row_index, lbl.intent, lbl.outcome)
            for lbl in _load_labels_for_key(session, dataset_id, text_column, context_hash)
        ]
        existing = _existing_summary_intents(session, dataset_id, text_column, context_hash)

    total = len(label_rows)
    if total == 0:
        return

    # Aggregate per-intent: count, outcome distribution, and a capped transcript sample.
    per_intent: dict[str, dict] = {}
    for row_index, intent, outcome in label_rows:
        d = per_intent.setdefault(
            intent,
            {"count": 0, "outcomes": {"Positive": 0, "Neutral": 0, "Negative": 0}, "samples": []},
        )
        d["count"] += 1
        d["outcomes"][outcome] = d["outcomes"].get(outcome, 0) + 1
        if len(d["samples"]) < settings.summary_sample_size and 0 <= row_index < len(transcripts):
            raw = transcripts[row_index]
            if not is_blank(raw):
                d["samples"].append(
                    _truncate(str(raw), settings.summary_transcript_max_chars)
                )

    pending_intents = [i for i in per_intent if i not in existing]
    if not pending_intents:
        return

    for intent in pending_intents:
        d = per_intent[intent]
        pct = round(100.0 * d["count"] / total, 1) if total else 0.0
        if intent in _SENTINEL_INTENTS:
            summary, it, ot = _canned_summary(intent, d["count"], pct), 0, 0
        else:
            summary, it, ot = await asyncio.to_thread(
                summarise_intent,
                client,
                intent,
                d["count"],
                pct,
                d["outcomes"],
                d["samples"],
                business_context,
            )
        totals["it"] += it
        totals["ot"] += ot
        with create_db_session() as session:
            # Guard against a concurrent writer having filled this intent in the meantime.
            if intent in _existing_summary_intents(
                session, dataset_id, text_column, context_hash
            ):
                continue
            session.add(
                IntentSummaryRow(
                    job_id=job_id,
                    dataset_id=dataset_id,
                    text_column=text_column,
                    context_hash=context_hash,
                    intent=intent,
                    summary=summary,
                )
            )
            job = session.get(ClassificationJobRow, job_id)
            if job is not None:
                job.input_tokens = totals["it"]
                job.output_tokens = totals["ot"]
                job.cost_usd = pricing.cost_usd(
                    settings.classify_model, totals["it"], totals["ot"]
                )


# --- Orchestration ------------------------------------------------------------

async def run_classification(job_id: str, client: LLMClient | None = None) -> None:
    """Background entry point. Loads the job, derives/reuses the taxonomy, classifies
    the remaining un-labelled rows in bounded-concurrency batches, and persists
    incrementally. Marks the job `done` (or `error`). Never raises to the caller."""
    settings = get_settings()
    client = client or _default_client()
    try:
        await _run(job_id, client, settings)
    except Exception as exc:  # pragma: no cover - defensive
        _log.error("classification_job_failed", job_id=job_id, error=str(exc))
        with create_db_session() as session:
            job = session.get(ClassificationJobRow, job_id)
            if job is not None:
                job.status = "error"
                job.error = str(exc)


async def _run(job_id: str, client: LLMClient, settings) -> None:
    # 1. Load job + dataset, read the DataFrame.
    with create_db_session() as session:
        job = session.get(ClassificationJobRow, job_id)
        if job is None:
            return
        dataset = session.get(DatasetRow, job.dataset_id)
        if dataset is None:
            job.status = "error"
            job.error = "Dataset file not found."
            return
        dataset_id = job.dataset_id
        text_column = job.text_column
        context_hash = job.context_hash
        session_id = job.session_id
        filepath = dataset.filepath
        existing_taxonomy = json.loads(job.taxonomy_json) if job.taxonomy_json else None
        job.status = "deriving_taxonomy"

    # Load the user-authored business context for this session (grounds both prompts).
    with create_db_session() as session:
        session_row = session.get(SessionRow, session_id)
        business_context = (session_row.business_context or "").strip() if session_row else ""
    has_context = bool(business_context)

    df = loader.load_dataframe(filepath)
    if text_column not in df.columns:
        with create_db_session() as session:
            job = session.get(ClassificationJobRow, job_id)
            if job is not None:
                job.status = "error"
                job.error = f"Column {text_column!r} not found in the dataset."
        return

    total_calls = int(len(df))
    transcripts = df[text_column].tolist()
    call_id_col = detect_call_id_column(list(df.columns))
    call_ids = df[call_id_col].tolist() if call_id_col else [None] * total_calls

    # 2. Determine which rows still need classifying (idempotent resume).
    with create_db_session() as session:
        already = _labelled_row_indices(session, dataset_id, text_column, context_hash)
        job = session.get(ClassificationJobRow, job_id)
        job.total_calls = total_calls
        job.classified_calls = len(already)
        # Reuse taxonomy from this job or any prior job for the same
        # dataset + column + context. A changed context has a different hash, so it
        # derives a fresh, context-aware taxonomy rather than reusing a stale one.
        if existing_taxonomy is None:
            prior = (
                session.query(ClassificationJobRow)
                .filter(
                    ClassificationJobRow.dataset_id == dataset_id,
                    ClassificationJobRow.text_column == text_column,
                    ClassificationJobRow.context_hash == context_hash,
                    ClassificationJobRow.taxonomy_json.isnot(None),
                )
                .first()
            )
            if prior is not None and prior.taxonomy_json:
                existing_taxonomy = json.loads(prior.taxonomy_json)

    # 3. Split remaining rows into empty (no LLM) vs. to-classify.
    empty_rows: list[tuple] = []
    pending: list[tuple[int, str]] = []
    for row_index in range(total_calls):
        if row_index in already:
            continue
        raw = transcripts[row_index]
        cid = call_ids[row_index]
        cid = None if cid is None or (not isinstance(cid, str) and pd.isna(cid)) else str(cid)
        if is_blank(raw):
            empty_rows.append((row_index, cid, NO_TRANSCRIPT_INTENT, DEFAULT_OUTCOME))
        else:
            pending.append((row_index, cid, _truncate(str(raw), settings.transcript_max_chars)))

    # 4. Derive taxonomy (once) from a sample of non-empty transcripts.
    if existing_taxonomy:
        taxonomy = normalise_taxonomy(existing_taxonomy, force_base=not has_context)
        tax_it = tax_ot = 0
    else:
        sample_source = [t for _, _, t in pending] or [
            str(v) for v in transcripts if not is_blank(v)
        ]
        sample = sample_source[: settings.taxonomy_sample_size]
        taxonomy, tax_it, tax_ot = await asyncio.to_thread(
            derive_taxonomy, client, sample, business_context
        )

    totals = {"it": tax_it, "ot": tax_ot}
    db_lock = asyncio.Lock()

    with create_db_session() as session:
        job = session.get(ClassificationJobRow, job_id)
        job.taxonomy_json = json.dumps(taxonomy)
        job.status = "classifying"
        job.input_tokens = totals["it"]
        job.output_tokens = totals["ot"]
        job.cost_usd = pricing.cost_usd(settings.classify_model, totals["it"], totals["ot"])
        # 5. Persist empty-transcript rows immediately (no Gemini call).
        if empty_rows:
            _upsert_labels(
                session, job_id, dataset_id, text_column, context_hash, empty_rows
            )
            job.classified_calls = job.classified_calls + len(empty_rows)

    # 6. Batch the pending rows; classify with bounded concurrency.
    batch_size = max(1, settings.classify_batch_size)
    batches = [pending[i : i + batch_size] for i in range(0, len(pending), batch_size)]
    # Conservative concurrency bound: high concurrency provokes Gemini "high demand" 503s
    # on large (12k-row) jobs. Reliability over raw speed — a big run may take minutes.
    sem = asyncio.Semaphore(max(1, settings.classify_max_concurrency))

    async def _process(batch: list[tuple[int, str, str]]) -> None:
        indexed = [(row_index, text) for row_index, _cid, text in batch]
        async with sem:
            result, it, ot = await asyncio.to_thread(
                classify_batch, client, taxonomy, indexed, business_context
            )
        labels = []
        for row_index, cid, _text in batch:
            intent, outcome = result.get(row_index, (UNCLASSIFIED_INTENT, DEFAULT_OUTCOME))
            labels.append((row_index, cid, intent, outcome))
        async with db_lock:
            totals["it"] += it
            totals["ot"] += ot
            with create_db_session() as session:
                written = _upsert_labels(
                    session, job_id, dataset_id, text_column, context_hash, labels
                )
                job = session.get(ClassificationJobRow, job_id)
                job.classified_calls = job.classified_calls + written
                job.input_tokens = totals["it"]
                job.output_tokens = totals["ot"]
                job.cost_usd = pricing.cost_usd(
                    settings.classify_model, totals["it"], totals["ot"]
                )

    if batches:
        # return_exceptions=True: one batch's ultimate failure never cancels its siblings.
        # _process already falls back to Unclassified/Neutral internally, so a returned
        # exception is only a defensive last resort — log it and keep the job alive.
        results = await asyncio.gather(
            *(_process(b) for b in batches), return_exceptions=True
        )
        for exc in results:
            if isinstance(exc, BaseException):
                _log.warning("classify_batch_task_exception", error=str(exc))

    # 7. Per-intent narrative summaries (one Gemini call per distinct intent; cached by
    #    the same key as the labels, so an unchanged resume makes no new calls).
    with create_db_session() as session:
        job = session.get(ClassificationJobRow, job_id)
        job_errored = job is None or job.status == "error"
    if not job_errored:
        await generate_intent_summaries(
            job_id,
            dataset_id,
            text_column,
            context_hash,
            transcripts,
            business_context,
            client,
            settings,
            totals,
        )

    # 8. Finalise.
    with create_db_session() as session:
        job = session.get(ClassificationJobRow, job_id)
        if job is not None and job.status != "error":
            job.status = "done"
            job.classified_calls = total_calls
            job.input_tokens = totals["it"]
            job.output_tokens = totals["ot"]
            job.cost_usd = pricing.cost_usd(
                settings.classify_model, totals["it"], totals["ot"]
            )
    _log.info(
        "classification_done",
        job_id=job_id,
        total=total_calls,
        input_tokens=totals["it"],
        output_tokens=totals["ot"],
    )
