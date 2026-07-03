// REAL: renders the /ask response — plain-language answer, step list + counter,
// collapsible code, token/cost badge, clarify + error states.
// Charts area + Export buttons are STUBS. See spec/ui.md.
'use client'

import { formatCost, type AskResult } from '@/lib/api'
import { StubButton, StubPanel } from './Stub'

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

      {/* Stubs: charts + exports */}
      <StubPanel title="Charts" testId="charts-stub">
        Interactive charts for this answer will appear here.
      </StubPanel>

      <div data-testid="exports-stub" className="flex flex-wrap gap-2">
        <StubButton label="Export cleaned CSV" />
        <StubButton label="Export chart image" />
        <StubButton label="Generate report" />
      </div>
    </section>
  )
}
