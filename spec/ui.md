# UI

The single-page Next.js UI served at `/app/`. Calls the endpoints in [`api.md`](api.md). Product intent in [`roadmap.md`](roadmap.md).

---

## UI Type

Web single-page app. Next.js 15 + React 19, statically exported and served by FastAPI at `http://localhost:8001/app/`. API base is same-origin (`""`). Files: `frontend/src/app/page.tsx`, `frontend/src/components/**`, API client `frontend/src/lib/api.ts`. Recharts is added for charts in Phase 2.

**Stub discipline:** every not-yet-built surface is rendered but visibly **greyed out with a "Coming soon" badge**, so a stub is never mistaken for a bug. Only the elements marked REAL below are functional in Phase 1.

---

## Layout

```
┌──────────────┬───────────────────────────────────────────────┐
│ Sessions     │  Upload dropzone            [Add file] (STUB)  │
│ sidebar      │  ───────────────────────────────────────────  │
│ (STUB —      │  Profile panel (REAL)                          │
│  "Coming     │  ───────────────────────────────────────────  │
│  soon")      │  Data-quality flags (STUB)                     │
│              │  ───────────────────────────────────────────  │
│  Daily cost  │  Question box  [ Ask ] (REAL)                  │
│  total       │  Follow-up suggestion chips (STUB)             │
│  (STUB)      │  ───────────────────────────────────────────  │
│              │  Answer display (REAL): answer text,           │
│              │   step list + counter, Show code, cost badge   │
│              │  Charts area (STUB)                            │
│              │  Export buttons (STUB)                          │
└──────────────┴───────────────────────────────────────────────┘
```

## Views / Screens

### Screen: Analysis workspace (the whole app)

**Purpose:** upload a CSV, read its profile, ask a question, read the answer with its code and cost.

**REAL elements:**
- **Upload dropzone** — drag/drop or pick a CSV. Calls `POST /datasets/upload` (creates a session via `POST /sessions` first if none). On success, stores `session_id` + `dataset_id` and renders the profile.
- **Profile panel** — table from `profile.columns`: column name, dtype, non-null count, missing %, min/max (numeric). Header shows `row_count × col_count`.
- **Question box + Ask button** — textarea + button. Calls `POST /ask` with `{session_id, dataset_id, question}`.
- **Answer display** — renders `/ask` response:
  - plain-language `answer` text;
  - **Show code** — collapsible `<details>` showing `generated_code` (monospace);
  - **Step list + counter** — renders `steps[]` (Plan → Generate code → Execute → Answer) with a "step X of N" counter and per-step status;
  - **Token/cost badge** — `input_tokens` in / `output_tokens` out / `cost_usd` (formatted, e.g. `$0.0002`);
  - **Clarify state** — if `needs_clarification`, show `clarify_question` as a prompt inviting the user to refine and re-ask.

**Labelled NON-FUNCTIONAL stubs (greyed + "Coming soon"):** Sessions sidebar, Add-file button, Data-quality flags panel, Follow-up suggestion chips, Charts area, Export buttons, running Daily-cost total, column annotation editor.

**Actions available (P1):** upload a CSV; ask a question; expand/collapse code; refine + re-ask on clarify.

## Error & Loading States (REAL elements)

- **Upload:** empty → dropzone with hint; loading → spinner + "Profiling…"; error → inline message from `error.message` (e.g. "Not a valid CSV"); success → profile panel.
- **Profile panel:** empty (no dataset) → "Upload a CSV to begin"; populated → table.
- **Ask/Answer:** disabled Ask until a dataset is loaded and the box is non-empty; loading → step list animates as "step X of N"; error → the failure `answer`/`error` text shown plainly (no crash); clarify → clarifying prompt.
- **Network failure:** any failed fetch shows a non-blocking error toast/inline message; the app never white-screens.

## Tech Stack

Next.js 15 + React 19 (static export), TypeScript, Recharts (Phase 2). E2E: Playwright in `frontend/tests/e2e/` — the Phase 1 smoke starts the real server and drives upload → ask → answer in the browser (config `frontend/playwright.config.ts`).
