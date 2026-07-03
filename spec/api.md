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

## Phase 4 — Conversation Intelligence endpoints (REAL in Phase 4)

Routers live in `src/api/classify.py`, registered in `src/api/__init__.py`. All use the same `ok(data)` / `api_error(code, message, status)` envelope. The classify job runs as an in-process background async task; the client polls the progress endpoint. See [`capabilities/conversation_intelligence.md`](capabilities/conversation_intelligence.md) and [`agent.md`](agent.md).

### `GET /sessions/{session_id}/business_context`
**Purpose:** read the session's saved free-text **business context** — a user-authored description of their domain that grounds the Conversation Intelligence Intent taxonomy + Outcome judgments. `""` when unset.
**Response (200):**
```json
{"data": {"session_id": "uuid", "business_context": "We are a lending NBFC; this call center handles loan servicing, EMI, KYC/verification, disbursement and collections."}, "error": null}
```
**Errors:** 404 `not_found` (unknown session).

### `PUT /sessions/{session_id}/business_context`
**Purpose:** save (replace) the session's business context. Trimmed on save. Reused automatically on every subsequent classify run; a **changed** value re-labels on the next run (it is part of the classification cache key), an unchanged value resumes with no re-bill.
**Request:** `{"business_context": "string (may be empty to clear)"}`
**Response (200):** same shape as the GET (the stored, trimmed value).
**Errors:** 404 `not_found` (unknown session), 500 (DB failure).

### `POST /datasets/{id}/classify`
**Purpose:** start a Conversation Intelligence job for a dataset's transcript column (idempotent/resumable — reuses existing labels). The job automatically picks up the session's saved **business context** and injects it into both classification prompts; the context's fingerprint is part of the resume/cache key (same dataset + column + context → resume, no re-bill; changed context → a fresh run with fresh, context-aware labels).
**Request:** `{"text_column": "Conversation Log"}` (the transcript column; the frontend auto-detects a `"Conversation Log"` column and defaults the picker to it).
**Response (200):**
```json
{"data": {"job_id": "uuid", "dataset_id": "uuid", "text_column": "Conversation Log",
          "status": "pending", "total_calls": 12342, "classified_calls": 0}, "error": null}
```
**Errors:** 404 `not_found` (unknown dataset), 400 `bad_column` (column absent from the dataset schema), 500.

### `GET /classify/jobs/{job_id}`
**Purpose:** poll progress (drives the progress bar + running cost).
**Response (200):**
```json
{"data": {
  "job_id": "uuid", "status": "classifying",
  "total_calls": 12342, "classified_calls": 4800,
  "percent": 38.9, "elapsed_seconds": 72.4,
  "input_tokens": 210334, "output_tokens": 18422, "cost_usd": 0.0731,
  "error": null
}, "error": null}
```
`status` ∈ `pending` | `deriving_taxonomy` | `classifying` | `done` | `error`.
**Errors:** 404 `not_found`.

### `GET /classify/jobs/{job_id}/results`
**Purpose:** fetch the aggregated results (available while `classifying`; final at `done`).
**Response (200):**
```json
{"data": {
  "job_id": "uuid", "status": "done", "total_calls": 12342,
  "taxonomy": ["Loan enquiry", "EMI/Payment", "Account balance/Statement",
               "Verification/Registration", "Branch/Timing", "Complaint/Escalation", "Other/Unclear"],
  "intent_breakdown": [{"intent": "Loan enquiry", "count": 3120, "pct": 25.3,
                        "summary": "Customers mostly ask about eligibility and interest rates... resolves largely Positive."}],
  "outcome_breakdown": [{"outcome": "Positive", "count": 5010, "pct": 40.6},
                         {"outcome": "Neutral", "count": 4200, "pct": 34.0},
                         {"outcome": "Negative", "count": 3132, "pct": 25.4}],
  "cross_tab": [{"intent": "Verification/Registration",
                 "positive": 40, "neutral": 60, "negative": 233, "total": 333}],
  "input_tokens": 540221, "output_tokens": 41233, "cost_usd": 0.191
}, "error": null}
```
`intent_breakdown` and `outcome_breakdown` `pct` fields each sum to 100 (±0.1). In each `cross_tab` row `positive + neutral + negative == total`. Each `intent_breakdown` row also carries a `summary` — a concise (~2-4 sentence) narrative for that intent (what customers call about, how the calls resolve given the outcome mix, notable patterns), generated once per intent by Gemini and cached with the run (same dataset+column+context resumes and returns the cached summaries with no new Gemini calls; a changed `business_context` refreshes them). `summary` is `""` while a run is still classifying / before summaries are generated.
**Errors:** 404 `not_found`.

### `GET /classify/jobs/{job_id}/labelled.csv`
**Purpose:** download the full labelled dataset — all original columns plus `Intent` and `Outcome`, one row per input row in input order.
**Response (200):** `text/csv` streamed (`Content-Disposition: attachment; filename="<original>_labelled.csv"`). This is **not** enveloped — it is a raw CSV body.
**Errors:** 404 `not_found`, 409 `not_ready` (job not yet `done`).

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
