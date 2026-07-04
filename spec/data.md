# Data Model

SQLite persistence for the local analytics agent. Storage tech + privacy boundary in [`architecture.md`](architecture.md); entities are produced/consumed by the agent graph in [`agent.md`](agent.md) and the endpoints in [`api.md`](api.md).

---

## Storage Technology

SQLite via SQLAlchemy 2.0 (Mapped style), Alembic migrations. `AGENT_DATABASE_URL` (default `sqlite:///./data/agent.db`). Models live in `src/db/models.py`; the analytics tables are added in migration `alembic/versions/0002_analytics.py`. Raw uploaded files are **not** stored in the DB — they live on disk under `data/uploads/` and are referenced by `datasets.filepath`.

IDs are UUID strings (matching the existing `RunRow` convention). Timestamps are timezone-aware UTC.

---

## Entities

### Entity: `sessions`

A named workspace the user returns to across days. In P1 exactly one session is created on demand; the sidebar that lists/renames/switches sessions is Phase 2.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) PK | yes | Primary key |
| title | str | yes | Display name (default e.g. "Untitled analysis") |
| created_at | datetime (UTC) | yes | Creation time |
| updated_at | datetime (UTC) | yes | Last activity; bumped on new message |

**P1 populates:** all columns. **P2 uses:** `title` rename, `updated_at` ordering for the sidebar.

### Entity: `datasets`

An uploaded CSV plus its computed profile. Belongs to a session.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) PK | yes | Primary key |
| session_id | str FK→sessions.id | yes | Owning session |
| filename | str | yes | Original upload filename |
| filepath | str | yes | Local path under `data/uploads/<id>/<filename>` |
| row_count | int | yes | Rows in the DataFrame |
| col_count | int | yes | Columns in the DataFrame |
| profile_json | JSON (Text) | yes | Full profile: per-column `{name, dtype, non_null, missing_pct, min, max}` + sample rows + row/col counts |
| created_at | datetime (UTC) | yes | Upload time |

**P1 populates:** all columns. Multi-dataset / folder ingestion is Phase 3 (adds no schema change — more `datasets` rows per session; a Phase 3 migration may add a `group_id`/`kind` for folders).

### Entity: `messages`

One row per ask (a conversation turn). Stores the question, the exact executed code, the answer, the step trace, and token/cost.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) PK | yes | Primary key; equals the graph `run_id` |
| session_id | str FK→sessions.id | yes | Owning session |
| dataset_id | str FK→datasets.id | yes | Dataset the question ran against |
| role | str | yes | `"user"` question + `"assistant"` answer collapsed into one turn row (role=`"turn"`), or two rows — see note |
| question | str | yes | The user's natural-language question |
| generated_code | str \| null | no | The exact pandas that produced the answer |
| answer_text | str \| null | no | Plain-language answer |
| steps_json | JSON (Text) | no | `[{step, label, status}]` — the step list + counter shown in the UI |
| input_tokens | int | no | Prompt tokens across all Gemini calls in the run |
| output_tokens | int | no | Completion tokens across the run |
| cost_usd | float | no | Estimated USD via `src/llm/pricing.py` |
| error | str \| null | no | Failure text if the run could not answer |
| created_at | datetime (UTC) | yes | Ask time (used for `/cost/daily` aggregation in P2) |

> **Assumed:** one `messages` row per ask with `role="turn"` holding both the question and the assistant answer (simplest for a single-shot P1). P2 conversation reads these rows in `created_at` order to thread `AgentState.messages`; if two-row (user/assistant) modeling proves cleaner for chat rendering, P2 may split it — a Phase 2 migration decision, not a P1 concern.

**P1 populates:** all columns except future-only ones. **P2 uses:** `created_at` for daily cost, ordered reads for conversation memory.

### Entity: `classification_jobs` (Phase 4)

A background Conversation Intelligence run over one dataset's transcript column. One row per classify job. Added in migration `alembic/versions/0003_conversation_intelligence.py` (down_revision `0002`).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) PK | yes | Job id (returned to the client and polled) |
| dataset_id | str FK→datasets.id | yes | Dataset being classified |
| session_id | str FK→sessions.id | yes | Owning session (from the dataset) |
| text_column | str | yes | The transcript column being read (e.g. `Conversation Log`) |
| status | str | yes | `pending` → `deriving_taxonomy` → `classifying` → `done` \| `error` |
| total_calls | int | yes | Rows to classify |
| classified_calls | int | yes | Rows labelled so far (drives the progress bar) |
| taxonomy_json | JSON (Text) | no | The derived fixed Intent list, reused on resume |
| input_tokens | int | yes | Prompt tokens accumulated across taxonomy + all batches (default 0) |
| output_tokens | int | yes | Completion tokens accumulated (default 0) |
| cost_usd | float | yes | Running cost via `src/llm/pricing.py` (default 0.0) |
| error | str \| null | no | Failure text if the job errored |
| started_at | datetime (UTC) | yes | Job start (used for elapsed) |
| updated_at | datetime (UTC) | yes | Bumped as each batch completes |

### Entity: `call_labels` (Phase 4)

One row per classified call. Keyed for idempotent resume by `(dataset_id, text_column, row_index)` (unique constraint), so a re-run skips already-labelled rows.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) PK | yes | Primary key |
| job_id | str FK→classification_jobs.id | yes | Job that last wrote this label |
| dataset_id | str FK→datasets.id | yes | Dataset (part of the idempotency key) |
| text_column | str | yes | Transcript column classified (part of the idempotency key) |
| row_index | int | yes | 0-based row position in the dataset (the stable per-call key) |
| call_id | str \| null | no | The dataset's own call id if present (metadata only; may repeat across rows) |
| intent | str | yes | Intent from the fixed taxonomy, `No transcript`, or `Unclassified` |
| outcome | str | yes | `Positive` \| `Neutral` \| `Negative` |
| created_at | datetime (UTC) | yes | Label time |

**Unique constraint:** `(dataset_id, text_column, row_index)`. **Index:** `(dataset_id, text_column)` for the results aggregation + resume lookup.

> **Assumed:** each **row** is labelled once by its `row_index`; a repeated `call_id` across rows is stored as metadata but does not collapse rows (every row gets its own label). Intent for empty transcripts is `No transcript`; malformed/failed batches fall back to `Unclassified` with `Outcome="Neutral"` so outcome is always in `{Positive,Neutral,Negative}`.

### Concept: `annotations` (Phase 2)

User notes on a dataset column (e.g. "revenue is net of refunds") that enrich planning/quality flags. Introduced in Phase 2 as table `annotations` (`id`, `dataset_id` FK, `column_name`, `note`, `created_at`) via a Phase 2 migration (`0003_*`). Not created in Phase 1.

---

## Relationships

- `sessions 1 ──< datasets` (a session has many datasets; P1 typically one).
- `sessions 1 ──< messages` (a session has many turns).
- `datasets 1 ──< messages` (each ask targets one dataset).
- `datasets 1 ──< annotations` (Phase 2).
- `datasets 1 ──< classification_jobs` (Phase 4); `classification_jobs 1 ──< call_labels`; `datasets 1 ──< call_labels` (Phase 4).

---

## Data Lifecycle

- **Create:** `sessions` on first use; `datasets` + raw file on upload (profile computed synchronously); `messages` on each ask (persisted in `finalize`).
- **Update:** `sessions.updated_at` on new activity; `sessions.title` on rename (P2). Datasets and messages are immutable once written.
- **Delete:** no automated deletion in P1 (local single-user tool). Manual DB/file cleanup only.

## Sensitive Data

The user's raw data never enters the DB — only schema, aggregate profile stats, and a small sample (default 5 rows) inside `profile_json`. **Phase 4 exception:** `call_labels` stores derived `intent`/`outcome` labels (not transcript text) in the DB; the raw transcripts stay on disk under `data/uploads/`, but transcript **text** is sent to Gemini for classification — the user's explicit, scoped choice for that feature (see [`architecture.md`](architecture.md)). Raw files stay on the local disk under `data/uploads/`. No auth/PII of third parties; the tool is bound to `localhost` for one user. See the privacy boundary in [`architecture.md`](architecture.md).
