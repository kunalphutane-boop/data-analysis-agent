# Roadmap

Local, single-user data analytics agent. See [`architecture.md`](architecture.md) for the stack and the code-execution sandbox, [`agent.md`](agent.md) for the LangGraph loop, and [`capabilities/index.md`](capabilities/index.md) for the capability list.

---

## What This Agent Does

A local, browser-based data analytics agent for one technical user analyzing their own spreadsheets ad-hoc. The user uploads a CSV/Excel file (up to ~100 MB), the agent auto-profiles it (columns, types, ranges, missing values), and the user asks questions in plain English. The agent **plans**, **generates pandas/Python**, **executes that code locally against the real data**, **inspects the result**, **fixes and retries on error (bounded)**, and answers in plain language — always showing the exact code it ran and the token/cost of the query. Every number the user sees comes from real computation on their data, never from the model guessing.

## Who Uses It

A single technical user (data analyst / engineer / founder) working with their own spreadsheets on their own machine. They are comfortable reading code and act on the numbers, so correctness and transparency matter more than hand-holding. They return to sessions across days to continue and compare analyses.

## Core Problem Being Solved

Ad-hoc spreadsheet analysis today means either writing pandas by hand for every question or pasting data into a chatbot that hallucinates numbers. This agent gives the speed of natural language with the correctness of executed code — the user asks in English, real pandas runs locally against the full dataset, and the answer is backed by inspectable code and cost.

## Success Criteria

- [ ] Uploading a CSV (up to ~100 MB) returns a correct profile: every column with its inferred type, min/max (numeric), non-null count, and missing %.
- [ ] A natural-language question produces an answer whose numbers **exactly match** the same computation run directly with pandas on the full dataset (not a sample).
- [ ] The exact executed pandas code is shown to the user (collapsible), and the per-query input/output token counts and estimated USD cost are displayed.
- [ ] When generated code errors, the agent fixes and retries up to a bounded limit and still returns a correct answer (or a clear failure), without the user re-asking.
- [ ] Raw data rows never leave the machine — only schema + a small sample (default 5 rows) is sent to Gemini; all computation runs locally.

## What This Agent Does NOT Do (Out of Scope)

- No multi-user, auth, or cloud/hosted deployment — it is a local single-user tool bound to `localhost:8001`.
- No database/warehouse connectors — file uploads (CSV/Excel/folder) only.
- No write-back to source files; the agent reads uploaded copies and produces new export artifacts.
- No arbitrary shell/network/filesystem access from generated code — the sandbox forbids it (see [`architecture.md`](architecture.md)).
- No fine-tuning or training; it uses Gemini via API only.
- No scheduled/automated runs — every analysis is user-triggered from the browser.

## Key Constraints

- **LLM:** Google Gemini via the existing `src/llm/providers/gemini.py`, key `AGENT_GEMINI_API_KEY`. Cheap model by default; keep per-query cost low by sending schema + small sample only.
- **Local only:** server on port 8001, SQLite at `AGENT_DATABASE_URL`, files stored under `data/uploads/`.
- **File size:** target up to ~100 MB per file; profiling and execution must stay within a single machine's memory.
- **Correctness over cleverness:** answers must come from executed code; a bounded retry loop fixes errors rather than guessing.
- **Privacy:** raw rows stay local; only schema + a small configurable sample is sent to the LLM.

---

## Capabilities

| Phase | Capability | File |
|-------|-----------|------|
| 1 | Dataset upload & auto-profile | [`capabilities/dataset_upload_profile.md`](capabilities/dataset_upload_profile.md) |
| 1 | Local code-execution sandbox | [`capabilities/code_execution_sandbox.md`](capabilities/code_execution_sandbox.md) |
| 1 | Analytical Q&A (plan→code→execute→answer) | [`capabilities/analytical_qa.md`](capabilities/analytical_qa.md) |
| 2 | Conversation & persistent sessions | [`capabilities/conversation_sessions.md`](capabilities/conversation_sessions.md) |
| 2 | Visual outputs (charts + tables) | [`capabilities/visual_outputs.md`](capabilities/visual_outputs.md) |
| 2 | Quality insights & cost transparency | [`capabilities/quality_insights.md`](capabilities/quality_insights.md) |
| 3 | Multi-dataset (files, joins, folders) | [`capabilities/multi_dataset.md`](capabilities/multi_dataset.md) |
| 3 | Data exports (cleaned CSV, chart images) | [`capabilities/data_exports.md`](capabilities/data_exports.md) |
| 3 | Report generation | [`capabilities/document_generation.md`](capabilities/document_generation.md) |
| 4 | Conversation Intelligence (per-call Intent + Outcome classification) | [`capabilities/conversation_intelligence.md`](capabilities/conversation_intelligence.md) |

---

## Phases of Development

> **Phase 1 is the smallest first-time-right user-testable win.** Its backend is minimal but REAL on the one core path (real file, real pandas execution, real Gemini). Its frontend is visually complete: real UI for upload → profile → ask → answer + code + cost, PLUS clearly-labelled NON-FUNCTIONAL stubs for everything coming later (charts, sessions sidebar, follow-ups, quality flags, exports, daily-cost total, multi-file). Later phases wire those stubs into real features.

### Phase 1 — Upload → profile → ask one question (real execution)

- **Goal:** The user uploads one CSV, sees a correct auto-profile, types one natural-language question, and gets a plain-language answer backed by pandas actually executed on the full dataset — with the executed code (collapsible), the analysis steps (with a step counter), and the per-query token/cost shown. Real file, real sandbox, real Gemini.
- **Independent slices (parallel build units):**
  - `backend` (backend) — deps: none. DB models (sessions/datasets/messages) + Alembic migration; upload+profile; the local sandbox executor; the full LangGraph loop (load_context → plan → generate_code → execute_code → inspect → answer → finalize, with the bounded error-fix retry wired); Gemini prompts + token/cost capture; `/sessions`, `/datasets/upload`, `/datasets/{id}`, `/ask` endpoints; unit + integration tests. Codes the API contract in [`api.md`](api.md).
  - `frontend` (frontend) — deps: none. Upload dropzone, profile panel, question box, answer display with collapsible code, step list + counter, per-query token/cost badge, and all labelled NON-FUNCTIONAL stubs; Playwright E2E smoke. Codes against the API contract in [`api.md`](api.md) — no dependency on backend source, only on the documented envelope.
- **Key surfaces / files:**
  - backend: `src/db/models.py`, `alembic/versions/0002_analytics.py`, `src/analysis/{loader,profiler,sandbox,storage}.py`, `src/graph/{state,nodes,edges,agent,runner}.py`, `src/prompts/{plan,generate_code,answer,clarify}.md`, `src/llm/providers/gemini.py` (extend for usage), `src/llm/pricing.py`, `src/api/{sessions,datasets,ask}.py`, `src/api/__init__.py` (register routers), `src/domain/{session,dataset,ask}.py`, `tests/unit/**`, `tests/integration/test_analytics.py`, `tests/fixtures/sales_10k.csv`.
  - frontend: `frontend/src/app/page.tsx`, `frontend/src/components/**`, `frontend/src/lib/api.ts`, `frontend/tests/e2e/smoke.spec.ts`, `frontend/playwright.config.ts`, `frontend/package.json` (add Playwright).
- **Gate command:** `uv run alembic upgrade head && uv run pytest && (cd frontend && pnpm install && pnpm build && pnpm exec playwright test)` — runs against the real Gemini key in `.env` and the production SQLite driver. The integration test uploads `tests/fixtures/sales_10k.csv` (≥10,000 rows so a sampled answer ≠ a full-data answer) and asserts the agent's numeric answer **exactly equals** the pandas-computed full-data value. The Playwright smoke starts the real server (`uv run python -m src`) and drives upload → ask → answer in the browser.
- **How the user tests it (handoff seed):** Run `uv run python -m src --run` (migrations + frontend build + server), open `http://localhost:8001/app/`. Drag in a CSV → the **Profile panel** fills with real columns/types/missing/ranges. Type e.g. "What is the total revenue by region?" → click **Ask**. Watch the **step counter** advance (Plan → Generate code → Execute → Answer), read the plain-language answer, click **Show code** to see the exact pandas, and see the **token/cost** badge. Labelled stubs (greyed, "Coming soon"): left **Sessions** sidebar, **Charts** area, **Follow-up suggestions**, **Data-quality flags**, **Export** buttons, **Add file**, **Daily cost total**, column **annotation** editing — these are intentionally non-functional in Phase 1.

### Phase 2 — Conversation, charts & insight (wire the stubs)

- **Goal:** Turn the single-shot tool into a working analytics companion: multi-turn conversation with memory ("now break that down by month"), persistent sessions the user returns to across days, interactive charts + summary tables for answers, auto follow-up suggestions, data-quality flags, and full running cost transparency (per-query + daily total). Delivers ≥3 capabilities: [conversation_sessions](capabilities/conversation_sessions.md), [visual_outputs](capabilities/visual_outputs.md), [quality_insights](capabilities/quality_insights.md).
- **Independent slices (parallel build units):**
  - `backend` (backend) — deps: none. Conversation history threaded through `AgentState.messages` and persisted; `/sessions` list + `/sessions/{id}/messages`; column annotations endpoint; chart-spec generation node (agent emits a Vega-Lite/Recharts-ready spec + summary table); data-quality + follow-up enrichment node (activate the P1 `enrich` stub); `/cost/daily` aggregate. Owns `src/graph/*`, `src/analysis/charts.py`, `src/api/*`, new migration `0003_*`.
  - `frontend` (frontend) — deps: none (codes to the extended [`api.md`](api.md) contract). Sessions sidebar (create/switch/rename), multi-turn chat transcript, chart rendering (Recharts), summary tables, follow-up chips, data-quality panel, running daily-cost total, annotation editor.
- **Key surfaces / files:** backend `src/graph/nodes.py`, `src/analysis/charts.py`, `src/api/{sessions,ask,cost,annotations}.py`, `alembic/versions/0003_*.py`, tests; frontend `frontend/src/components/**`, `frontend/src/app/page.tsx`, `frontend/tests/e2e/*.spec.ts`.
- **Gate command:** `uv run alembic upgrade head && uv run pytest && (cd frontend && pnpm build && pnpm exec playwright test)` — integration test asserts a second turn ("break that down by month") uses prior context and returns a monthly breakdown whose totals reconcile to the first answer; a chart-spec is returned and rendered; daily cost sums per-query costs.
- **How the user tests it (handoff seed):** Ask a question, then a follow-up that references it — the answer respects prior context. See a chart + table render. Click a follow-up chip. Reopen the app later and pick the session from the sidebar to continue. Watch the daily-cost total climb.

### Phase 3 — Multiple datasets & exports

- **Goal:** Analyze across multiple files (joins/compare) and treat a folder as one dataset; export cleaned CSVs, chart images, and a shareable analysis report. Delivers ≥3 capabilities: [multi_dataset](capabilities/multi_dataset.md), [data_exports](capabilities/data_exports.md), [report_generation](capabilities/document_generation.md).
- **Independent slices (parallel build units):**
  - `backend` (backend) — deps: none. Multi-file upload + folder ingestion; multi-DataFrame sandbox namespace (`df1`, `df2`, … / named); join-aware planning; export endpoints (cleaned CSV, chart PNG via a headless renderer, report as Markdown/HTML/PDF). Owns `src/analysis/{loader,sandbox,export}.py`, `src/api/{datasets,exports,reports}.py`, migration `0004_*`.
  - `frontend` (frontend) — deps: none. Multi-file manager, dataset picker per question, export/report buttons wired, report preview.
- **Key surfaces / files:** backend `src/analysis/export.py`, `src/api/exports.py`, `src/api/reports.py`; frontend `frontend/src/components/**`.
- **Gate command:** `uv run alembic upgrade head && uv run pytest && (cd frontend && pnpm build && pnpm exec playwright test)` — integration test uploads two related CSVs, asks a join question, and asserts the joined result matches a direct pandas merge; export endpoints return a valid cleaned CSV and a non-empty chart PNG and a report file.
- **How the user tests it (handoff seed):** Upload two files, ask a question spanning both, verify the join answer; download the cleaned CSV, a chart image, and a report and confirm they open correctly.

### Phase 4 — Conversation Intelligence (per-call Intent + Outcome classification)

- **Goal:** On a loaded call-center dataset with free-text transcripts, the user clicks **Analyze conversations**, picks the transcript column (auto-detected to `"Conversation Log"`), watches a live progress bar with count + elapsed + running cost while Gemini reads **every** call, then sees an **Intent breakdown**, an **Outcome breakdown** (Positive/Neutral/Negative), an **Outcome-by-intent cross-tab** table, and downloads a **labelled CSV** with two new `Intent`/`Outcome` columns. The job is resumable/idempotent — a re-run does not re-classify already-labelled calls. Real transcripts, real Gemini, real SQLite. Delivers the [conversation_intelligence](capabilities/conversation_intelligence.md) capability.
  > This capability is a single, cohesive vertical (classifier service + job endpoints + results UI) rather than three loosely-related capabilities. It is a deliberate add-a-capability increment on top of the completed Phases 1–3, not a fresh requirements phase, so the ≥3-capabilities-per-phase heuristic (for greenfield requirements phases) does not apply here.
- **Independent slices (parallel build units):**
  - `backend` (backend) — deps: none. Owns all of `src/` + the migration + backend tests. Delivers: `classification_jobs` + `call_labels` tables and Alembic migration `0003_conversation_intelligence.py` (down_revision `0002`); the async batch classifier service `src/analysis/classifier.py` (taxonomy derivation → batched, bounded-concurrency Gemini classification → incremental persist → aggregation); the classification prompts under `src/prompts/`; the domain orchestrator `src/domain/classify.py` (start job, run in background, read progress/results, stream CSV); the FastAPI router `src/api/classify.py` registered in `src/api/__init__.py`; new `AGENT_`-prefixed settings in `src/config/settings.py`; unit + integration tests. Codes the contract in [`api.md`](api.md).
  - `frontend` (frontend) — deps: none (codes only to the [`api.md`](api.md) contract — no dependency on backend source). Delivers: an **Analyze conversations** action on a loaded dataset with a transcript-column picker (auto-detect `"Conversation Log"`); a progress bar with count + elapsed + running cost polling `GET /classify/jobs/{job_id}`; a results panel rendering the intent breakdown, outcome breakdown, and cross-tab table; a **Download labelled CSV** button hitting `GET /classify/jobs/{job_id}/labelled.csv` (wire the previously-stubbed Export button for this labelled CSV); Playwright E2E. Other stubs (charts, sessions sidebar) stay stubbed.
- **Key surfaces / files:**
  - backend: `src/db/models.py` (add `ClassificationJobRow`, `CallLabelRow`), `alembic/versions/0003_conversation_intelligence.py`, `src/analysis/classifier.py`, `src/domain/classify.py`, `src/api/classify.py`, `src/api/__init__.py` (register router), `src/prompts/{derive_taxonomy,classify_calls}.md`, `src/config/settings.py`, `tests/unit/test_classifier.py`, `tests/integration/test_conversation_intelligence.py`, `tests/fixtures/transcripts_synthetic.csv`.
  - frontend: `frontend/src/components/ConversationIntelligence.tsx` (+ progress/results subcomponents), `frontend/src/app/page.tsx` (wire the action), `frontend/src/lib/api.ts` (new endpoints), `frontend/tests/e2e/conversation_intelligence.spec.ts`.
- **Gate command:** `uv run alembic upgrade head && uv run pytest tests/integration/test_conversation_intelligence.py -q && uv run pytest && (cd frontend && pnpm install && pnpm build && pnpm exec playwright test)` — runs against the real `AGENT_GEMINI_API_KEY` in `.env` and the production SQLite driver. The integration test classifies `tests/fixtures/transcripts_synthetic.csv` (recognizable intents + clear positive/negative tone + one EMPTY transcript + one REPEATED `call_id`) and asserts: every row gets an `intent` and an `outcome` in `{Positive,Neutral,Negative}`; the empty-transcript row is `No transcript`/`Neutral` with no Gemini call; intent + outcome breakdowns each sum to 100%; the cross-tab is well-formed (`positive+neutral+negative==total` per intent); the exported CSV has the two new columns in input order; and a **second** classify run creates **no** new `call_labels` rows and makes **no** classification Gemini call for already-labelled rows (idempotency).
- **How the user tests it (handoff seed):** Run `uv run python -m src --run`, open `http://localhost:8001/app/`, upload the call-center CSV (e.g. `Test Data/Data/Transcript_Calls_Apr_Jun26_Modified.csv`). Click **Analyze conversations**, confirm the column picker defaults to **Conversation Log**, click start. Watch the **progress bar** climb (calls classified / total, elapsed, running cost). When it finishes, read the **Intent breakdown**, the **Outcome breakdown** (Positive/Neutral/Negative), and the **Outcome-by-intent cross-tab** table (e.g. "Verification calls 70% Negative"), then click **Download labelled CSV** and confirm the file has `Intent` + `Outcome` columns on every row. Re-click **Analyze conversations** on the same dataset/column and confirm it completes near-instantly without re-billing (resume). Still stubbed: charts area, sessions sidebar — intentionally non-functional.
