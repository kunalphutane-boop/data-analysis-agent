# API

FastAPI contract for the local analytics agent. This is the contract the frontend slice codes against (see [`ui.md`](ui.md)); field names match the agent output in [`agent.md`](agent.md) and the entities in [`data.md`](data.md).

---

## API Style

REST over JSON on `localhost:8001`. Every response uses the skeleton envelope: success → `{"data": <payload>, "error": null}` via `ok(data)`; failure → `{"code", "message"}` at `detail` with an HTTP status via `api_error(code, message, status)` (see `src/api/_common.py`). Routers live under `src/api/*` and are registered in `src/api/__init__.py`.

The statically-exported Next.js UI is mounted at **`/app/`** (StaticFiles). The API base for the frontend is same-origin (`""`) — e.g. `fetch("/ask", …)`.

## Authentication

None. Local single-user tool bound to `localhost:8001`. No tokens, no CORS beyond same-origin.

---

## Phase 1 — REAL endpoints

### `GET /health`
**Purpose:** liveness check. **Response:** `{"data": {"status": "ok"}, "error": null}`.

### `POST /sessions`
**Purpose:** create a session (workspace).
**Request:** `{"title": "string (optional; default 'Untitled analysis')"}`
**Response (200):**
```json
{"data": {"id": "uuid", "title": "Untitled analysis",
          "created_at": "iso8601", "updated_at": "iso8601"}, "error": null}
```
**Errors:** 500 (DB failure).

### `POST /datasets/upload`
**Purpose:** upload a CSV, store it locally, compute the full profile, persist a `datasets` row.
**Request:** `multipart/form-data` — `file` (the CSV), `session_id` (optional form field; if omitted a session is created).
**Response (200):**
```json
{"data": {
  "id": "uuid",
  "session_id": "uuid",
  "filename": "sales.csv",
  "row_count": 10000,
  "col_count": 7,
  "profile": {
    "row_count": 10000,
    "col_count": 7,
    "columns": [
      {"name": "region", "dtype": "object", "non_null": 10000,
       "missing_pct": 0.0, "min": null, "max": null},
      {"name": "revenue", "dtype": "float64", "non_null": 9987,
       "missing_pct": 0.13, "min": 0.0, "max": 98421.55}
    ],
    "sample": [{"region": "West", "revenue": 1200.0}]
  }
}, "error": null}
```
**Errors:** 400 `bad_file` (not a CSV / unparseable / empty), 413 `file_too_large` (> ~100 MB), 500.

### `GET /datasets/{id}`
**Purpose:** fetch a dataset + its stored profile (for reload).
**Response (200):** same `data` shape as upload (id, session_id, filename, row_count, col_count, profile).
**Errors:** 404 `not_found`.

### `POST /ask`
**Purpose:** run one natural-language question through the agent graph against the dataset's full data.
**Request:**
```json
{"session_id": "uuid", "dataset_id": "uuid", "question": "What is total revenue by region?"}
```
**Response (200):**
```json
{"data": {
  "message_id": "uuid",
  "answer": "Total revenue by region: West 1.2M, East 0.9M, ...",
  "generated_code": "result = df.groupby('region')['revenue'].sum()",
  "steps": [
    {"step": 1, "label": "Plan", "status": "done"},
    {"step": 2, "label": "Generate code", "status": "done"},
    {"step": 3, "label": "Execute", "status": "done"},
    {"step": 4, "label": "Answer", "status": "done"}
  ],
  "input_tokens": 812,
  "output_tokens": 143,
  "cost_usd": 0.00021,
  "needs_clarification": false,
  "clarify_question": null,
  "error": null
}, "error": null}
```
When the question is ambiguous, the graph returns `needs_clarification: true` and `clarify_question: "Which revenue column — gross or net?"` with `answer` set to that clarifying question and empty `generated_code`. When execution fails after all retries, `error` holds a plain-language failure and `answer` explains it.
**Errors:** 400 `bad_request` (missing fields), 404 `not_found` (unknown session/dataset), 500.

These field names (`answer`, `generated_code`, `steps`, `input_tokens`, `output_tokens`, `cost_usd`, `needs_clarification`, `clarify_question`) are exactly what the graph in [`agent.md`](agent.md) produces and what the UI in [`ui.md`](ui.md) renders.

---

## Phase 2 / 3 — FUTURE endpoints (labelled, not built in P1)

| Endpoint | Phase | Purpose |
|----------|-------|---------|
| `GET /sessions` | 2 | List sessions for the sidebar (id, title, updated_at) |
| `GET /sessions/{id}/messages` | 2 | Conversation transcript for a session (ordered turns) |
| `PATCH /sessions/{id}` | 2 | Rename a session |
| `GET /cost/daily` | 2 | Aggregate `cost_usd` per calendar day (running total) |
| `POST /datasets/{id}/annotations` | 2 | Add/update a column annotation |
| `GET /cost/daily`, chart-spec in `/ask` | 2 | `/ask` gains a `chart` spec + `follow_ups[]` + `quality_flags[]` in `data` |
| `POST /datasets/upload` (multi/folder) | 3 | Multi-file + folder ingestion |
| `POST /exports/cleaned-csv`, `/exports/chart-image` | 3 | Export artifacts |
| `POST /reports` | 3 | Generate a shareable report (MD/HTML/PDF) |

Phase 2 extends the `/ask` `data` payload additively (new fields), so the P1 contract stays backward-compatible.
