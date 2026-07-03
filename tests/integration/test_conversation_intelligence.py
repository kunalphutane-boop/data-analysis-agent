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
from db.models import CallLabelRow, ClassificationJobRow
from domain import classify as classify_domain
from domain import dataset as dataset_domain

FIXTURE = Path(__file__).parent.parent / "fixtures" / "transcripts_synthetic.csv"
TEXT_COLUMN = "Conversation Log"


@pytest.fixture
def fixture_df():
    return pd.read_csv(FIXTURE)


def _upload() -> dict:
    return dataset_domain.upload_dataset("transcripts.csv", FIXTURE.read_bytes(), None)


def _run_job(dataset_id: str) -> str:
    job = classify_domain.start_job(dataset_id, TEXT_COLUMN, spawn=False)
    asyncio.run(classifier.run_classification(job["job_id"]))
    return job["job_id"]


def _count_labels(dataset_id: str) -> int:
    from sqlalchemy.orm import Session

    with Session(session_module._engine) as s:
        return (
            s.query(CallLabelRow)
            .filter(
                CallLabelRow.dataset_id == dataset_id,
                CallLabelRow.text_column == TEXT_COLUMN,
            )
            .count()
        )


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
