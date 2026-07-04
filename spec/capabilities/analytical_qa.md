# Capability: Analytical Q&A (plan → code → execute → answer)

## What It Does
Turns a natural-language question into a plain-language answer backed by pandas actually executed on the full dataset, showing the exact code, the analysis steps, and the per-query token/cost — with a bounded error-fix retry and clarify-on-ambiguity.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| session_id | uuid | `POST /ask` | yes |
| dataset_id | uuid | `POST /ask` | yes |
| question | str | `POST /ask` | yes |
| schema + sample | derived | `load_context` from the dataset | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| answer | str | `/ask` response + `messages.answer_text` |
| generated_code | str | `/ask` response + `messages.generated_code` |
| steps | list | `/ask` response + `messages.steps_json` |
| input_tokens/output_tokens/cost_usd | int/int/float | `/ask` response + `messages` |
| needs_clarification/clarify_question | bool/str | `/ask` response |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini | plan / generate_code / answer | provider retry/backoff; then finalize with clear error |
| Sandbox | execute generated pandas | error → bounded retry (`max_retries`, default 3) |
| SQLite | persist `messages` | 500 |

## Business Rules
- The graph is `load_context → plan → generate_code → execute_code → inspect → answer → enrich(no-op P1) → finalize` with the retry loop and clarify branch defined in [`agent.md`](agent.md).
- Every number in the answer comes from the executed `result` — the answer prompt forbids inventing values not present in the result.
- On execution error with retries left, the error is fed back to `generate_code`; on exhaustion, `answer` explains the failure (never a guessed number).
- On an ambiguous question, `plan` sets `needs_clarification` and the graph returns a `clarify_question` instead of an answer.
- Only schema + sample (default 5 rows) + the question are sent to Gemini — never the full data.
- Tokens are accumulated across all Gemini calls; `cost_usd` is computed via `src/llm/pricing.py`.

## Error Cases
- Unknown session/dataset → 404.
- Gemini unavailable after retries → answer is a clear failure message, `error` set, `messages` persisted.
- Code fails all retries → failure answer explaining what went wrong.
- Ambiguous question → clarify prompt (not an error).

## Success Criteria
- [ ] For a question like "total revenue by region", the numeric answer **exactly equals** the same computation run directly with pandas on the full ≥10,000-row fixture (not a sample).
- [ ] The response includes the exact executed `generated_code`, a `steps[]` trace with a counter, and non-zero `input_tokens`/`output_tokens`/`cost_usd`.
- [ ] Injecting a first-attempt code error still yields a correct final answer within `max_retries` (verified in an integration test), with `steps` reflecting the retry.
- [ ] An ambiguous question returns `needs_clarification=true` with a non-empty `clarify_question` and no fabricated answer.
- [ ] No raw data rows beyond the sample are sent to Gemini (asserted by inspecting the outbound prompt in a test).
