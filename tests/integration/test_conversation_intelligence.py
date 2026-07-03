"""Integration test for Conversation Intelligence — REAL Gemini via AGENT_GEMINI_API_KEY.

Skips (never stubs) if no key is present. Classifies the synthetic transcript fixture
(recognizable intents + clear positive/negative tone + one EMPTY transcript + one
REPEATED call_id) end-to-end and asserts every success criterion in
spec/capabilities/conversation_intelligence.md, including idempotent resume.

The classification is driven synchronously in the test thread (start_job(spawn=False)
+ asyncio.run) so all DB writes stay single-threaded and the gate is deterministic; the
read endpoints (progress / results / labelled.csv) and error paths are exercised over
real HTTP via the FastAPI TestClient.
"""
from __future__ import annotations

import asyncio
import io
import threading
from pathlib import Path

import pandas as pd
import pytest

from analysis import classifier
from db import session as session_module
from db.models import CallLabelRow, ClassificationJobRow, IntentSummaryRow
from domain import classify as classify_domain
from domain import dataset as dataset_domain
from domain import session as session_domain

FIXTURE = Path(__file__).parent.parent / "fixtures" / "transcripts_synthetic.csv"
TEXT_COLUMN = "Conversation Log"

LENDING_CONTEXT = (
    "We are a lending NBFC. This call center handles loan servicing: loan enquiries, "
    "EMI/payments, KYC/verification, disbursement, foreclosure/prepayment and "
    "collections/overdue. A Negative outcome means the customer's servicing issue was "
    "left unresolved or they raised a complaint."
)


@pytest.fixture
def fixture_df():
    return pd.read_csv(FIXTURE)


def _upload() -> dict:
    return dataset_domain.upload_dataset("transcripts.csv", FIXTURE.read_bytes(), None)


def _run_job(dataset_id: str) -> str:
    job = classify_domain.start_job(dataset_id, TEXT_COLUMN, spawn=False)
    asyncio.run(classifier.run_classification(job["job_id"]))
    return job["job_id"]


def _count_labels(dataset_id: str, context_hash: str | None = None) -> int:
    from sqlalchemy.orm import Session

    with Session(session_module._engine) as s:
        q = s.query(CallLabelRow).filter(
            CallLabelRow.dataset_id == dataset_id,
            CallLabelRow.text_column == TEXT_COLUMN,
        )
        if context_hash is not None:
            q = q.filter(CallLabelRow.context_hash == context_hash)
        return q.count()


@pytest.mark.usefixtures("_require_llm_key")
def test_full_classification_and_idempotency(api_client, fixture_df, monkeypatch):
    n_rows = len(fixture_df)
    assert n_rows == 8, "fixture shape changed"

    # Count every real Gemini call (taxonomy + classify batches), thread-safely.
    counter = {"classify": 0, "taxonomy": 0}
    lock = threading.Lock()
    orig_classify = classifier.classify_batch
    orig_taxonomy = classifier.derive_taxonomy

    def counting_classify(*a, **k):
        with lock:
            counter["classify"] += 1
        return orig_classify(*a, **k)

    def counting_taxonomy(*a, **k):
        with lock:
            counter["taxonomy"] += 1
        return orig_taxonomy(*a, **k)

    monkeypatch.setattr(classifier, "classify_batch", counting_classify)
    monkeypatch.setattr(classifier, "derive_taxonomy", counting_taxonomy)

    data = _upload()
    dataset_id = data["id"]

    # --- First run -----------------------------------------------------------
    job_id = _run_job(dataset_id)
    first_classify_calls = counter["classify"]
    assert first_classify_calls >= 1, "expected at least one real classify batch"
    assert counter["taxonomy"] == 1, "taxonomy derived exactly once"

    # Progress endpoint: done, fully classified, non-zero cost.
    prog = api_client.get(f"/classify/jobs/{job_id}").json()["data"]
    assert prog["status"] == "done", prog
    assert prog["total_calls"] == n_rows
    assert prog["classified_calls"] == n_rows
    assert prog["percent"] == pytest.approx(100.0, abs=0.1)
    assert prog["cost_usd"] > 0
    assert prog["input_tokens"] > 0

    # Every row labelled exactly once.
    assert _count_labels(dataset_id) == n_rows

    # Results: valid outcomes, breakdowns sum to 100, cross-tab well-formed.
    res = api_client.get(f"/classify/jobs/{job_id}/results").json()["data"]
    assert res["total_calls"] == n_rows
    assert res["taxonomy"], "taxonomy must be present"

    intent_sum = sum(b["pct"] for b in res["intent_breakdown"])
    outcome_sum = sum(b["pct"] for b in res["outcome_breakdown"])
    assert intent_sum == pytest.approx(100.0, abs=0.1), res["intent_breakdown"]
    assert outcome_sum == pytest.approx(100.0, abs=0.1), res["outcome_breakdown"]
    assert sum(b["count"] for b in res["intent_breakdown"]) == n_rows
    assert sum(b["count"] for b in res["outcome_breakdown"]) == n_rows

    for row in res["outcome_breakdown"]:
        assert row["outcome"] in {"Positive", "Neutral", "Negative"}

    grand = 0
    for row in res["cross_tab"]:
        assert row["positive"] + row["neutral"] + row["negative"] == row["total"]
        grand += row["total"]
    assert grand == n_rows

    # Per-row labels: every row has a valid outcome; empty row is No transcript/Neutral.
    from sqlalchemy.orm import Session

    with Session(session_module._engine) as s:
        labels = {
            lbl.row_index: lbl
            for lbl in s.query(CallLabelRow)
            .filter(CallLabelRow.dataset_id == dataset_id)
            .all()
        }
    assert set(labels.keys()) == set(range(n_rows))
    for lbl in labels.values():
        assert lbl.outcome in {"Positive", "Neutral", "Negative"}
        assert lbl.intent  # non-empty

    # The empty-transcript row (index 5 in the fixture) — labelled without a Gemini call.
    empty_index = next(
        i for i, v in enumerate(fixture_df[TEXT_COLUMN].tolist())
        if classifier.is_blank(v)
    )
    assert labels[empty_index].intent == "No transcript"
    assert labels[empty_index].outcome == "Neutral"

    # The repeated call_id appears on two distinct rows, each independently labelled.
    call_ids = [lbl.call_id for lbl in labels.values()]
    assert call_ids.count("C001") == 2

    # Labelled CSV: raw text/csv, original cols + Intent + Outcome, input order.
    csv_resp = api_client.get(f"/classify/jobs/{job_id}/labelled.csv")
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv_resp.headers["content-disposition"]
    out = pd.read_csv(io.StringIO(csv_resp.text))
    assert len(out) == n_rows
    assert list(out.columns[-2:]) == ["Intent", "Outcome"]
    # input order preserved: call_id column matches the original in order
    assert list(out["call_id"]) == list(fixture_df["call_id"])
    for val in out["Outcome"]:
        assert val in {"Positive", "Neutral", "Negative"}

    # --- Second run (idempotent resume) --------------------------------------
    counter["classify"] = 0
    counter["taxonomy"] = 0
    job_id_2 = _run_job(dataset_id)

    # No re-classification: no Gemini classify call, no taxonomy re-derivation.
    assert counter["classify"] == 0, "already-labelled rows must not be re-classified"
    assert counter["taxonomy"] == 0, "taxonomy must be reused on resume"
    # No new labels created.
    assert _count_labels(dataset_id) == n_rows

    prog2 = api_client.get(f"/classify/jobs/{job_id_2}").json()["data"]
    assert prog2["status"] == "done"
    assert prog2["classified_calls"] == n_rows


@pytest.mark.usefixtures("_require_llm_key")
def test_per_intent_summaries_and_cache(api_client, fixture_df, monkeypatch):
    """Every intent in the breakdown gets a non-empty narrative summary (real Gemini);
    resuming the same dataset+column+context returns the cached summaries with NO extra
    classification and NO extra summary Gemini calls."""
    n_rows = len(fixture_df)

    counter = {"classify": 0, "taxonomy": 0, "summarise": 0}
    lock = threading.Lock()
    orig_classify = classifier.classify_batch
    orig_taxonomy = classifier.derive_taxonomy
    orig_summarise = classifier.summarise_intent

    def counting_classify(*a, **k):
        with lock:
            counter["classify"] += 1
        return orig_classify(*a, **k)

    def counting_taxonomy(*a, **k):
        with lock:
            counter["taxonomy"] += 1
        return orig_taxonomy(*a, **k)

    def counting_summarise(*a, **k):
        with lock:
            counter["summarise"] += 1
        return orig_summarise(*a, **k)

    monkeypatch.setattr(classifier, "classify_batch", counting_classify)
    monkeypatch.setattr(classifier, "derive_taxonomy", counting_taxonomy)
    monkeypatch.setattr(classifier, "summarise_intent", counting_summarise)

    data = _upload()
    dataset_id = data["id"]

    # --- First run: labels + a summary per (non-sentinel) intent ---------------
    job_id = _run_job(dataset_id)
    assert counter["summarise"] >= 1, "expected at least one real per-intent summary call"

    res = api_client.get(f"/classify/jobs/{job_id}/results").json()["data"]
    breakdown = res["intent_breakdown"]
    assert breakdown, "expected a non-empty intent breakdown"
    # EVERY intent in the breakdown carries a non-empty summary string.
    for row in breakdown:
        assert "summary" in row, row
        assert isinstance(row["summary"], str)
        assert row["summary"].strip(), f"intent {row['intent']!r} has an empty summary"

    # One summary row persisted per distinct intent (idempotent by the cache key).
    from sqlalchemy.orm import Session

    distinct_intents = {row["intent"] for row in breakdown}
    with Session(session_module._engine) as s:
        summary_rows = s.query(IntentSummaryRow).filter(
            IntentSummaryRow.dataset_id == dataset_id,
            IntentSummaryRow.text_column == TEXT_COLUMN,
        ).all()
    assert {r.intent for r in summary_rows} == distinct_intents
    assert len(summary_rows) == len(distinct_intents), "one summary per distinct intent"

    # --- Second run (idempotent resume): cached summaries, no new Gemini work ---
    first_summaries = {r["intent"]: r["summary"] for r in breakdown}
    counter["classify"] = counter["taxonomy"] = counter["summarise"] = 0
    job_id_2 = _run_job(dataset_id)

    assert counter["classify"] == 0, "resume must not re-classify"
    assert counter["taxonomy"] == 0, "resume must not re-derive taxonomy"
    assert counter["summarise"] == 0, "resume must return cached summaries, not regenerate"

    res2 = api_client.get(f"/classify/jobs/{job_id_2}/results").json()["data"]
    cached = {r["intent"]: r["summary"] for r in res2["intent_breakdown"]}
    assert cached == first_summaries, "cached summaries must be returned unchanged on resume"

    # No duplicate summary rows created on resume.
    with Session(session_module._engine) as s:
        again = s.query(IntentSummaryRow).filter(
            IntentSummaryRow.dataset_id == dataset_id,
            IntentSummaryRow.text_column == TEXT_COLUMN,
        ).count()
    assert again == len(distinct_intents), "resume must not create duplicate summary rows"


@pytest.mark.usefixtures("_require_llm_key")
def test_classify_unknown_dataset_404(api_client):
    r = api_client.post(
        "/datasets/does-not-exist/classify", json={"text_column": TEXT_COLUMN}
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "not_found"


@pytest.mark.usefixtures("_require_llm_key")
def test_classify_bad_column_400(api_client):
    data = _upload()
    r = api_client.post(
        f"/datasets/{data['id']}/classify", json={"text_column": "NoSuchColumn"}
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "bad_column"


@pytest.mark.usefixtures("_require_llm_key")
def test_labelled_csv_not_ready_409(api_client):
    data = _upload()
    job = classify_domain.start_job(data["id"], TEXT_COLUMN, spawn=False)  # not run
    r = api_client.get(f"/classify/jobs/{job['job_id']}/labelled.csv")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "not_ready"


@pytest.mark.usefixtures("_require_llm_key")
def test_job_not_found_404(api_client):
    r = api_client.get("/classify/jobs/nope")
    assert r.status_code == 404


# --- Business-context grounding (real Gemini) ---------------------------------

@pytest.mark.usefixtures("_require_llm_key")
def test_business_context_grounds_classification(api_client, fixture_df):
    """With a lending business_context saved on the session, a run produces intent
    labels drawn from a context-tailored taxonomy and valid outcomes for every row."""
    n_rows = len(fixture_df)
    data = _upload()
    dataset_id, session_id = data["id"], data["session_id"]

    session_domain.set_business_context(session_id, LENDING_CONTEXT)
    context_hash = classifier.context_fingerprint(LENDING_CONTEXT)

    job_id = _run_job(dataset_id)

    prog = api_client.get(f"/classify/jobs/{job_id}").json()["data"]
    assert prog["status"] == "done", prog
    assert prog["classified_calls"] == n_rows
    assert prog["cost_usd"] > 0

    res = api_client.get(f"/classify/jobs/{job_id}/results").json()["data"]
    taxonomy = res["taxonomy"]
    assert taxonomy, "a context-tailored taxonomy must be present"
    assert taxonomy[-1] == "Other/Unclear"

    # Every label is a valid outcome and its intent comes from the taxonomy (or the
    # empty-transcript sentinel) — i.e. labels are consistent with the derived taxonomy.
    allowed_intents = set(taxonomy) | {classifier.NO_TRANSCRIPT_INTENT}
    for row in res["intent_breakdown"]:
        assert row["intent"] in allowed_intents, (row["intent"], taxonomy)
    for row in res["outcome_breakdown"]:
        assert row["outcome"] in {"Positive", "Neutral", "Negative"}

    # Labels were persisted under the lending context fingerprint.
    assert _count_labels(dataset_id, context_hash) == n_rows

    # The frustrated/unresolved complaint call (fixture row 7) reads Negative.
    from sqlalchemy.orm import Session

    with Session(session_module._engine) as s:
        by_index = {
            lbl.row_index: lbl
            for lbl in s.query(CallLabelRow)
            .filter(
                CallLabelRow.dataset_id == dataset_id,
                CallLabelRow.context_hash == context_hash,
            )
            .all()
        }
    assert by_index[7].outcome == "Negative", "clear complaint should be Negative"


@pytest.mark.usefixtures("_require_llm_key")
def test_changing_context_invalidates_cache_and_relabels(api_client, fixture_df):
    """Same context resumes (no re-bill); a CHANGED context is a fresh run that
    re-classifies every call (labels recomputed, not served stale)."""
    n_rows = len(fixture_df)

    counter = {"classify": 0, "taxonomy": 0}
    lock = threading.Lock()
    orig_classify = classifier.classify_batch
    orig_taxonomy = classifier.derive_taxonomy

    def counting_classify(*a, **k):
        with lock:
            counter["classify"] += 1
        return orig_classify(*a, **k)

    def counting_taxonomy(*a, **k):
        with lock:
            counter["taxonomy"] += 1
        return orig_taxonomy(*a, **k)

    classifier.classify_batch = counting_classify
    classifier.derive_taxonomy = counting_taxonomy
    try:
        data = _upload()
        dataset_id, session_id = data["id"], data["session_id"]

        # --- Run 1: lending context --------------------------------------------
        session_domain.set_business_context(session_id, LENDING_CONTEXT)
        hash_a = classifier.context_fingerprint(LENDING_CONTEXT)
        _run_job(dataset_id)
        run1_classify = counter["classify"]
        assert run1_classify >= 1
        assert _count_labels(dataset_id, hash_a) == n_rows

        # Re-run with the SAME context → resume, no re-classification, no re-bill.
        counter["classify"] = counter["taxonomy"] = 0
        _run_job(dataset_id)
        assert counter["classify"] == 0, "unchanged context must resume, not re-classify"
        assert counter["taxonomy"] == 0
        assert _count_labels(dataset_id, hash_a) == n_rows

        # --- Run 2: CHANGED context → fresh, context-aware run -----------------
        changed_context = (
            "We are a health-insurance TPA call center. Calls are about claims intake, "
            "pre-authorization, network hospitals, policy coverage and reimbursement "
            "status. A Negative outcome means a denied or delayed claim."
        )
        session_domain.set_business_context(session_id, changed_context)
        hash_b = classifier.context_fingerprint(changed_context)
        assert hash_b != hash_a

        counter["classify"] = counter["taxonomy"] = 0
        job_b = _run_job(dataset_id)

        # A changed context is NOT served from cache: it re-derives + re-classifies.
        assert counter["classify"] >= 1, "changed context must trigger re-classification"
        assert counter["taxonomy"] == 1, "changed context must derive a fresh taxonomy"

        # Fresh label set under the new fingerprint; the old set is untouched.
        assert _count_labels(dataset_id, hash_b) == n_rows
        assert _count_labels(dataset_id, hash_a) == n_rows
        # Two distinct context label sets now exist for the same dataset+column.
        assert _count_labels(dataset_id) == 2 * n_rows

        # The results for the changed-context job reflect the new taxonomy, not stale ones.
        res_b = api_client.get(f"/classify/jobs/{job_b}/results").json()["data"]
        assert res_b["total_calls"] == n_rows
        assert res_b["taxonomy"] and res_b["taxonomy"][-1] == "Other/Unclear"
        for row in res_b["outcome_breakdown"]:
            assert row["outcome"] in {"Positive", "Neutral", "Negative"}
    finally:
        classifier.classify_batch = orig_classify
        classifier.derive_taxonomy = orig_taxonomy
