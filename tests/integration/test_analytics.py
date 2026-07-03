"""Integration tests for the analytics agent — REAL Gemini via AGENT_GEMINI_API_KEY.

Skips (never stubs) if no key is present. Uploads the >=10k-row fixture and asserts
the agent's computed numbers EXACTLY equal a direct pandas full-data computation.
"""
import io
from pathlib import Path

import pandas as pd
import pytest

from analysis.sandbox import run_code

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sales_10k.csv"


@pytest.fixture
def full_df():
    return pd.read_csv(FIXTURE)


def _upload_fixture(api_client) -> dict:
    content = FIXTURE.read_bytes()
    files = {"file": ("sales_10k.csv", io.BytesIO(content), "text/csv")}
    r = api_client.post("/datasets/upload", files=files)
    assert r.status_code == 200, r.text
    return r.json()["data"]


@pytest.mark.usefixtures("_require_llm_key")
def test_fixture_has_at_least_10k_rows(full_df):
    assert len(full_df) >= 10_000


@pytest.mark.usefixtures("_require_llm_key")
def test_upload_profile_matches_pandas(api_client, full_df):
    data = _upload_fixture(api_client)
    assert data["row_count"] == len(full_df)
    assert data["col_count"] == full_df.shape[1]
    cols = {c["name"]: c for c in data["profile"]["columns"]}
    assert cols["region"]["dtype"] == str(full_df["region"].dtype)
    # revenue has injected missing values
    assert cols["revenue"]["non_null"] == int(full_df["revenue"].notna().sum())
    assert len(data["profile"]["sample"]) <= 5


@pytest.mark.usefixtures("_require_llm_key")
def test_total_revenue_by_region_exact_match(api_client, full_df):
    """The agent's numbers must EXACTLY equal the full-data pandas groupby."""
    data = _upload_fixture(api_client)
    session_id = data["session_id"]
    dataset_id = data["id"]

    r = api_client.post(
        "/ask",
        json={
            "session_id": session_id,
            "dataset_id": dataset_id,
            "question": "What is the total revenue by region?",
        },
    )
    assert r.status_code == 200, r.text
    payload = r.json()["data"]

    # Full data envelope shape (api.md).
    for key in [
        "message_id", "answer", "generated_code", "steps",
        "input_tokens", "output_tokens", "cost_usd",
        "needs_clarification", "clarify_question", "error",
    ]:
        assert key in payload, f"missing {key}"

    assert payload["needs_clarification"] is False
    assert payload["error"] is None
    assert payload["generated_code"], "expected non-empty generated code"
    assert payload["input_tokens"] > 0
    assert payload["output_tokens"] > 0
    assert payload["cost_usd"] > 0
    assert isinstance(payload["steps"], list) and len(payload["steps"]) >= 1

    # Ground truth: full-data pandas groupby.
    expected = full_df.groupby("region")["revenue"].sum()

    # Re-execute the agent's EXACT generated code against the full DataFrame and
    # confirm it reproduces the pandas ground truth exactly.
    out = run_code(payload["generated_code"], full_df)
    assert out["ok"] is True, out["error"]
    result = out["result"]

    if isinstance(result, pd.Series):
        got = result
    elif isinstance(result, pd.DataFrame):
        # pick the revenue-bearing numeric column
        num = result.select_dtypes("number")
        got = num.iloc[:, 0]
        if result.index.name != "region" and "region" in result.columns:
            got = result.set_index("region").select_dtypes("number").iloc[:, 0]
    else:
        got = pd.Series(result)

    for region, exp_val in expected.items():
        assert region in got.index, f"{region} missing from agent result"
        assert got.loc[region] == pytest.approx(exp_val, rel=0, abs=1e-6)

    # The answer text must mention at least one region (grounded, not empty).
    assert any(region in payload["answer"] for region in expected.index)


@pytest.mark.usefixtures("_require_llm_key")
def test_ambiguous_question_asks_for_clarification(api_client):
    csv = (
        b"region,gross_revenue,net_revenue\n"
        b"West,1000,900\nEast,2000,1800\nWest,1500,1400\nEast,800,700\n"
    )
    files = {"file": ("ambig.csv", io.BytesIO(csv), "text/csv")}
    up = api_client.post("/datasets/upload", files=files)
    assert up.status_code == 200
    data = up.json()["data"]

    r = api_client.post(
        "/ask",
        json={
            "session_id": data["session_id"],
            "dataset_id": data["id"],
            "question": "What is the total revenue?",
        },
    )
    assert r.status_code == 200, r.text
    payload = r.json()["data"]
    assert payload["needs_clarification"] is True
    assert payload["clarify_question"]
    assert payload["answer"]  # surfaces the clarifying question


def _upload_transcript_csv(api_client) -> dict:
    """A small synthetic call-log with a free-text transcript column + repeated ids."""
    rows = [
        ("num1", "[CUSTOMER] I want to check my loan EMI due date || [AGENT] Sure"),
        ("num1", "[CUSTOMER] What is my next EMI payment amount || [AGENT] Let me check"),
        ("num2", "[CUSTOMER] I need my account balance and statement || [AGENT] Ok"),
        ("num3", "[CUSTOMER] The line is not audible, I cannot hear you || [AGENT] Sorry"),
        ("num4", "[CUSTOMER] I want to complete my registration verification || [AGENT] Sure"),
        ("num5", "[CUSTOMER] What are your branch timings today || [AGENT] 10 to 5"),
    ]
    header = "dialled_number,Conversation Log\n"
    body = "".join(f'{n},"{log}"\n' for n, log in rows)
    csv = (header + body).encode("utf-8")
    files = {"file": ("calls.csv", io.BytesIO(csv), "text/csv")}
    up = api_client.post("/datasets/upload", files=files)
    assert up.status_code == 200, up.text
    return up.json()["data"]


@pytest.mark.usefixtures("_require_llm_key")
def test_openended_intent_question_is_answered_not_clarified(api_client):
    """An open-ended 'reasons customers call, with %' over a transcript column must
    be answered best-effort (needs_clarification=False) with pandas code + percentages."""
    data = _upload_transcript_csv(api_client)
    r = api_client.post(
        "/ask",
        json={
            "session_id": data["session_id"],
            "dataset_id": data["id"],
            "question": "What are the main reasons customers call, with %?",
        },
    )
    assert r.status_code == 200, r.text
    payload = r.json()["data"]

    assert payload["needs_clarification"] is False, payload.get("clarify_question")
    assert payload["error"] is None
    assert payload["generated_code"], "expected non-empty generated pandas code"
    assert payload["answer"], "expected a non-empty answer"
    # A '% of calls' answer must surface percentage figures.
    assert "%" in payload["answer"], payload["answer"]


@pytest.mark.usefixtures("_require_llm_key")
def test_nonexistent_column_still_asks_for_clarification(api_client):
    """A question referencing columns that plainly do not exist must clarify."""
    data = _upload_transcript_csv(api_client)
    r = api_client.post(
        "/ask",
        json={
            "session_id": data["session_id"],
            "dataset_id": data["id"],
            "question": "What is the total revenue by region?",
        },
    )
    assert r.status_code == 200, r.text
    payload = r.json()["data"]
    assert payload["needs_clarification"] is True
    assert payload["clarify_question"]
    assert payload["answer"]


@pytest.mark.usefixtures("_require_llm_key")
def test_returns_grounded_answer_and_persists(api_client, full_df):
    """A normal ask exercises the full loop and persists a messages row."""
    data = _upload_fixture(api_client)
    r = api_client.post(
        "/ask",
        json={
            "session_id": data["session_id"],
            "dataset_id": data["id"],
            "question": "How many rows are there and what is the average revenue?",
        },
    )
    assert r.status_code == 200, r.text
    payload = r.json()["data"]
    assert payload["answer"]
    assert payload["error"] is None

    # Persisted with tokens + cost.
    from sqlalchemy.orm import Session
    from db import session as session_module
    from db.models import MessageRow

    with Session(session_module._engine) as s:
        msg = s.get(MessageRow, payload["message_id"])
        assert msg is not None
        assert msg.answer_text == payload["answer"]
        assert msg.cost_usd > 0
        assert msg.input_tokens > 0
