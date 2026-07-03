# Capability: Visual Outputs (charts + tables)

> **Phase 2.** Stub — detailed at build time for Phase 2.

## What It Does
Renders answers as interactive charts and summary tables when the result is chartable, driven by a chart spec the agent emits.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| execution_result | any | agent graph | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| chart spec | JSON (Recharts/Vega-Lite-ready) | `/ask` response `chart` field |
| summary table | JSON | `/ask` response |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini (`enrich` node) | derive a chart spec from the result | degrade: return answer without chart |

## Business Rules
- The `enrich` node (P1 no-op) activates to emit a chart spec + summary table; the frontend renders with Recharts.
- Chart generation is best-effort — a failure never blocks the core answer.

## Error Cases
- Non-chartable result → no chart, table only.

## Success Criteria
- [ ] A grouped/aggregated answer returns a chart spec that renders in the UI plus a summary table.
- [ ] Chart-spec failure still returns the plain answer.
