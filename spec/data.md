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

### Concept: `annotations` (Phase 2)

User notes on a dataset column (e.g. "revenue is net of refunds") that enrich planning/quality flags. Introduced in Phase 2 as table `annotations` (`id`, `dataset_id` FK, `column_name`, `note`, `created_at`) via a Phase 2 migration (`0003_*`). Not created in Phase 1.

---

## Relationships

- `sessions 1 ──< datasets` (a session has many datasets; P1 typically one).
- `sessions 1 ──< messages` (a session has many turns).
- `datasets 1 ──< messages` (each ask targets one dataset).
- `datasets 1 ──< annotations` (Phase 2).

---

## Data Lifecycle

- **Create:** `sessions` on first use; `datasets` + raw file on upload (profile computed synchronously); `messages` on each ask (persisted in `finalize`).
- **Update:** `sessions.updated_at` on new activity; `sessions.title` on rename (P2). Datasets and messages are immutable once written.
- **Delete:** no automated deletion in P1 (local single-user tool). Manual DB/file cleanup only.

## Sensitive Data

The user's raw data never enters the DB — only schema, aggregate profile stats, and a small sample (default 5 rows) inside `profile_json`. Raw files stay on the local disk under `data/uploads/`. No auth/PII of third parties; the tool is bound to `localhost` for one user. See the privacy boundary in [`architecture.md`](architecture.md).
