// Typed fetch helpers for the analytics agent API.
// Base is same-origin ("") — the UI is served by FastAPI at /app/ and the API
// lives at the same origin (e.g. POST /datasets/upload). See spec/api.md.
//
// Envelope: success -> { data, error: null }; failure -> { detail: { code, message } }.

export interface Session {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ProfileColumn {
  name: string
  dtype: string
  non_null: number
  missing_pct: number
  min: number | string | null
  max: number | string | null
}

export interface Profile {
  row_count: number
  col_count: number
  columns: ProfileColumn[]
  sample: Record<string, unknown>[]
}

export interface Dataset {
  id: string
  session_id: string
  filename: string
  row_count: number
  col_count: number
  profile: Profile
}

export interface AskStep {
  step: number
  label: string
  status: string
}

export interface AskResult {
  message_id: string
  answer: string
  generated_code: string
  steps: AskStep[]
  input_tokens: number
  output_tokens: number
  cost_usd: number
  needs_clarification: boolean
  clarify_question: string | null
  error: string | null
}

// Thrown when the API returns a non-2xx with the { detail: { code, message } } shape.
export class ApiError extends Error {
  code: string
  status: number
  constructor(code: string, message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

interface Envelope<T> {
  data: T
  error: string | null
}

interface ErrorBody {
  detail?: { code?: string; message?: string }
}

async function unwrap<T>(res: Response): Promise<T> {
  let body: unknown
  try {
    body = await res.json()
  } catch {
    throw new ApiError('bad_response', `Server returned invalid JSON (${res.status})`, res.status)
  }
  if (!res.ok) {
    const detail = (body as ErrorBody).detail
    throw new ApiError(
      detail?.code ?? 'error',
      detail?.message ?? `Request failed (${res.status})`,
      res.status,
    )
  }
  return (body as Envelope<T>).data
}

export async function createSession(title?: string): Promise<Session> {
  const res = await fetch('/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(title ? { title } : {}),
  })
  return unwrap<Session>(res)
}

// Business Context — free-text description of the user's business that grounds
// Conversation Intelligence (Intent taxonomy + Outcome) in their domain. Scoped to
// the session. Contract: spec/api.md "GET/PUT /sessions/{id}/business_context".
export interface BusinessContext {
  session_id: string
  business_context: string
}

export async function getBusinessContext(sessionId: string): Promise<BusinessContext> {
  const res = await fetch(`/sessions/${sessionId}/business_context`)
  return unwrap<BusinessContext>(res)
}

export async function saveBusinessContext(
  sessionId: string,
  businessContext: string,
): Promise<BusinessContext> {
  const res = await fetch(`/sessions/${sessionId}/business_context`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ business_context: businessContext }),
  })
  return unwrap<BusinessContext>(res)
}

export async function uploadDataset(file: File, sessionId?: string): Promise<Dataset> {
  const form = new FormData()
  form.append('file', file)
  if (sessionId) form.append('session_id', sessionId)
  const res = await fetch('/datasets/upload', { method: 'POST', body: form })
  return unwrap<Dataset>(res)
}

export async function ask(
  sessionId: string,
  datasetId: string,
  question: string,
): Promise<AskResult> {
  const res = await fetch('/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, dataset_id: datasetId, question }),
  })
  return unwrap<AskResult>(res)
}

// ---------------------------------------------------------------------------
// Phase 4 — Conversation Intelligence (per-call Intent + Outcome classification)
// Contract: spec/api.md "Phase 4 — Conversation Intelligence endpoints".
// ---------------------------------------------------------------------------

export type ClassifyStatus =
  | 'pending'
  | 'deriving_taxonomy'
  | 'classifying'
  | 'done'
  | 'error'

// POST /datasets/{id}/classify response.
export interface ClassifyJob {
  job_id: string
  dataset_id: string
  text_column: string
  status: ClassifyStatus
  total_calls: number
  classified_calls: number
}

// GET /classify/jobs/{job_id} response (drives the progress bar).
export interface ClassifyProgress {
  job_id: string
  status: ClassifyStatus
  total_calls: number
  classified_calls: number
  percent: number
  elapsed_seconds: number
  input_tokens: number
  output_tokens: number
  cost_usd: number
  error: string | null
}

export interface IntentBreakdownRow {
  intent: string
  count: number
  pct: number
  // Narrative summary for this intent (what customers call about, how it resolves,
  // notable patterns). May be "" while a run is still classifying / before generation.
  summary: string
}

export interface OutcomeBreakdownRow {
  outcome: string
  count: number
  pct: number
}

export interface CrossTabRow {
  intent: string
  positive: number
  neutral: number
  negative: number
  total: number
}

// GET /classify/jobs/{job_id}/results response.
export interface ClassifyResults {
  job_id: string
  status: ClassifyStatus
  total_calls: number
  taxonomy: string[]
  intent_breakdown: IntentBreakdownRow[]
  outcome_breakdown: OutcomeBreakdownRow[]
  cross_tab: CrossTabRow[]
  input_tokens: number
  output_tokens: number
  cost_usd: number
}

// Start (or resume) a classification job for a dataset's transcript column.
export async function startClassify(
  datasetId: string,
  textColumn: string,
): Promise<ClassifyJob> {
  const res = await fetch(`/datasets/${datasetId}/classify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text_column: textColumn }),
  })
  return unwrap<ClassifyJob>(res)
}

// Poll job progress.
export async function getClassifyProgress(jobId: string): Promise<ClassifyProgress> {
  const res = await fetch(`/classify/jobs/${jobId}`)
  return unwrap<ClassifyProgress>(res)
}

// Fetch aggregated results (available while classifying; final at done).
export async function getClassifyResults(jobId: string): Promise<ClassifyResults> {
  const res = await fetch(`/classify/jobs/${jobId}/results`)
  return unwrap<ClassifyResults>(res)
}

// Same-origin URL for the labelled CSV download (raw text/csv, not enveloped).
// Used as the href of a download link so the browser triggers a file download.
export function labelledCsvUrl(jobId: string): string {
  return `/classify/jobs/${jobId}/labelled.csv`
}

// Auto-detect the transcript column: a column literally named "Conversation Log"
// if present, otherwise the first column. Returns null if there are no columns.
export function detectTranscriptColumn(dataset: Dataset): string | null {
  const cols = dataset.profile.columns
  if (cols.length === 0) return null
  const match = cols.find((c) => c.name === 'Conversation Log')
  return match ? match.name : cols[0].name
}

export function formatCost(cost: number): string {
  if (!Number.isFinite(cost)) return '$0.00'
  if (cost === 0) return '$0.00'
  if (cost < 0.01) return `$${cost.toFixed(4)}`
  return `$${cost.toFixed(2)}`
}
