# Capability: Visual Outputs (charts + tables)

> **Phase 2.** Frontend-first, no-LLM approach: the graph serializes the executed
> result to a structured table; the frontend renders that table and auto-picks a
> simple chart from it.

## What It Does
Renders each `/ask` answer with a **summary table** of the executed pandas result and, when the shape suits, an **auto-picked bar chart** — alongside the plain-language answer. Deterministic and free: no extra Gemini call.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| execution_result | any (DataFrame / Series / scalar / dict / list) | agent graph (`state.execution_result`) | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| summary table | JSON `{columns, rows, row_count, truncated}` (rows/cols capped at 50×20; cells JSON-safe; NaN → null) | `/ask` response `table` field |
| auto chart | rendered client-side from `table` (no server field) | UI (`AnswerDisplay`) |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| — | none; the `enrich` node builds the table by pure serialization (no LLM) | on any serialization error the node returns no table — the answer is unaffected |

## Business Rules
- The graph's `enrich` node (P1 no-op) activates to serialize `execution_result` into a capped, JSON-safe `table` (DataFrame → columns+rows incl. a non-default index; Series/dict → key/value; list-of-dicts → union columns; scalar → single cell). No Gemini call.
- **Best-effort:** table-building never raises out — a non-tabular result or an execution error simply yields `table: null`, and the plain answer is unchanged.
- The frontend renders the table always (when present) and **auto-picks a bar chart** only when the table has a distinct label column + a numeric value column and ≤ 30 rows (bars sorted by value, capped at 15); otherwise it shows the table alone. Reuses the shared dependency-free chart primitives (no Recharts).

## Error Cases
- Non-tabular / non-chartable result → `table` may still render (e.g. a scalar) but no chart; a truly unusable result → `table: null`, answer only.
- Execution error or clarify → `table: null`.

## Success Criteria
- [ ] A grouped/aggregated answer (e.g. revenue by region) returns a `table` with the right columns/rows and the UI renders both the table and an auto-picked bar chart.
- [ ] A scalar answer (e.g. a single total) returns a one-cell `table` and no chart.
- [ ] A serialization failure or execution error still returns the plain answer with `table: null` — the answer is never blocked.
