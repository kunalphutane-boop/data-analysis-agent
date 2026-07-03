# Capability: Conversation & Persistent Sessions

> **Phase 2.** Stub — detailed at build time for Phase 2.

## What It Does
Threads multi-turn conversation with memory (follow-ups like "now break that down by month") and lets the user return to named, persisted sessions across days.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| session_id | uuid | `POST /ask`, `GET /sessions/{id}/messages` | yes |
| question (follow-up) | str | `POST /ask` | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| context-aware answer | str | `/ask` response |
| session list / transcript | JSON | `GET /sessions`, `GET /sessions/{id}/messages` |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite | read prior `messages` in order; list/rename `sessions` | 500 |
| Gemini | plan/code with prior turns in context | retry then error |

## Business Rules
- Prior `messages` (ordered by `created_at`) are threaded into `AgentState.messages` so follow-ups resolve references to earlier answers.
- Sessions can be listed, switched, and renamed (`GET /sessions`, `PATCH /sessions/{id}`).

## Error Cases
- Unknown session → 404. Empty history → behaves as a first turn.

## Success Criteria
- [ ] A follow-up that references a prior answer uses that context and reconciles numerically to it.
- [ ] Reopening the app lists prior sessions and restores the transcript.
