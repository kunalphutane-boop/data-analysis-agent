"""Unit tests for the Conversation Intelligence classifier + aggregation.

Network-free: the Gemini-facing `classify_batch` is exercised with a fake client that
returns canned text, so we test parsing/coercion/fallback logic deterministically.
The real-key end-to-end path is covered in tests/integration/test_conversation_intelligence.py.
"""
from __future__ import annotations

import io
import json
from types import SimpleNamespace

import numpy as np
import pytest

from analysis import classifier
from domain import classify as classify_domain


class _FakeClient:
    """Returns a queue of canned responses; records prompts. (text, in_tok, out_tok)."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = 0

    def call_with_usage(self, prompt, *, system=None):
        self.calls += 1
        text = self._responses.pop(0) if self._responses else ""
        return text, 100, 20


# --- pure helpers -------------------------------------------------------------

def test_is_blank():
    assert classifier.is_blank("")
    assert classifier.is_blank("   ")
    assert classifier.is_blank(None)
    assert classifier.is_blank(np.nan)
    assert classifier.is_blank(float("nan"))
    assert not classifier.is_blank("hello")
    assert not classifier.is_blank("[CUSTOMER] hi")


def test_coerce_outcome():
    assert classifier.coerce_outcome("Positive") == "Positive"
    assert classifier.coerce_outcome("Negative") == "Negative"
    assert classifier.coerce_outcome("Neutral") == "Neutral"
    # out-of-set -> Neutral
    assert classifier.coerce_outcome("Angry") == "Neutral"
    assert classifier.coerce_outcome("") == "Neutral"
    assert classifier.coerce_outcome(None) == "Neutral"
    assert classifier.coerce_outcome(42) == "Neutral"


def test_coerce_intent():
    tax = list(classifier.BASE_TAXONOMY)
    assert classifier.coerce_intent("EMI/Payment", tax) == "EMI/Payment"
    # unknown intent falls back to Other/Unclear
    assert classifier.coerce_intent("Something new", tax) == "Other/Unclear"
    assert classifier.coerce_intent(None, tax) == "Other/Unclear"


def test_normalise_taxonomy_keeps_full_base_set():
    tax = classifier.normalise_taxonomy(["Loan enquiry", "Fraud report"])
    for base in classifier.BASE_TAXONOMY:
        assert base in tax
    assert "Fraud report" in tax
    assert tax[-1] == "Other/Unclear"
    # No duplicates
    assert len(tax) == len(set(tax))


def test_normalise_taxonomy_handles_garbage():
    tax = classifier.normalise_taxonomy("not a list")
    assert tax == classifier.BASE_TAXONOMY


def test_normalise_taxonomy_context_mode_does_not_force_base():
    # With a business context (force_base=False) the model's domain labels are kept as-is,
    # not padded with the generic lending base set.
    tax = classifier.normalise_taxonomy(
        ["Loan enquiry", "Disbursement delay", "Collections/Overdue"], force_base=False
    )
    assert tax == [
        "Loan enquiry",
        "Disbursement delay",
        "Collections/Overdue",
        "Other/Unclear",
    ]
    # Generic-only base categories are NOT injected.
    assert "Branch/Timing" not in tax


def test_normalise_taxonomy_context_mode_falls_back_when_empty():
    tax = classifier.normalise_taxonomy([], force_base=False)
    assert tax == classifier.BASE_TAXONOMY


# --- business context fingerprint (cache key) ---------------------------------

def test_context_fingerprint_stable_and_empty_default():
    from db.models import EMPTY_CONTEXT_HASH

    assert classifier.context_fingerprint("") == EMPTY_CONTEXT_HASH
    assert classifier.context_fingerprint(None) == EMPTY_CONTEXT_HASH
    # Whitespace-only normalises to empty.
    assert classifier.context_fingerprint("   ") == EMPTY_CONTEXT_HASH
    # Deterministic + insensitive to surrounding whitespace.
    a = classifier.context_fingerprint("lending NBFC")
    assert a == classifier.context_fingerprint("  lending NBFC  ")
    # A different context yields a different fingerprint.
    assert a != classifier.context_fingerprint("insurance claims")


def test_business_context_injected_into_classify_prompt():
    tax = list(classifier.BASE_TAXONOMY)
    resp = json.dumps([{"call_index": 0, "intent": "EMI/Payment", "outcome": "Negative"}])
    client = _FakeClient([resp])
    client.systems: list = []
    orig = client.call_with_usage

    def _spy(prompt, *, system=None):
        client.systems.append(system)
        return orig(prompt, system=system)

    client.call_with_usage = _spy  # type: ignore[assignment]
    classifier.classify_batch(
        client, tax, [(0, "emi failed")], business_context="We are a lending NBFC."
    )
    # The injected block (with the user's verbatim text) is appended to the prompt.
    assert client.systems and "authored by the user" in client.systems[0]
    assert "We are a lending NBFC." in client.systems[0]


def test_no_business_context_leaves_prompt_unchanged():
    tax = list(classifier.BASE_TAXONOMY)
    resp = json.dumps([{"call_index": 0, "intent": "EMI/Payment", "outcome": "Neutral"}])
    client = _FakeClient([resp])
    client.systems = []
    orig = client.call_with_usage

    def _spy(prompt, *, system=None):
        client.systems.append(system)
        return orig(prompt, system=system)

    client.call_with_usage = _spy  # type: ignore[assignment]
    classifier.classify_batch(client, tax, [(0, "emi failed")])  # no context
    # The injected user block is absent (the static prompt may still mention the feature).
    assert client.systems and "authored by the user" not in client.systems[0]


def test_detect_call_id_column():
    assert classifier.detect_call_id_column(["call_id", "Conversation Log"]) == "call_id"
    assert classifier.detect_call_id_column(["dialled_number", "log"]) == "dialled_number"
    assert classifier.detect_call_id_column(["region", "revenue"]) is None


# --- classify_batch (parsing / coercion / retry) ------------------------------

def test_classify_batch_parses_and_coerces():
    tax = list(classifier.BASE_TAXONOMY)
    resp = json.dumps(
        [
            {"call_index": 0, "intent": "EMI/Payment", "outcome": "Negative"},
            {"call_index": 1, "intent": "MadeUpIntent", "outcome": "Ecstatic"},
        ]
    )
    client = _FakeClient([resp])
    result, it, ot = classifier.classify_batch(
        client, tax, [(0, "emi failed"), (1, "loan question")]
    )
    assert result[0] == ("EMI/Payment", "Negative")
    # out-of-set intent -> Other/Unclear, out-of-set outcome -> Neutral
    assert result[1] == ("Other/Unclear", "Neutral")
    assert it == 100 and ot == 20
    assert client.calls == 1


def test_classify_batch_retries_once_then_gives_up():
    tax = list(classifier.BASE_TAXONOMY)
    client = _FakeClient(["not json at all", "still not json"])
    result, it, ot = classifier.classify_batch(client, tax, [(0, "x")])
    assert result == {}
    assert client.calls == 2  # initial + one retry
    assert it == 200 and ot == 40  # tokens still accumulate across attempts


def test_classify_batch_recovers_on_retry():
    tax = list(classifier.BASE_TAXONOMY)
    good = json.dumps([{"call_index": 0, "intent": "Branch/Timing", "outcome": "Positive"}])
    client = _FakeClient(["garbage", good])
    result, _, _ = classifier.classify_batch(client, tax, [(0, "timings?")])
    assert result[0] == ("Branch/Timing", "Positive")
    assert client.calls == 2


# --- percentage + aggregation math --------------------------------------------

def test_pcts_sum_to_exactly_100():
    for counts, total in [
        ([1, 1, 1], 3),
        ([3120, 4200, 5022], 12342),
        ([1], 1),
        ([7, 0, 0], 7),
        ([1, 1, 1, 1, 1, 1, 1], 7),
    ]:
        pcts = classify_domain._pcts(counts, total)
        assert abs(sum(pcts) - 100.0) < 0.05, (counts, pcts)


def test_pcts_empty_total():
    assert classify_domain._pcts([0, 0], 0) == [0.0, 0.0]


def _label(intent, outcome):
    return SimpleNamespace(intent=intent, outcome=outcome)


def test_aggregate_breakdowns_and_cross_tab():
    labels = [
        _label("Verification/Registration", "Negative"),
        _label("Verification/Registration", "Negative"),
        _label("Verification/Registration", "Neutral"),
        _label("Loan enquiry", "Positive"),
        _label("EMI/Payment", "Negative"),
        _label("No transcript", "Neutral"),
    ]
    agg = classify_domain._aggregate(labels)
    assert agg["total_calls"] == 6

    # breakdowns sum to 100%
    assert abs(sum(b["pct"] for b in agg["intent_breakdown"]) - 100.0) < 0.1
    assert abs(sum(b["pct"] for b in agg["outcome_breakdown"]) - 100.0) < 0.1

    # counts are consistent
    assert sum(b["count"] for b in agg["intent_breakdown"]) == 6
    assert sum(b["count"] for b in agg["outcome_breakdown"]) == 6

    # cross_tab well-formed: positive+neutral+negative == total per intent
    grand = 0
    for row in agg["cross_tab"]:
        assert row["positive"] + row["neutral"] + row["negative"] == row["total"]
        grand += row["total"]
    assert grand == 6

    verify = next(r for r in agg["cross_tab"] if r["intent"] == "Verification/Registration")
    assert verify["negative"] == 2
    assert verify["neutral"] == 1
    assert verify["total"] == 3


# --- CSV column assembly (input order, two new columns) -----------------------

def test_export_csv_appends_intent_outcome_in_input_order(_isolated_db):
    from domain import dataset as dataset_domain
    from db.models import CallLabelRow, ClassificationJobRow
    from db.session import create_db_session

    csv = (
        b"call_id,Conversation Log\n"
        b'A,"[CUSTOMER] loan?"\n'
        b'B,"[CUSTOMER] emi failed"\n'
        b'C,""\n'
    )
    ds = dataset_domain.upload_dataset("calls.csv", csv, None)
    dataset_id = ds["id"]

    with create_db_session() as session:
        job = ClassificationJobRow(
            dataset_id=dataset_id,
            session_id=ds["session_id"],
            text_column="Conversation Log",
            status="done",
            total_calls=3,
            classified_calls=3,
            taxonomy_json=json.dumps(classifier.BASE_TAXONOMY),
        )
        session.add(job)
        session.flush()
        job_id = job.id
        rows = [
            (0, "A", "Loan enquiry", "Positive"),
            (1, "B", "EMI/Payment", "Negative"),
            (2, "C", "No transcript", "Neutral"),
        ]
        for ridx, cid, intent, outcome in rows:
            session.add(
                CallLabelRow(
                    job_id=job_id,
                    dataset_id=dataset_id,
                    text_column="Conversation Log",
                    row_index=ridx,
                    call_id=cid,
                    intent=intent,
                    outcome=outcome,
                )
            )

    csv_text, filename = classify_domain.export_labelled_csv(job_id)
    assert filename == "calls_labelled.csv"

    import pandas as pd

    out = pd.read_csv(io.StringIO(csv_text))
    assert list(out.columns[-2:]) == ["Intent", "Outcome"]
    assert list(out["Intent"]) == ["Loan enquiry", "EMI/Payment", "No transcript"]
    assert list(out["Outcome"]) == ["Positive", "Negative", "Neutral"]
    # original columns preserved, one row per input row in order
    assert list(out["call_id"]) == ["A", "B", "C"]


def test_export_not_ready_raises(_isolated_db):
    from domain import dataset as dataset_domain
    from db.models import ClassificationJobRow
    from db.session import create_db_session

    csv = b'call_id,Conversation Log\nA,"[CUSTOMER] hi"\n'
    ds = dataset_domain.upload_dataset("c.csv", csv, None)
    with create_db_session() as session:
        job = ClassificationJobRow(
            dataset_id=ds["id"],
            session_id=ds["session_id"],
            text_column="Conversation Log",
            status="classifying",
            total_calls=1,
            classified_calls=0,
        )
        session.add(job)
        session.flush()
        job_id = job.id
    with pytest.raises(classify_domain.NotReadyError):
        classify_domain.export_labelled_csv(job_id)
