# Capability: Report Generation

> **Phase 3 — deferred.** Stub — detailed at build time for Phase 3.

## What It Does
Compiles a shareable analysis document (Markdown/HTML/PDF) summarizing the questions, answers, code, and charts from a session.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| session_id | uuid | `POST /reports` | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| analysis document | MD/HTML/PDF | download / preview |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite | read session `messages` | 500 |
| renderer | build the document | 500 |

## Business Rules
- The document compiles the session's turns (question, answer, code, cost, charts) into one artifact.

## Error Cases
- Empty session → 400.

## Success Criteria
- [ ] `POST /reports` returns a non-empty document that opens correctly and reflects the session's analyses.
