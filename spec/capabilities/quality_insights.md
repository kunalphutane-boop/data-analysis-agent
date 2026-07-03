# Capability: Quality Insights & Cost Transparency

> **Phase 2.** Stub — detailed at build time for Phase 2.

## What It Does
Surfaces data-quality flags (missing values, outliers, type oddities), auto follow-up suggestions, and a running daily cost total alongside the per-query cost.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| profile / result | JSON / any | dataset profile + agent result | yes |
| date | date | server clock | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| quality_flags | list | `/ask` response |
| follow_ups | list | `/ask` response |
| daily cost total | float | `GET /cost/daily` |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite | sum `messages.cost_usd` by day | 500 |
| Gemini (`enrich`) | derive flags + follow-ups | degrade gracefully |

## Business Rules
- Data-quality flags derive from the profile + result; follow-ups from the `enrich` node.
- `GET /cost/daily` aggregates `messages.cost_usd` grouped by `created_at` calendar day.

## Error Cases
- Enrichment failure → answer returns without flags/follow-ups.

## Success Criteria
- [ ] Data-quality flags appear for a dataset with missing values/outliers.
- [ ] The daily cost total equals the sum of that day's per-query `cost_usd`.
- [ ] Follow-up chips appear and, when clicked, pre-fill the question box.
