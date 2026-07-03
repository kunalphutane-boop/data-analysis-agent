// REAL: question textarea + Ask button. Disabled until a dataset is loaded and
// the box is non-empty. Follow-up suggestion chips are a STUB. See spec/ui.md.
'use client'

import { StubButton } from './Stub'

interface Props {
  value: string
  onChange: (v: string) => void
  onAsk: () => void
  loading: boolean
  disabled: boolean
}

export function QuestionBox({ value, onChange, onAsk, loading, disabled }: Props) {
  const canAsk = !disabled && !loading && value.trim().length > 0

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold text-gray-700">Ask a question</h2>

      <textarea
        data-testid="question-input"
        className="w-full rounded-lg border border-gray-300 p-3 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50"
        rows={3}
        placeholder={
          disabled
            ? 'Upload a CSV first, then ask a question…'
            : 'e.g. What is the total revenue by region?'
        }
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && canAsk) onAsk()
        }}
        disabled={disabled || loading}
      />

      <div className="mt-3 flex items-center justify-between">
        <button
          type="button"
          data-testid="ask-button"
          onClick={onAsk}
          disabled={!canAsk}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading && (
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
          )}
          {loading ? 'Analyzing…' : 'Ask'}
        </button>

        <div data-testid="followups-stub" className="flex items-center gap-2">
          <StubButton label="Follow-up suggestions" />
        </div>
      </div>
    </section>
  )
}
