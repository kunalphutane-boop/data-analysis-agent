// REAL: renders the /ask response — plain-language answer, a structured result
// table + an auto-picked chart (P2 visual outputs), step list + counter,
// collapsible code, token/cost badge, clarify + error states.
// Export buttons remain STUBS (Phase 3). See spec/ui.md + spec/capabilities/visual_outputs.md.
'use client'

import { formatCost, type AskResult, type ResultTable, type TableCell } from '@/lib/api'
import { BarChart, type BarDatum } from './charts'
import { StubButton } from './Stub'

function isNum(v: TableCell): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

function fmtCell(v: TableCell): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return v.toLocaleString(undefined, { maximumFractionDigits: 4 })
  if (typeof v === 'boolean') return v ? 'true' : 'false'
  return v
}

// Auto-pick a bar chart from a result table: needs a numeric value column, a
// distinct label column, and a sane number of rows. Returns null when the table
// isn't chartable (the table alone is then shown).
function pickChart(table: ResultTable): BarDatum[] | null {
  const { columns, rows } = table
  if (rows.length < 1 || rows.length > 30 || columns.length < 2) return null
  let valueIdx = -1
  for (let c = columns.length - 1; c >= 0; c--) {
    if (rows.every((r) => isNum(r[c]))) {
      valueIdx = c
      break
    }
  }
  if (valueIdx === -1) return null
  let labelIdx = columns.findIndex((_, c) => c !== valueIdx && rows.some((r) => !isNum(r[c])))
  if (labelIdx === -1) labelIdx = columns.findIndex((_, c) => c !== valueIdx)
  if (labelIdx === -1) return null
  const data = rows.map((r) => ({ label: fmtCell(r[labelIdx]), value: Number(r[valueIdx]) }))
  if (new Set(data.map((d) => d.label)).size !== data.length) return null // categories must be distinct
  return [...data].sort((a, b) => b.value - a.value).slice(0, 15)
}

function ResultView({ table }: { table: ResultTable }) {
  const chart = pickChart(table)
  return (
    <div data-testid="result-visuals" className="space-y-4">
      {chart && (
        <div data-testid="answer-chart">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
            Chart
          </h4>
          <BarChart testId="answer-bar-chart" data={chart} />
        </div>
      )}
      <div data-testid="answer-table">
        <div className="mb-2 flex items-center justify-between">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Result</h4>
          <span className="text-xs text-gray-400">
            {table.row_count.toLocaleString()} row{table.row_count === 1 ? '' : 's'}
            {table.truncated && ` · showing first ${table.rows.length}`}
          </span>
        </div>
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                {table.columns.map((c, i) => (
                  <th key={i} className="px-3 py-2 font-medium">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, ri) => (
                <tr key={ri} className="border-b border-gray-100 last:border-0 hover:bg-gray-50/60">
                  {row.map((cell, ci) => (
                    <td
                      key={ci}
                      className={`px-3 py-1.5 tabular-nums ${
                        isNum(cell) ? 'text-right text-gray-800' : 'text-gray-700'
                      }`}
                    >
                      {fmtCell(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function StepList({ steps }: { steps: AskResult['steps'] }) {
  const total = steps.length
  const done = steps.filter((s) => s.status === 'done').length
  const current = Math.min(done + (done < total ? 1 : 0), total)

  return (
    <div data-testid="step-list" className="rounded-lg border border-gray-200 bg-gray-50 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Analysis steps
        </span>
        <span data-testid="step-counter" className="text-xs font-medium text-gray-500">
          step {current} of {total}
        </span>
      </div>
      <ol className="space-y-1.5">
        {steps.map((s) => {
          const color =
            s.status === 'done'
              ? 'text-green-600'
              : s.status === 'error'
                ? 'text-red-600'
                : s.status === 'running'
                  ? 'text-blue-600'
                  : 'text-gray-400'
          const mark =
            s.status === 'done'
              ? '✓'
              : s.status === 'error'
                ? '✕'
                : s.status === 'running'
                  ? '…'
                  : '○'
          return (
            <li key={s.step} className="flex items-center gap-2 text-sm">
              <span className={`w-4 shrink-0 text-center font-semibold ${color}`}>{mark}</span>
              <span className="text-gray-700">
                {s.step}. {s.label}
              </span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

export function AnswerDisplay({ result }: { result: AskResult | null }) {
  if (!result) return null

  const clarify = result.needs_clarification
  const failed = !!result.error

  return (
    <section
      data-testid="answer-display"
      className="space-y-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
    >
      {/* Answer / clarify / error */}
      {clarify ? (
        <div
          data-testid="clarify-block"
          className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800"
        >
          <p className="mb-1 font-semibold">Needs clarification</p>
          <p>{result.clarify_question ?? result.answer}</p>
          <p className="mt-2 text-xs text-amber-700">Refine your question above and ask again.</p>
        </div>
      ) : failed ? (
        <div
          data-testid="answer-error"
          className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
        >
          <p className="mb-1 font-semibold">Analysis failed</p>
          <p className="whitespace-pre-wrap">{result.error || result.answer}</p>
        </div>
      ) : (
        <div
          data-testid="answer-text"
          className="whitespace-pre-wrap text-sm leading-relaxed text-gray-800"
        >
          {result.answer}
        </div>
      )}

      {/* Step list + counter */}
      {result.steps?.length > 0 && <StepList steps={result.steps} />}

      {/* Show code (collapsible) */}
      {result.generated_code && (
        <details data-testid="show-code" className="rounded-lg border border-gray-200">
          <summary className="cursor-pointer select-none px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
            Show code
          </summary>
          <pre
            data-testid="generated-code"
            className="overflow-x-auto border-t border-gray-200 bg-gray-900 p-3 text-xs leading-relaxed text-gray-100"
          >
            <code>{result.generated_code}</code>
          </pre>
        </details>
      )}

      {/* Token / cost badge */}
      <div className="flex flex-wrap items-center gap-3">
        <span
          data-testid="cost-badge"
          className="inline-flex items-center gap-2 rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-600"
        >
          <span data-testid="tokens-in">{result.input_tokens.toLocaleString()} in</span>
          <span className="text-gray-300">·</span>
          <span data-testid="tokens-out">{result.output_tokens.toLocaleString()} out</span>
          <span className="text-gray-300">·</span>
          <span data-testid="cost-usd" className="font-semibold text-gray-800">
            {formatCost(result.cost_usd)}
          </span>
        </span>
      </div>

      {/* Real: structured result table + auto-picked chart (P2 visual outputs). */}
      {!clarify && !failed && result.table && result.table.rows.length > 0 && (
        <ResultView table={result.table} />
      )}

      {/* Exports remain stubbed (Phase 3). */}
      <div data-testid="exports-stub" className="flex flex-wrap gap-2">
        <StubButton label="Export cleaned CSV" />
        <StubButton label="Export chart image" />
        <StubButton label="Generate report" />
      </div>
    </section>
  )
}
