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

export function formatCost(cost: number): string {
  if (!Number.isFinite(cost)) return '$0.00'
  if (cost === 0) return '$0.00'
  if (cost < 0.01) return `$${cost.toFixed(4)}`
  return `$${cost.toFixed(2)}`
}
