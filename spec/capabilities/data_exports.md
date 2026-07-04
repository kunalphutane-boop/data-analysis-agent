# Capability: Data Exports (cleaned CSV, chart images)

> **Phase 3 — deferred.** Stub — detailed at build time for Phase 3.

## What It Does
Exports analysis artifacts: a cleaned CSV, chart images (PNG), for download.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| dataset_id / result | uuid / any | `POST /exports/*` | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| cleaned CSV | file | download |
| chart PNG | file | download |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| pandas | write cleaned CSV | 500 |
| headless chart renderer | render PNG | 500 |

## Business Rules
- Exports are new artifacts; source files are never modified (out of scope per roadmap).

## Error Cases
- Nothing to export → 400.

## Success Criteria
- [ ] Export endpoints return a valid cleaned CSV and a non-empty chart PNG.
