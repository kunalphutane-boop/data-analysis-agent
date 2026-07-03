# Agent

The LangGraph analysis loop. Stack + sandbox design in [`architecture.md`](architecture.md); the field names produced here match [`api.md`](api.md) and persist to the `messages` table in [`data.md`](data.md).

---

## Agent Architecture Pattern

**Chosen: Graph (LangGraph).** The flow is a multi-step pipeline with conditional edges — a bounded error-fix retry loop (execute → inspect → back to generate_code) and a clarify-on-ambiguity branch (plan → clarify → END). A plain loop cannot express these branches cleanly; a multi-agent setup is overkill for one user, one dataset, one question.

| Pattern | Use when |
|---------|----------|
| Single-agent loop | Deterministic tool loop, no branches |
| **Graph (LangGraph)** | Conditional edges, retry loops, branches ← **this** |
| Multi-agent / Supervisor | Multiple specialised roles |
| Human-in-the-loop | Pause for approval (clarify uses END-return, not a graph pause) |

---

## LLM Provider & Model

| Agent / Node | Provider | Model ID | Rationale |
|-------------|----------|----------|-----------|
| `plan` | Gemini | `gemini-2.0-flash` | Cheap, fast planning + ambiguity check |
| `generate_code` | Gemini | `gemini-2.0-flash` | Code gen from schema + sample; retries stay cheap |
| `answer` | Gemini | `gemini-2.0-flash` | Plain-language write-up of the real `result` |

Model is env-configurable via `AGENT_LLM_MODEL` (default `gemini-2.0-flash`); a stronger model can be set without code change. `execute_code`, `inspect`, `load_context`, `finalize` make **no** LLM call.

**Fallback behaviour:** provider-level retry/backoff on transient Gemini errors; on persistent failure the run finalizes with `error` set and a clear message surfaced via `/ask`. No offline/stub path — tests call real Gemini with `AGENT_GEMINI_API_KEY` from `.env`.

**Prompt strategy:** system/user split, one prompt file per node under `src/prompts/` (`plan.md`, `generate_code.md`, `answer.md`, `clarify.md`). `generate_code` instructs the model to return only Python assigning a `result` variable, using `pd`, `np`, `df`; on retry the prior code + `execution_error` are appended. `plan` returns structured JSON (`{plan, needs_clarification, clarify_question}`) parsed by the node.

---

## Tools & Tool Calling

This agent uses **code execution as its single tool**, not LLM function-calling. The model emits pandas code (a string); the node executes it in the local sandbox.

| Tool name | Description | Inputs | Output | Side-effects |
|-----------|-------------|--------|--------|--------------|
| `sandbox.run_code` | Execute generated pandas locally against the full `df` | `code: str`, `df: DataFrame` | `{ok, result, result_repr, stdout, error}` | None (no fs/network; in-memory only) |

**Tool selection strategy:** deterministic — every ask runs generate_code → execute_code. The LLM chooses *what* code to run, never *whether* to run a tool. **Tool failure handling:** captured error routes through `inspect` into the bounded retry loop (`max_retries`, default 3).

---

## Agent State

```python
class AgentState(TypedDict, total=False):
    # Identity / input
    run_id: str                     # message id for this ask; set at init
    session_id: str                 # set at init
    dataset_id: str                 # set at init
    question: str                   # set at init (user's NL question)

    # Context (load_context node — privacy boundary: schema + sample only)
    schema: dict                    # {column: dtype, ...}
    sample: list                    # first N rows (default 5) as records
    profile: dict                   # aggregate stats (missing %, ranges)
    messages: list                  # prior chat turns — [] in P1, threaded in P2

    # Planning
    plan: str                       # plan node's approach text
    needs_clarification: bool       # plan flagged an ambiguous question
    clarify_question: str           # question to ask the user (if ambiguous)

    # Code gen + execution
    generated_code: str             # latest pandas from generate_code
    execution_result: object        # the `result` value from the sandbox
    execution_result_repr: str      # display-safe repr fed to answer
    execution_stdout: str           # captured print() output
    execution_error: str | None     # exception text; drives retry
    retry_count: int                # incremented on each failed execute
    max_retries: int                # default 3; set at init

    # Output
    answer: str                     # plain-language answer (answer node)
    steps: list                     # [{step, label, status}] step trace + counter
    error: str | None               # fatal error (set by any node → handle_error)

    # Cost (accumulated across all Gemini calls)
    input_tokens: int
    output_tokens: int
    cost_usd: float
```

---

## Nodes / Steps

Files: `src/graph/state.py` (state), `src/graph/nodes.py` (nodes), `src/graph/edges.py` (routing fns), `src/graph/agent.py` (assembly), `src/graph/runner.py` (invoke + persist).

### `load_context` — REAL in P1
Reads: `dataset_id`, `session_id`. Writes: `schema`, `sample`, `profile`, `messages`, appends a `steps` entry. **No LLM.** Loads the dataset's DataFrame + profile; builds the privacy-bounded context (schema + sample of `AGENT_SAMPLE_ROWS`, default 5). In P1 `messages` is `[]`; P2 threads prior turns.

### `plan` — REAL in P1
Reads: `question`, `schema`, `sample`, `profile`, `messages`. Writes: `plan`, `needs_clarification`, `clarify_question`, tokens, `steps`. **LLM (Gemini).** Decides the analytical approach; if the question is ambiguous (unknown column, undefined metric), sets `needs_clarification=True` and a `clarify_question`. On failure sets `error`.

### `generate_code` — REAL in P1
Reads: `plan`, `schema`, `sample`, `question`, and (on retry) `generated_code` + `execution_error`. Writes: `generated_code`, tokens, `steps`. **LLM (Gemini).** Emits pandas assigning `result`, using `pd`/`np`/`df` only. On retry, includes the prior code and error so the model fixes it.

### `execute_code` — REAL in P1
Reads: `generated_code`, the DataFrame. Writes: `execution_result`, `execution_result_repr`, `execution_stdout`, `execution_error`, `steps`. **No LLM.** Runs `sandbox.run_code` locally (curated namespace, timeout). Captures success or error; never raises out.

### `inspect` — REAL in P1 (routing logic)
Reads: `execution_error`, `retry_count`, `max_retries`. Writes: `retry_count` (incremented on error), `steps`. **No LLM.** Pure router state prep; the conditional edge decides the next hop (see topology).

### `answer` — REAL in P1
Reads: `question`, `execution_result_repr`, `execution_stdout`, `plan`. Writes: `answer`, tokens, `steps`. **LLM (Gemini).** Writes the plain-language answer grounded in the real computed `result` — instructed never to invent numbers not present in the result.

### `enrich` — STUB in P1, REAL in P2
Reads: `execution_result`, `answer`. Writes: chart spec, follow-up suggestions, data-quality flags (P2). **In P1 a pass-through no-op node** so the graph shape is stable; P2 activates it (charts, follow-ups, quality flags — see [visual_outputs](capabilities/visual_outputs.md), [quality_insights](capabilities/quality_insights.md)).

### `finalize` — REAL in P1
Reads: all output fields. Writes: computes `cost_usd` from accumulated tokens via `src/llm/pricing.py`; persists the `messages` row; marks `steps` complete. **No LLM.**

### `clarify` — REAL in P1
Reads: `clarify_question`. Writes: `answer` (set to the clarifying question), `needs_clarification=True`. **No LLM** (question already produced by `plan`). Routes to END so the UI can prompt the user.

### `handle_error` — REAL in P1
Reads: `error`. Writes: `answer` (clear failure message), `steps` marked failed. Terminates.

---

## Graph / Flow Topology

```
START
  │
  ▼
load_context ──(error)──► handle_error ──► END
  │
  ▼
plan ──(error)──────────► handle_error ──► END
  │
  ├──(needs_clarification)──► clarify ──► END
  │
  ▼
generate_code ◄─────────────────────────┐
  │                                       │ (retry: error & retry_count < max_retries)
  ▼                                       │
execute_code                              │
  │                                       │
  ▼                                       │
inspect ──(error & retries left)──────────┘
  │
  ├──(error & retries exhausted)──► answer   (answer explains the failure)
  │
  ▼ (success)
answer
  │
  ▼
enrich  (no-op in P1)
  │
  ▼
finalize ──► END
```

**Conditional edges:**

| Source | Condition | Target |
|--------|-----------|--------|
| `load_context` | `state.get("error")` | `handle_error` |
| `load_context` | else | `plan` |
| `plan` | `state.get("error")` | `handle_error` |
| `plan` | `state.get("needs_clarification")` | `clarify` |
| `plan` | else | `generate_code` |
| `inspect` | `execution_error` and `retry_count < max_retries` | `generate_code` |
| `inspect` | else (success, or retries exhausted) | `answer` |

`generate_code → execute_code → inspect` are unconditional edges; `execute_code` always flows to `inspect`. `answer → enrich → finalize → END` are unconditional.

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| Within a run | LangGraph `AgentState` | schema, sample, plan, code, result, tokens |
| Across runs | SQLite `messages` (see [`data.md`](data.md)) | question, code, answer, steps, tokens, cost per turn |
| Conversation | `AgentState.messages` from prior `messages` rows | **P1: `[]` (single-shot).** P2: prior turns threaded into `plan`/`generate_code` for follow-ups |

**Context window management:** only schema + a small sample + the current question (+ prior turns in P2) are sent — inherently small. Sample size is `AGENT_SAMPLE_ROWS` (default 5).

---

## Error Handling & Recovery

**Node-level:** each node try/excepts; a fatal (non-code) error sets `state["error"]` and the conditional edge routes to `handle_error`. A **code execution** error is *not* fatal — it's captured in `execution_error` and drives the bounded retry.

**Graph-level (`handle_error`):** sets a clear failure `answer`, marks the current step failed; `finalize`/runner persists the `messages` row with `error`.

**Retry strategy:** the execute→inspect→generate_code loop retries up to `max_retries` (default 3, `AGENT_MAX_RETRIES`), each time feeding the error back to the model. On exhaustion, `answer` produces a plain-language failure explanation — never a guessed number.

**Partial failure:** the P2 `enrich` step (charts/follow-ups) degrades gracefully — if it fails, the core answer still returns.

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| Trace | One log context per run (`run_id`), one event per node | structlog → stdout (`src/observability/`) |
| LLM calls | model, prompt tokens, completion tokens, latency | Structured log + accumulated into state |
| Code exec | code, ok/error, retry_count, latency, timeout | Structured log |
| Run outcome | status, total tokens, `cost_usd`, error | DB (`messages`) + structured log |

Wired from Phase 1 — observability is never deferred.

---

## Concurrency Model

- **Run isolation:** one ask per request; each invocation is scoped by its own `run_id` (the `messages` id). Single-user tool — no cross-run contention.
- **Parallel nodes within a run:** none; the pipeline is sequential (the retry loop is inherently serial).
- **Sandbox execution** runs in a worker thread to enforce the wall-clock timeout.
- **Checkpointing:** none (runs are short; no human-in-the-loop pause).

---

## Graph Assembly (`src/graph/agent.py`)

```python
graph = StateGraph(AgentState)

for name, fn in [
    ("load_context", load_context), ("plan", plan),
    ("generate_code", generate_code), ("execute_code", execute_code),
    ("inspect", inspect), ("answer", answer), ("enrich", enrich),
    ("clarify", clarify), ("finalize", finalize), ("handle_error", handle_error),
]:
    graph.add_node(name, fn)

graph.set_entry_point("load_context")

graph.add_conditional_edges(
    "load_context",
    lambda s: "handle_error" if s.get("error") else "plan",
)
graph.add_conditional_edges(
    "plan",
    lambda s: "handle_error" if s.get("error")
    else "clarify" if s.get("needs_clarification")
    else "generate_code",
)
graph.add_edge("generate_code", "execute_code")
graph.add_edge("execute_code", "inspect")
graph.add_conditional_edges(
    "inspect",
    lambda s: "generate_code"
    if s.get("execution_error") and s.get("retry_count", 0) < s.get("max_retries", 3)
    else "answer",
)
graph.add_edge("answer", "enrich")
graph.add_edge("enrich", "finalize")
graph.add_edge("finalize", END)
graph.add_edge("clarify", END)
graph.add_edge("handle_error", END)

agentic_ai = graph.compile()
```
