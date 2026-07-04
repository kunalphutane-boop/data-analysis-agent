// REAL (Phase 4): Conversation Intelligence. On a loaded dataset, the user
// clicks "Analyze conversations", picks the transcript column (auto-defaulted to
// a column named "Conversation Log"), and starts a classification job. We POST
// /datasets/{id}/classify, then poll GET /classify/jobs/{job_id} showing a live
// progress bar (count, percent, elapsed, running cost). On done we fetch and
// render the intent breakdown, outcome breakdown, and outcome-by-intent
// cross-tab, plus a "Download labelled CSV" button. See spec/ui.md + spec/api.md.
'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiError,
  detectTranscriptColumn,
  formatCost,
  getBusinessContext,
  getClassifyProgress,
  getClassifyResults,
  labelledCsvUrl,
  saveBusinessContext,
  startClassify,
  type ClassifyProgress,
  type ClassifyResults,
  type Dataset,
  type IntentBreakdownRow,
} from '@/lib/api'
import {
  BarChart,
  OUTCOME_COLOR,
  StackedBarChart,
  type BarDatum,
} from './charts'

const BUSINESS_CONTEXT_HINT =
  "Describe your business so intents & outcomes are tailored — e.g. 'We are a lending " +
  'NBFC; this call center handles loan servicing, EMI, KYC/verification, disbursement ' +
  "and collections.'"

const POLL_INTERVAL_MS = 1500
const OUTCOME_ORDER = ['Positive', 'Neutral', 'Negative'] as const

type Phase = 'idle' | 'starting' | 'running' | 'done' | 'error'

function isActive(status: ClassifyProgress['status']): boolean {
  return status === 'pending' || status === 'deriving_taxonomy' || status === 'classifying'
}

function statusLabel(status: ClassifyProgress['status']): string {
  switch (status) {
    case 'pending':
      return 'Starting…'
    case 'deriving_taxonomy':
      return 'Deriving taxonomy…'
    case 'classifying':
      return 'Classifying calls…'
    case 'done':
      return 'Done'
    case 'error':
      return 'Error'
  }
}

function pct(n: number): string {
  return `${n.toFixed(1)}%`
}

function ProgressView({ progress }: { progress: ClassifyProgress }) {
  const percent = Math.max(0, Math.min(100, progress.percent))
  return (
    <div data-testid="classify-progress" className="space-y-2">
      <div className="flex items-center justify-between text-xs font-medium text-gray-600">
        <span data-testid="classify-status">{statusLabel(progress.status)}</span>
        <span data-testid="classify-percent">{pct(percent)}</span>
      </div>
      <div className="h-2.5 w-full overflow-hidden rounded-full bg-gray-100">
        <div
          data-testid="classify-progress-bar"
          className="h-full rounded-full bg-blue-600 transition-all"
          style={{ width: `${percent}%` }}
        />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
        <span data-testid="classify-count">
          {progress.classified_calls.toLocaleString()} / {progress.total_calls.toLocaleString()} calls
        </span>
        <span data-testid="classify-elapsed">{progress.elapsed_seconds.toFixed(1)}s elapsed</span>
        <span data-testid="classify-cost" className="font-semibold text-gray-700">
          {formatCost(progress.cost_usd)}
        </span>
      </div>
    </div>
  )
}

function IntentRow({ row }: { row: IntentBreakdownRow }) {
  const [expanded, setExpanded] = useState(false)
  const hasSummary = row.summary.trim().length > 0
  return (
    <>
      <tr className="border-b border-gray-100 last:border-0">
        <td className="py-2 pr-4 font-medium text-gray-800">
          <button
            type="button"
            data-testid="intent-summary-toggle"
            onClick={() => setExpanded((v) => !v)}
            disabled={!hasSummary}
            className="inline-flex items-center gap-1.5 text-left font-medium text-gray-800 hover:text-blue-700 disabled:cursor-default disabled:text-gray-800 disabled:hover:text-gray-800"
            aria-expanded={expanded}
          >
            {hasSummary && (
              <span
                className={`inline-block text-[10px] text-gray-400 transition-transform ${
                  expanded ? 'rotate-90' : ''
                }`}
              >
                ▶
              </span>
            )}
            {row.intent}
          </button>
        </td>
        <td className="py-2 pr-4 text-gray-700">{row.count.toLocaleString()}</td>
        <td className="py-2 pr-4 text-gray-700">{pct(row.pct)}</td>
      </tr>
      {expanded && hasSummary && (
        <tr data-testid="intent-summary-row" className="border-b border-gray-100 last:border-0">
          <td colSpan={3} className="px-1 pb-3 pt-0">
            <p
              data-testid="intent-summary-text"
              className="rounded-md bg-blue-50/60 px-3 py-2 text-xs leading-relaxed text-gray-700"
            >
              {row.summary}
            </p>
          </td>
        </tr>
      )}
    </>
  )
}

function IntentBreakdown({ results }: { results: ClassifyResults }) {
  const anySummary = results.intent_breakdown.some((r) => r.summary.trim().length > 0)
  return (
    <div data-testid="intent-breakdown">
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
        Intent breakdown
      </h4>
      {anySummary && (
        <p className="mb-2 text-xs text-gray-400">
          Click an intent to read its summary — what customers call about, how it resolves,
          and notable patterns.
        </p>
      )}
      <table className="w-full border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-xs uppercase tracking-wide text-gray-400">
            <th className="py-2 pr-4 font-medium">Intent</th>
            <th className="py-2 pr-4 font-medium">Count</th>
            <th className="py-2 pr-4 font-medium">%</th>
          </tr>
        </thead>
        <tbody data-testid="intent-rows">
          {results.intent_breakdown.map((r) => (
            <IntentRow key={r.intent} row={r} />
          ))}
        </tbody>
      </table>
      <div className="mt-4">
        <BarChart
          testId="intent-chart"
          data={[...results.intent_breakdown]
            .sort((a, b) => b.count - a.count)
            .map<BarDatum>((r) => ({
              label: r.intent,
              value: r.count,
              valueLabel: `${r.count.toLocaleString()} · ${pct(r.pct)}`,
              title: `${r.intent}: ${r.count.toLocaleString()} (${pct(r.pct)})`,
            }))}
        />
      </div>
    </div>
  )
}

function OutcomeBreakdown({ results }: { results: ClassifyResults }) {
  // Render Positive / Neutral / Negative in a stable order.
  const byOutcome = new Map(results.outcome_breakdown.map((r) => [r.outcome, r]))
  const rows = OUTCOME_ORDER.map(
    (o) => byOutcome.get(o) ?? { outcome: o, count: 0, pct: 0 },
  )
  const tone: Record<string, string> = {
    Positive: 'text-green-700',
    Neutral: 'text-gray-700',
    Negative: 'text-red-700',
  }
  return (
    <div data-testid="outcome-breakdown">
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
        Outcome breakdown
      </h4>
      <table className="w-full border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-xs uppercase tracking-wide text-gray-400">
            <th className="py-2 pr-4 font-medium">Outcome</th>
            <th className="py-2 pr-4 font-medium">Count</th>
            <th className="py-2 pr-4 font-medium">%</th>
          </tr>
        </thead>
        <tbody data-testid="outcome-rows">
          {rows.map((r) => (
            <tr key={r.outcome} className="border-b border-gray-100 last:border-0">
              <td className={`py-2 pr-4 font-medium ${tone[r.outcome] ?? 'text-gray-800'}`}>
                {r.outcome}
              </td>
              <td className="py-2 pr-4 text-gray-700">{r.count.toLocaleString()}</td>
              <td className="py-2 pr-4 text-gray-700">{pct(r.pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-4">
        <BarChart
          testId="outcome-chart"
          data={rows.map<BarDatum>((r) => ({
            label: r.outcome,
            value: r.count,
            color: OUTCOME_COLOR[r.outcome],
            valueLabel: `${r.count.toLocaleString()} · ${pct(r.pct)}`,
            title: `${r.outcome}: ${r.count.toLocaleString()} (${pct(r.pct)})`,
          }))}
        />
      </div>
    </div>
  )
}

function CrossTab({ results }: { results: ClassifyResults }) {
  return (
    <div data-testid="cross-tab" className="overflow-x-auto">
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
        Outcome by intent
      </h4>
      <table className="w-full border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-xs uppercase tracking-wide text-gray-400">
            <th className="py-2 pr-4 font-medium">Intent</th>
            <th className="py-2 pr-4 font-medium">Positive</th>
            <th className="py-2 pr-4 font-medium">Neutral</th>
            <th className="py-2 pr-4 font-medium">Negative</th>
            <th className="py-2 pr-4 font-medium">Total</th>
          </tr>
        </thead>
        <tbody data-testid="cross-tab-rows">
          {results.cross_tab.map((r) => (
            <tr key={r.intent} className="border-b border-gray-100 last:border-0">
              <td className="py-2 pr-4 font-medium text-gray-800">{r.intent}</td>
              <td className="py-2 pr-4 text-green-700">{r.positive.toLocaleString()}</td>
              <td className="py-2 pr-4 text-gray-700">{r.neutral.toLocaleString()}</td>
              <td className="py-2 pr-4 text-red-700">{r.negative.toLocaleString()}</td>
              <td className="py-2 pr-4 font-semibold text-gray-800">{r.total.toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-4">
        <StackedBarChart
          testId="cross-tab-chart"
          legend={[
            { name: 'Positive', color: OUTCOME_COLOR.Positive },
            { name: 'Neutral', color: OUTCOME_COLOR.Neutral },
            { name: 'Negative', color: OUTCOME_COLOR.Negative },
          ]}
          data={[...results.cross_tab]
            .sort((a, b) => b.total - a.total)
            .map((r) => ({
              label: r.intent,
              segments: [
                { name: 'Positive', value: r.positive, color: OUTCOME_COLOR.Positive },
                { name: 'Neutral', value: r.neutral, color: OUTCOME_COLOR.Neutral },
                { name: 'Negative', value: r.negative, color: OUTCOME_COLOR.Negative },
              ],
            }))}
        />
      </div>
    </div>
  )
}

function StatTile({
  label,
  value,
  testId,
}: {
  label: string
  value: string
  testId?: string
}) {
  return (
    <div
      data-testid={testId}
      className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2"
    >
      <div className="text-lg font-semibold tabular-nums text-gray-900">{value}</div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  )
}

function RepeatCallsPanel({ results }: { results: ClassifyResults }) {
  const rc = results.repeat_calls
  if (!rc || rc.identified_calls === 0) {
    return (
      <div data-testid="repeat-calls">
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
          Repeat calls
        </h4>
        <p
          data-testid="repeat-calls-empty"
          className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-4 text-xs text-gray-500"
        >
          No call identifier column was detected in this dataset, so repeat callers
          can&apos;t be attributed.
        </p>
      </div>
    )
  }
  return (
    <div data-testid="repeat-calls" className="space-y-4">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
        Repeat calls
      </h4>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile
          testId="repeat-unique-callers"
          label="Unique callers"
          value={rc.unique_callers.toLocaleString()}
        />
        <StatTile
          testId="repeat-repeat-callers"
          label="Repeat callers"
          value={rc.repeat_callers.toLocaleString()}
        />
        <StatTile
          testId="repeat-caller-pct"
          label="Callers who repeat"
          value={pct(rc.repeat_caller_pct)}
        />
        <StatTile
          testId="repeat-call-pct"
          label="Calls from repeaters"
          value={pct(rc.repeat_call_pct)}
        />
      </div>

      <div>
        <p className="mb-2 text-xs text-gray-400">Callers by number of calls</p>
        <BarChart
          testId="repeat-distribution-chart"
          data={rc.distribution.map<BarDatum>((d) => ({
            label: `${d.calls} call${d.calls === '1' ? '' : 's'}`,
            value: d.callers,
            title: `${d.callers.toLocaleString()} caller(s) made ${d.calls} call(s)`,
          }))}
        />
      </div>

      {rc.top_repeat_callers.length > 0 && (
        <div>
          <p className="mb-2 text-xs text-gray-400">Top repeat callers</p>
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-xs uppercase tracking-wide text-gray-400">
                <th className="py-2 pr-4 font-medium">Call ID</th>
                <th className="py-2 pr-4 font-medium">Calls</th>
              </tr>
            </thead>
            <tbody data-testid="top-repeat-rows">
              {rc.top_repeat_callers.map((c) => (
                <tr key={c.call_id} className="border-b border-gray-100 last:border-0">
                  <td className="py-2 pr-4 font-mono text-xs text-gray-700">{c.call_id}</td>
                  <td className="py-2 pr-4 tabular-nums text-gray-700">
                    {c.count.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function ResultsView({ jobId, results }: { jobId: string; results: ClassifyResults }) {
  return (
    <div data-testid="classify-results" className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-sm font-medium text-gray-700">
          {results.total_calls.toLocaleString()} calls classified
        </span>
        <a
          data-testid="download-labelled-csv"
          href={labelledCsvUrl(jobId)}
          download
          className="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700"
        >
          Download labelled CSV
        </a>
      </div>

      <IntentBreakdown results={results} />
      <OutcomeBreakdown results={results} />
      <CrossTab results={results} />
      <RepeatCallsPanel results={results} />

      <div className="flex flex-wrap items-center gap-3">
        <span
          data-testid="classify-cost-badge"
          className="inline-flex items-center gap-2 rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-600"
        >
          <span>{results.input_tokens.toLocaleString()} in</span>
          <span className="text-gray-300">·</span>
          <span>{results.output_tokens.toLocaleString()} out</span>
          <span className="text-gray-300">·</span>
          <span className="font-semibold text-gray-800">{formatCost(results.cost_usd)}</span>
        </span>
      </div>
    </div>
  )
}

function BusinessContextPanel({ sessionId }: { sessionId: string }) {
  const [text, setText] = useState('')
  const [savedValue, setSavedValue] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // True once a save actually changed the stored context — so the user knows a
  // re-run will re-classify with the new context.
  const [changedOnSave, setChangedOnSave] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)
    getBusinessContext(sessionId)
      .then((bc) => {
        if (!active) return
        setText(bc.business_context)
        setSavedValue(bc.business_context)
      })
      .catch(() => {
        // Absent/unset context is fine — start empty.
        if (active) {
          setText('')
          setSavedValue('')
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [sessionId])

  async function handleSave() {
    setSaving(true)
    setError(null)
    const previous = savedValue.trim()
    try {
      const bc = await saveBusinessContext(sessionId, text)
      setText(bc.business_context)
      setSavedValue(bc.business_context)
      setChangedOnSave(bc.business_context.trim() !== previous)
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Network error — is the server running at :8001?',
      )
    } finally {
      setSaving(false)
    }
  }

  const dirty = text.trim() !== savedValue.trim()

  return (
    <div
      data-testid="business-context-panel"
      className="rounded-lg border border-gray-200 bg-gray-50 p-3"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Business Context
        </h3>
        <button
          type="button"
          data-testid="business-context-save"
          onClick={handleSave}
          disabled={saving || loading || !dirty}
          className="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving && (
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />
          )}
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>

      <p data-testid="business-context-helper" className="mt-1 text-xs text-gray-500">
        {BUSINESS_CONTEXT_HINT}
      </p>

      <textarea
        data-testid="business-context-input"
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          setChangedOnSave(false)
        }}
        disabled={loading}
        rows={3}
        placeholder="e.g. We are a lending NBFC handling loan servicing, EMI, KYC/verification, disbursement and collections."
        className="mt-2 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-800 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-100"
      />

      {error && (
        <p data-testid="business-context-error" className="mt-1 text-xs text-red-600">
          {error}
        </p>
      )}

      {changedOnSave && !dirty && (
        <p
          data-testid="business-context-saved"
          className="mt-2 rounded-md bg-amber-50 px-2 py-1 text-xs font-medium text-amber-700"
        >
          Business context updated. Run (or Re-run) classification to re-label every call
          with the new context.
        </p>
      )}

      {dirty && !loading && (
        <p data-testid="business-context-dirty" className="mt-2 text-xs text-amber-600">
          Unsaved changes — click Save before running so the new context is used.
        </p>
      )}
    </div>
  )
}

export function ConversationIntelligence({ dataset }: { dataset: Dataset }) {
  const columns = dataset.profile.columns
  const [open, setOpen] = useState(false)
  const [column, setColumn] = useState<string>(() => detectTranscriptColumn(dataset) ?? '')
  const [phase, setPhase] = useState<Phase>('idle')
  const [jobId, setJobId] = useState<string | null>(null)
  const [progress, setProgress] = useState<ClassifyProgress | null>(null)
  const [results, setResults] = useState<ClassifyResults | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Keep a ref to the poll timer so we can clear it on unmount / state change.
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  useEffect(() => clearTimer, [clearTimer])

  const finish = useCallback(async (id: string) => {
    try {
      const r = await getClassifyResults(id)
      setResults(r)
      setPhase('done')
    } catch (err) {
      setErrorMsg(
        err instanceof ApiError
          ? err.message
          : 'Network error — is the server running at :8001?',
      )
      setPhase('error')
    }
  }, [])

  const poll = useCallback(
    async (id: string) => {
      try {
        const p = await getClassifyProgress(id)
        setProgress(p)
        if (p.status === 'error') {
          setErrorMsg(p.error || 'Classification failed.')
          setPhase('error')
          return
        }
        if (p.status === 'done') {
          await finish(id)
          return
        }
        // Still active — schedule the next poll.
        timerRef.current = setTimeout(() => void poll(id), POLL_INTERVAL_MS)
      } catch (err) {
        setErrorMsg(
          err instanceof ApiError
            ? err.message
            : 'Network error — is the server running at :8001?',
        )
        setPhase('error')
      }
    },
    [finish],
  )

  async function handleStart() {
    if (!column) return
    clearTimer()
    setPhase('starting')
    setErrorMsg(null)
    setResults(null)
    setProgress(null)
    try {
      const job = await startClassify(dataset.id, column)
      setJobId(job.job_id)
      setProgress({
        job_id: job.job_id,
        status: job.status,
        total_calls: job.total_calls,
        classified_calls: job.classified_calls,
        percent: job.total_calls > 0 ? (job.classified_calls / job.total_calls) * 100 : 0,
        elapsed_seconds: 0,
        input_tokens: 0,
        output_tokens: 0,
        cost_usd: 0,
        error: null,
      })
      setPhase('running')
      void poll(job.job_id)
    } catch (err) {
      setErrorMsg(
        err instanceof ApiError
          ? err.message
          : 'Network error — is the server running at :8001?',
      )
      setPhase('error')
    }
  }

  const running = phase === 'starting' || phase === 'running'

  return (
    <section
      data-testid="conversation-intelligence"
      className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">Conversation Intelligence</h2>
        {!open && (
          <button
            type="button"
            data-testid="analyze-conversations"
            onClick={() => setOpen(true)}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Analyze conversations
          </button>
        )}
      </div>

      <p className="mt-1 text-xs text-gray-500">
        Classify every call by Intent + Outcome with Gemini, then read the breakdowns and
        download a labelled CSV.
      </p>

      {open && (
        <div className="mt-4 space-y-4">
          {/* Business Context — grounds the taxonomy + outcome judgments in the
              user's domain. Prefilled from the saved value, reused on every run. */}
          <BusinessContextPanel sessionId={dataset.session_id} />

          {/* Column picker + start */}
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col text-xs font-medium text-gray-600">
              Transcript column
              <select
                data-testid="transcript-column-select"
                value={column}
                onChange={(e) => setColumn(e.target.value)}
                disabled={running}
                className="mt-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-800 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50"
              >
                {columns.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>

            <button
              type="button"
              data-testid="classify-start"
              onClick={handleStart}
              disabled={running || !column}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {running && (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
              )}
              {running ? 'Analyzing…' : phase === 'done' ? 'Re-run' : 'Start'}
            </button>
          </div>

          {/* Progress */}
          {running && progress && isActive(progress.status) && (
            <ProgressView progress={progress} />
          )}

          {/* Error */}
          {phase === 'error' && errorMsg && (
            <div
              data-testid="classify-error"
              className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
            >
              <p className="mb-1 font-semibold">Classification failed</p>
              <p className="whitespace-pre-wrap">{errorMsg}</p>
            </div>
          )}

          {/* Results */}
          {phase === 'done' && results && jobId && (
            <ResultsView jobId={jobId} results={results} />
          )}
        </div>
      )}
    </section>
  )
}

export { BusinessContextPanel }
