# Capability: Dataset Upload & Auto-Profile

## What It Does
Accepts a CSV upload, stores the raw file locally, and computes a full column-level profile (types, missing values, numeric ranges, a small sample) persisted for later questions.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| file | multipart CSV | `POST /datasets/upload` | yes |
| session_id | uuid | form field (created if absent) | no |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| dataset record | JSON | API response (`api.md` upload shape) |
| profile | JSON (columns, sample, counts) | `datasets.profile_json` + response |
| raw file | file on disk | `data/uploads/<dataset_id>/<filename>` |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Local filesystem | write raw CSV | 500 `write_failed` |
| pandas | `read_csv` → profile | 400 `bad_file` (unparseable/empty) |
| SQLite | insert `datasets` (+ `sessions` if new) | 500 |

## Business Rules
- Only CSV in Phase 1; target up to ~100 MB; larger → 413 `file_too_large`.
- Profile per column: `name`, `dtype`, `non_null`, `missing_pct`, and `min`/`max` for numeric columns (null for non-numeric).
- Sample is the first `AGENT_SAMPLE_ROWS` rows (default 5) — this is the only row-level data ever exposed to the LLM.
- Raw rows never leave the machine (privacy boundary, see `architecture.md`).
- Profiling reads the full file, not a sample, so `row_count`/`col_count` are exact.

## Error Cases
- Non-CSV / corrupt / empty → 400 `bad_file` with a clear message; nothing persisted.
- Oversized file → 413 `file_too_large`.
- Disk write / DB failure → 500; partial file cleaned up.

## Success Criteria
- [ ] Uploading a valid CSV returns 200 with every column's dtype, non-null count, missing %, and numeric min/max.
- [ ] `row_count`/`col_count` exactly match the file (verified against a direct `pd.read_csv`).
- [ ] The raw file exists under `data/uploads/<id>/` and a `datasets` row with `profile_json` is persisted.
- [ ] An unparseable upload returns 400 and writes no `datasets` row.
- [ ] The profile `sample` contains at most `AGENT_SAMPLE_ROWS` rows.
