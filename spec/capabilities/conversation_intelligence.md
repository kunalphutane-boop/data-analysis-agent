# Capability: Conversation Intelligence (per-call Intent + Outcome classification)

## What It Does
Reads every call's free-text transcript in a call-center dataset with Gemini and attaches two labels per call — an **Intent** (from a data-driven, fixed taxonomy) and an **Outcome** (exactly one of Positive / Neutral / Negative) — then produces an intent breakdown, an outcome breakdown, an outcome-by-intent cross-tab, and a downloadable labelled CSV. It runs as a resumable background job with live progress and running token/cost totals.

> **Deliberate privacy exception (scoped):** unlike the ask/sandbox path (which keeps raw rows local and sends only schema + a small sample), this capability **sends transcript text to Gemini** — the user's explicit, informed choice for this feature ("LLM reads every call — accurate"). The ask/sandbox path is unchanged and remains local-only. See the privacy boundary note in [`architecture.md`](../architecture.md).

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| dataset_id | uuid | `POST /datasets/{id}/classify` (path) | yes |
| text_column | str | `POST /datasets/{id}/classify` body — the transcript column (auto-detected default: a column literally named `"Conversation Log"` if present) | yes |
| session_id | uuid | resolved from the dataset | derived |
| business_context | str (free text) | `sessions.business_context`, authored by the user via `PUT /sessions/{id}/business_context` (see [`api.md`](../api.md)); `""` when unset | optional |
| transcripts | derived | the dataset DataFrame loaded from `data/uploads/` | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| job_id | uuid | `POST /datasets/{id}/classify` response + `classification_jobs.id` |
| progress | `{status, total_calls, classified_calls, percent, elapsed_seconds, input_tokens, output_tokens, cost_usd}` | `GET /classify/jobs/{job_id}` (polled for the progress bar) |
| per-call labels | rows of `{row_index, call_id, intent, outcome}` | `call_labels` table |
| intent_breakdown | `[{intent, count, pct, summary}]` (sums to 100%; `summary` is a ~2-4 sentence per-intent narrative) | `GET /classify/jobs/{job_id}/results` |
| per-intent summaries | rows of `{intent, summary}` | `intent_summaries` table |
| outcome_breakdown | `[{outcome, count, pct}]` (sums to 100%) | `GET /classify/jobs/{job_id}/results` |
| cross_tab | `[{intent, positive, neutral, negative, total}]` (outcome distribution per intent) | `GET /classify/jobs/{job_id}/results` |
| repeat_calls | `{total_calls, identified_calls, unique_callers, repeat_callers, repeat_caller_pct, repeat_call_pct, distribution:[{calls, callers}], top_repeat_callers:[{call_id, count}]}` (deterministic repeat-caller analysis from the stored `call_id`; **no LLM**) | `GET /classify/jobs/{job_id}/results` |
| taxonomy | `[str]` (the fixed intent list) | `classification_jobs.taxonomy_json` + results payload |
| labelled CSV | text/csv (all original columns + `Intent` + `Outcome`) | `GET /classify/jobs/{job_id}/labelled.csv` |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini | derive taxonomy from a sample of transcripts (once per job); classify each batch of transcripts → `{intent, outcome}` per call; summarise each distinct Intent (one call per intent, after classification) → a ~2-4 sentence narrative | batch JSON malformed → retry once, then mark that batch's rows `Intent="Unclassified", Outcome="Neutral"` (never fail the whole run); transient API error → provider retry/backoff, then mark the batch unclassified and continue; a failed intent summary falls back to a short deterministic summary (never fails the run) |
| SQLite | upsert `call_labels`; update `classification_jobs` progress/tokens/cost | 500; job row marked `status="error"` with `error` set |
| Local filesystem (`data/uploads/`) | read the dataset CSV for transcripts + CSV export | 404 if the dataset file is missing |

## Business Rules
- **User-authored business context (domain grounding).** The user types a free-text `business_context` describing their domain (persisted on `sessions.business_context`, edited via `PUT /sessions/{id}/business_context`). When **non-empty**, it is injected into BOTH classification prompts:
  - `src/prompts/derive_taxonomy.md` — the derived Intent taxonomy is **tailored to the context** rather than forced to the generic base set (e.g. a lending NBFC servicing center → `Loan enquiry`, `EMI/Payment`, `KYC/Verification`, `Disbursement delay`, `Foreclosure/Prepayment`, `Collections/Overdue`, `Complaint/Escalation`).
  - `src/prompts/classify_calls.md` — per-call Intent + Outcome judgments use the context (e.g. the user's notion of a Negative outcome).
  When **empty/unset**, behaviour is exactly the generic default (no regression). Wired through `src/analysis/classifier.py` (`derive_taxonomy` / `classify_batch`) and `src/domain/classify.py`.
- **Context-aware cache key.** The idempotency/resume key includes a 16-hex fingerprint (`context_hash = sha256(business_context.strip())[:16]`, empty → `e3b0c44298fc1c14`) stored on `classification_jobs.context_hash` and `call_labels.context_hash`. So: **same** dataset + column + context → resume, no re-classify, no re-bill; **changed** context → a fresh run that re-labels every call with context-aware labels (never returns stale generic labels). Each context keeps its own label set, so switching back also resumes.
- **Per-intent narrative summaries.** After every call is labelled, generate one concise (~2-4 sentence) narrative summary **per distinct Intent** that describes what customers in that intent typically call about (common needs / sub-themes), how those calls tend to resolve (grounded in the intent's Positive/Neutral/Negative outcome distribution — e.g. "mostly Negative because verification fails"), and any notable pattern. One Gemini call per intent (there are only ~6-12), using the same low-cost `AGENT_CLASSIFY_MODEL`, client, pricing and cost-accounting as classification. Each summary call is grounded in the intent name, its count and % share, its Outcome distribution, a capped SAMPLE of that intent's transcripts (`AGENT_SUMMARY_SAMPLE_SIZE`, default 20, each truncated to `AGENT_SUMMARY_TRANSCRIPT_MAX_CHARS`, default 1200) and the session's `business_context` (via `src/prompts/summarise_intent.md`). Sentinel intents (`No transcript`, `Unclassified`) get a deterministic no-LLM summary. Summaries are persisted in the `intent_summaries` table keyed by `(dataset_id, text_column, context_hash, intent)` and surfaced on each `intent_breakdown` row as `summary`. **Cache-consistent:** an unchanged dataset+column+context resumes and returns the cached summaries with **no new Gemini calls**; a changed `business_context` (which already forces re-labelling) refreshes them under the new `context_hash`. Summary token/cost rolls into the job's accounting.
- **Fixed, data-driven taxonomy.** Before classifying, derive a stable Intent taxonomy from a sample of `AGENT_TAXONOMY_SAMPLE_SIZE` transcripts (default 100). With no business context, seeded/fallback to the expected lending-call categories: `Loan enquiry`, `EMI/Payment`, `Account balance/Statement`, `Verification/Registration`, `Branch/Timing`, `Complaint/Escalation`, `Other/Unclear`. With a business context, the taxonomy is tailored to that domain. Every call is then classified into that **fixed set** so labels stay consistent. The taxonomy is derived once per job and stored on `classification_jobs.taxonomy_json`; a resumed run (same context) reuses it.
- **Outcome is exactly one of** `Positive` / `Neutral` / `Negative`. Any value the model returns outside this set is coerced to `Neutral`.
- **Empty / blank transcript** → **no LLM call**; `Intent="No transcript"`, `Outcome="Neutral"`.
- **Batching & efficiency (12k+ rows):** transcripts are sent in batches of `AGENT_CLASSIFY_BATCH_SIZE` calls per Gemini request (default 15) with bounded concurrency `AGENT_CLASSIFY_CONCURRENCY` (default 4), using the fast low-cost `AGENT_CLASSIFY_MODEL` (default `gemini-2.5-flash-lite`). Each transcript is truncated to `AGENT_TRANSCRIPT_MAX_CHARS` (default 6000) before sending.
- **Idempotent / resumable.** Labels are keyed by `(dataset_id, text_column, context_hash, row_index)` with a unique constraint. A re-run (same dataset + column + context) skips already-labelled rows and only classifies the remainder — no re-classification, no duplicate Gemini calls. A repeated `call_id` across rows is fine: each **row** is labelled once by its `row_index` (the stable key); `call_id` is stored as metadata only.
- **Repeat-calls analysis (deterministic, no LLM).** From the stored per-call `call_id`, the results payload also carries a `repeat_calls` block computed by pure counting on the labelled rows (never a Gemini call): `unique_callers` (distinct non-blank `call_id`s), `repeat_callers` (a `call_id` on **more than one** row), `repeat_caller_pct` (`repeat_callers / unique_callers`), `repeat_call_pct` (calls made by repeat callers / `identified_calls`), a `distribution` of callers bucketed by number of calls (`1`,`2`,`3`,`4`,`5+`), and up to 10 `top_repeat_callers` (`{call_id, count}`, count ≥ 2, ordered by count desc then id). Rows with a blank/absent `call_id` still count toward `total_calls` but are excluded from caller stats; when the dataset has no call-id column, `identified_calls == 0` and the UI shows a "no call identifier" note instead of the analysis. The UI renders each analysis (intent breakdown, outcome breakdown, cross-tab, repeat-call distribution) with a chart alongside its table.
- **Progress.** The job reports `classified_calls / total_calls`, percent, and elapsed seconds, plus a running `input_tokens` / `output_tokens` / `cost_usd` total, updated in the DB as each batch completes so the UI polls a live progress bar.
- **Cost accounting** reuses `src/llm/pricing.py` (`cost_usd(model, in, out)`); tokens come from the Gemini provider's `call_with_usage`.
- **Runs outside the sandbox.** This job legitimately needs network to reach Gemini; it runs as a plain async service (see [`agent.md`](../agent.md)), NOT inside the no-network pandas sandbox, which is left untouched.

## Error Cases
- Unknown dataset → 404 `not_found`.
- `text_column` absent from the dataset schema → 400 `bad_column`.
- Malformed batch JSON after one retry → those rows `Unclassified` (Outcome `Neutral`), run continues.
- Gemini unavailable after backoff for a batch → those rows `Unclassified`, run continues; job still reaches `done`.
- DB/file failure → job `status="error"`, `error` set, surfaced via the progress endpoint.

## Success Criteria
- [ ] Given a synthetic transcript CSV (a handful of rows with recognizable intents + clear positive/negative tone + one EMPTY transcript + one REPEATED `call_id`), **every row** receives an `intent` and an `outcome` in `{Positive, Neutral, Negative}` (real Gemini).
- [ ] The empty-transcript row is labelled `Intent="No transcript", Outcome="Neutral"` with **no** Gemini call made for it.
- [ ] `intent_breakdown` percentages sum to 100% (±0.1) and `outcome_breakdown` percentages sum to 100% (±0.1).
- [ ] The `cross_tab` is well-formed: one row per intent with `positive + neutral + negative == total`, and the `total` column sums to the number of calls.
- [ ] **Repeat calls:** given a CSV where one `call_id` recurs on multiple rows, `repeat_calls` reports the correct `unique_callers`, at least one `repeat_caller`, a `distribution` whose `callers` sum to `unique_callers`, and a `top_repeat_callers` list whose every `count ≥ 2` — all with **no** additional Gemini calls (pure counting).
- [ ] The labelled CSV export contains all original columns **plus** `Intent` and `Outcome`, one row per input row, in input order.
- [ ] **Idempotency:** re-running classify for the same dataset + column does **not** re-classify already-labelled rows — no new `call_labels` rows are created and no Gemini classification call is made for those rows (asserted by comparing Gemini call counts / label ids across two runs).
- [ ] The progress endpoint reports `classified_calls == total_calls` and a non-zero `cost_usd` on completion.
- [ ] **Per-intent summaries:** after classifying a small synthetic multi-intent CSV, **every** intent in `intent_breakdown` has a non-empty `summary` string; resuming the same dataset+column+context returns the cached summaries with **no** additional classification or summary Gemini calls.
- [ ] **Business context grounding:** with a lending `business_context` saved on the session, a run produces Intent labels consistent with that domain and every Outcome in `{Positive, Neutral, Negative}` (real Gemini).
- [ ] **Context-aware cache:** changing the saved `business_context` invalidates the cache (different `context_hash`) and triggers a fresh classification run that re-labels every call (labels recomputed, not served stale); an empty/unchanged context resumes with no re-bill.
