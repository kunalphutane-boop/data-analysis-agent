# Capability: Multi-Dataset (files, joins, folders)

> **Phase 3 — deferred.** Stub — detailed at build time for Phase 3.

## What It Does
Analyzes across multiple uploaded files (joins/compare) and treats a folder as one logical dataset.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| multiple files / folder | multipart | `POST /datasets/upload` (multi) | yes |
| question spanning datasets | str | `POST /ask` | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| join/compare answer | str | `/ask` response |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| pandas | multi-DataFrame merge/concat | error → bounded retry |
| Sandbox | multi-DataFrame namespace (`df1`, `df2`, …) | error → retry |

## Business Rules
- The sandbox namespace exposes multiple named DataFrames; planning becomes join-aware.
- A folder ingests as one dataset (concatenated/related files).

## Error Cases
- Incompatible join keys → clear failure answer after retries.

## Success Criteria
- [ ] A join question over two related CSVs returns a result matching a direct `pd.merge`.
- [ ] A folder of files is analyzable as one dataset.
