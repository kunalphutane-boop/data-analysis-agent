"""API contract tests — no LLM key required (graph is not invoked here)."""
import io


def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "ok"


def test_create_session(api_client):
    r = api_client.post("/sessions", json={"title": "My analysis"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["title"] == "My analysis"
    assert data["id"]
    assert data["created_at"] and data["updated_at"]


def test_create_session_default_title(api_client):
    r = api_client.post("/sessions", json={})
    assert r.status_code == 200
    assert r.json()["data"]["title"] == "Untitled analysis"


# --- Business context (session-scoped, grounds Conversation Intelligence) ------

def test_business_context_defaults_empty(api_client):
    sid = api_client.post("/sessions", json={}).json()["data"]["id"]
    r = api_client.get(f"/sessions/{sid}/business_context")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["session_id"] == sid
    assert data["business_context"] == ""


def test_business_context_save_and_read_back(api_client):
    sid = api_client.post("/sessions", json={}).json()["data"]["id"]
    ctx = "We are a lending NBFC handling EMI, KYC and collections."
    put = api_client.put(
        f"/sessions/{sid}/business_context", json={"business_context": f"  {ctx}  "}
    )
    assert put.status_code == 200
    # Stored trimmed.
    assert put.json()["data"]["business_context"] == ctx

    got = api_client.get(f"/sessions/{sid}/business_context").json()["data"]
    assert got["business_context"] == ctx


def test_business_context_can_be_cleared(api_client):
    sid = api_client.post("/sessions", json={}).json()["data"]["id"]
    api_client.put(f"/sessions/{sid}/business_context", json={"business_context": "x"})
    api_client.put(f"/sessions/{sid}/business_context", json={"business_context": ""})
    assert api_client.get(f"/sessions/{sid}/business_context").json()["data"][
        "business_context"
    ] == ""


def test_business_context_unknown_session_404(api_client):
    assert api_client.get("/sessions/nope/business_context").status_code == 404
    r = api_client.put("/sessions/nope/business_context", json={"business_context": "y"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "not_found"


def test_upload_non_csv_rejected(api_client):
    files = {"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")}
    r = api_client.post("/datasets/upload", files=files)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "bad_file"


def test_upload_empty_csv_rejected(api_client):
    files = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
    r = api_client.post("/datasets/upload", files=files)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "bad_file"


def test_upload_small_csv_profiles(api_client):
    csv = b"region,revenue\nWest,100.0\nEast,200.5\nWest,\n"
    files = {"file": ("mini.csv", io.BytesIO(csv), "text/csv")}
    r = api_client.post("/datasets/upload", files=files)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["filename"] == "mini.csv"
    assert data["row_count"] == 3
    assert data["col_count"] == 2
    profile = data["profile"]
    cols = {c["name"]: c for c in profile["columns"]}
    assert cols["revenue"]["non_null"] == 2
    assert round(cols["revenue"]["missing_pct"], 2) == round(1 / 3 * 100, 2)
    assert cols["revenue"]["min"] == 100.0
    assert cols["revenue"]["max"] == 200.5
    assert cols["region"]["min"] is None
    assert len(profile["sample"]) <= 5


def test_get_dataset_not_found(api_client):
    r = api_client.get("/datasets/does-not-exist")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "not_found"


def test_ask_empty_question_rejected(api_client):
    r = api_client.post(
        "/ask",
        json={"session_id": "s", "dataset_id": "d", "question": "   "},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "bad_request"


def test_ask_unknown_session_404(api_client):
    r = api_client.post(
        "/ask",
        json={"session_id": "nope", "dataset_id": "nope", "question": "hi"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "not_found"


def test_ask_missing_fields_422(api_client):
    r = api_client.post("/ask", json={"question": "hi"})
    assert r.status_code == 422
