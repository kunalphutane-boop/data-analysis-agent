# Architecture

System design for the local, single-user data analytics agent. Product intent lives in [`roadmap.md`](roadmap.md); the agent graph in [`agent.md`](agent.md); the data model in [`data.md`](data.md); the HTTP contract in [`api.md`](api.md); the UI in [`ui.md`](ui.md).

---

## System Overview

A single technical user runs this tool on their own machine. A FastAPI server on `localhost:8001` serves both a JSON API and a statically-exported Next.js UI (mounted at `/app/`). The user uploads a CSV, the server profiles it locally with pandas and stores the profile in SQLite. When the user asks a natural-language question, a LangGraph agent plans the analysis, asks Google Gemini to generate pandas code, executes that code **locally** in a restricted sandbox against the real, full DataFrame, inspects the result, fixes-and-retries on error (bounded), and returns a plain-language answer plus the exact code, the analysis steps, and the token/USD cost. Raw data rows never leave the machine — Gemini sees only the schema and a small sample (default 5 rows).

## Component Map

```
                       Browser (Next.js static export @ /app/)
                                   │  fetch (JSON)
                                   ▼
        ┌──────────────────────────────────────────────────┐
        │  FastAPI server  (localhost:8001)                 │
        │  src/api/{health,sessions,datasets,ask}.py        │
        └───────┬───────────────────────┬──────────────────┘
                │                        │
        ┌───────▼────────┐      ┌────────▼─────────────────┐
        │ Domain services│      │  LangGraph agent          │
        │ src/domain/*   │      │  src/graph/{state,nodes,  │
        │ (session,      │      │  edges,agent,runner}.py   │
        │  dataset, ask) │      └───┬──────────────┬────────┘
        └───┬────────────┘          │              │
            │              ┌────────▼───┐   ┌───────▼────────────┐
     ┌──────▼──────┐       │ LLM client │   │ Sandbox executor   │
     │ Analysis    │       │ src/llm/*  │   │ src/analysis/      │
     │ src/analysis│       │  (Gemini)  │   │ sandbox.py         │
     │ loader,     │       └─────┬──────┘   │ restricted exec:   │
     │ profiler,   │             │          │ pd, np, df, result │
     │ storage     │        ┌────▼─────┐    └───────┬────────────┘
     └──────┬──────┘        │ Gemini   │            │
            │               │ API      │     pandas / numpy
     ┌──────▼──────────┐    │ (schema+ │            │
     │ SQLite (SQLAlch)│    │ sample   │     ┌──────▼──────────┐
     │ src/db/*        │    │ only)    │     │ data/uploads/   │
     │ sessions,       │    └──────────┘     │ raw CSV files   │
     │ datasets,       │                     │ (stay local)    │
     │ messages        │                     └─────────────────┘
     └─────────────────┘
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| **API** (`src/api/*`) | FastAPI routers; request validation; `ok(data)` / `api_error(code, message, status)` envelopes; static mount of the Next.js export at `/app/`. |
| **Domain** (`src/domain/*`) | Orchestrates a use-case: create session, upload+profile a dataset, run an ask. Owns DB transactions; calls analysis + graph layers. Keeps API thin. |
| **Agent graph** (`src/graph/*`) | LangGraph loop: plan → generate_code → execute_code → inspect → answer, with bounded error-fix retry and clarify-on-ambiguity. See [`agent.md`](agent.md). |
| **Analysis** (`src/analysis/*`) | `loader` (read CSV → DataFrame), `profiler` (schema/types/missing/ranges + sample), `sandbox` (restricted local code execution), `storage` (files under `data/uploads/`). No LLM here. |
| **LLM** (`src/llm/*`) | Provider-agnostic `LLMClient`; Gemini provider; token-usage capture; `pricing.py` cost table. |
| **Persistence** (`src/db/*`) | SQLAlchemy 2.0 models + session factory over SQLite. See [`data.md`](data.md). |
| **Observability** (`src/observability/*`) | Structured (structlog) request/response + per-node logging: prompt, output, latency, tokens, cost, errors. |

## Data Flow (upload → profile → ask → answer)

1. **Upload** — `POST /datasets/upload` (multipart CSV, optional `session_id`). `src/analysis/storage.py` writes the raw file under `data/uploads/<dataset_id>/<filename>`. `loader.py` reads it into a pandas DataFrame; `profiler.py` computes the profile (per-column type, non-null count, missing %, numeric min/max, a small sample). A `datasets` row is persisted with `profile_json`. Response returns the profile.
2. **Ask** — `POST /ask` (`session_id`, `dataset_id`, `question`). `src/domain/ask.py` loads the dataset from disk into a DataFrame, builds `load_context` (schema + sample), and invokes the LangGraph runner.
3. **Agent loop** — `plan` (Gemini decides the approach or flags ambiguity) → `generate_code` (Gemini emits pandas assigning a `result` variable) → `execute_code` (sandbox runs it locally on the full `df`) → `inspect` (route: on error and `retry_count < max_retries`, loop back to `generate_code` with the error text; on success, continue) → `answer` (Gemini writes the plain-language answer from the real `result`) → `finalize` (persist the `messages` row, tokens, cost).
4. **Output** — the API returns `{answer, generated_code, steps[], input_tokens, output_tokens, cost_usd, needs_clarification, clarify_question}`. The UI shows the answer, a collapsible **Show code**, the step list + counter, and a token/cost badge.

## Local code-execution sandbox (`src/analysis/sandbox.py`)

Generated pandas code is **never** trusted; it runs locally in a restricted `exec` with a curated namespace and no ambient capabilities.

- **Namespace (globals) provided:** `pd` (pandas), `np` (numpy), and `df` (the loaded DataFrame). Multi-DataFrame names (`df1`, `df2`, …) are Phase 3. `__builtins__` is replaced with a curated allow-list (safe builtins only: `len`, `range`, `min`, `max`, `sum`, `sorted`, `abs`, `round`, `enumerate`, `zip`, `list`, `dict`, `set`, `tuple`, `str`, `int`, `float`, `bool`, `print`) — **no** `open`, `eval`, `exec`, `compile`, `__import__`, `input`, `globals`, `locals`, `getattr`/`setattr` escapes.
- **No imports:** because `__import__` is removed, generated code cannot `import` anything beyond the injected `pd`/`np`. Filesystem and network are unreachable (no `open`, no `socket`, no `requests`).
- **Result contract:** the code must assign its answer to a designated `result` variable. After `exec`, the sandbox reads `result` from the local namespace. `print()` output is captured by redirecting stdout to an in-memory buffer and returned as `stdout`.
- **Per-exec timeout:** execution runs under a wall-clock timeout (default 15s, `AGENT_SANDBOX_TIMEOUT_SECONDS`) enforced by running the exec in a worker thread and abandoning it on timeout; on timeout the sandbox returns a timeout error.
- **Error capture → retry loop:** any exception is caught; the exception type + message + a trimmed traceback are returned as `execution_error`. The `inspect` node feeds that error back into `generate_code` (see [`agent.md`](agent.md)) so Gemini can fix the code, up to `max_retries` (default 3). Persistent failure returns a clear failure answer, never a guessed number.
- **Output shape:** `{ok: bool, result: Any, result_repr: str, stdout: str, error: str | None}`. `result_repr` is a truncated, display-safe string of `result` used to build the answer prompt.

## Data-privacy boundary

The LLM sees **only** metadata, never the raw dataset:

- **Sent to Gemini:** the schema (column names + inferred dtypes), aggregate profile stats (missing %, numeric ranges), and a small sample of rows (default 5, `AGENT_SAMPLE_ROWS`). The user's question. On retry, the prior code + the execution error.
- **Never sent:** the full DataFrame, the raw file, or any row beyond the sample. All computation runs locally in the sandbox against the full `df`; only the computed `result_repr` (already an aggregate/derived value in normal use) is sent to write the final answer.
- **File storage:** raw uploads live under `data/uploads/` on the local disk and are never transmitted. SQLite (`AGENT_DATABASE_URL`) stores metadata, profiles, and message history locally.

## Token & cost capture

- The Gemini provider (`src/llm/providers/gemini.py`) returns `usage_metadata` (prompt/candidates token counts) alongside the text; `LLMClient` surfaces `input_tokens` / `output_tokens` per call.
- The graph accumulates tokens across all Gemini calls in a run into `AgentState.input_tokens` / `output_tokens`.
- **Pricing table:** `src/llm/pricing.py` maps model id → USD per 1M input / output tokens; `cost_usd = input_tokens/1e6 * in_rate + output_tokens/1e6 * out_rate`. The per-query cost is returned by `/ask` and persisted on the `messages` row. Daily aggregation (`/cost/daily`) is Phase 2.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Google Gemini API | Plan, generate pandas, write the answer | On error/rate-limit: provider retries with backoff, then the run finalizes with a clear error surfaced to the UI (no stub path — tests use the real key from `.env`). |
| pandas / numpy | Local profiling + sandboxed computation | Code error → captured and fed into the bounded retry loop; profiling error → 400 on upload. |
| SQLite (via SQLAlchemy) | Local metadata/history store | Connection/migration failure → server startup fails loudly. |
| Local filesystem (`data/uploads/`) | Raw file storage | Write failure → 500 on upload. |

## Stack

> Concrete choices for **this** project. Generic rules (model-naming, DB driver, dev port, real-key tests) live in `harness/patterns/tech-stack.md`.

- **Language:** Python 3.11+ (backend), TypeScript (frontend).
- **Agent framework:** LangGraph — multi-step pipeline with conditional edges (bounded retry, clarify branch). See [`agent.md`](agent.md).
- **LLM provider + model:** Google Gemini via `src/llm/providers/gemini.py`. Default model **`gemini-2.0-flash`** (cheap, low-latency; overridable via `AGENT_LLM_MODEL`). API key `AGENT_GEMINI_API_KEY`. Provider auto-detected from whichever key is set (`src/llm/client.py`).
- **Backend:** FastAPI + uvicorn (`localhost:8001`).
- **Database + ORM:** SQLite + SQLAlchemy 2.0 (Mapped style), Alembic migrations. `AGENT_DATABASE_URL` (default `sqlite:///./data/agent.db`).
- **Frontend:** Next.js 15 + React 19, static export served by FastAPI at `/app/`.
- **Dependency management:** uv + `pyproject.toml` (backend); pnpm (frontend).

| Key library | Version | Purpose |
|-------------|---------|---------|
| langgraph | >=0.1 | Agent graph |
| google-genai | >=2.9 | Gemini client |
| fastapi / uvicorn | >=0.115 / >=0.30 | HTTP server |
| sqlalchemy / alembic | >=2.0 / >=1.13 | Persistence + migrations |
| pydantic / pydantic-settings | >=2.7 / >=2.3 | Validation + settings (`AGENT_` prefix) |
| pandas / numpy | latest | Profiling + sandboxed analysis |
| structlog | >=24.1 | Structured logging |
| Recharts | latest | Charts (Phase 2) |
| Playwright | latest | Frontend E2E (`frontend/tests/e2e/`) |

**Avoid:** any package that grants generated code filesystem/network/subprocess access; a hosted DB (this is local-only, SQLite); shipping raw rows to the LLM; SQLite-as-substitute for a stated prod DB (here SQLite **is** the stated store).

## Deployment Model

Local, single-user, long-running process. Source root is `src/` on `PYTHONPATH` (`pythonpath = ["src"]` in `pyproject.toml`); modules import as top-level (`from graph...`, `from analysis...`, `from db...`). Env vars use the `AGENT_` prefix and load from `.env`. Run with `uv run python -m src` (server on `:8001`); the handoff run command `uv run python -m src --run` performs migrations + frontend build + server start. No cloud, no auth, no multi-user.
