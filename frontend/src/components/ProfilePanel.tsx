// REAL: renders the dataset profile table. Empty state before upload.
// Data-quality flags + column annotation editor are STUBS. See spec/ui.md.
'use client'

import type { Dataset } from '@/lib/api'
import { StubPanel } from './Stub'

function fmt(v: number | string | null): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') {
    if (!Number.isFinite(v)) return '—'
    return Number.isInteger(v) ? String(v) : v.toFixed(2)
  }
  return String(v)
}

export function ProfilePanel({ dataset }: { dataset: Dataset | null }) {
  if (!dataset) {
    return (
      <section
        data-testid="profile-empty"
        className="rounded-xl border border-gray-200 bg-white p-8 text-center shadow-sm"
      >
        <h2 className="text-sm font-semibold text-gray-700">Profile</h2>
        <p className="mt-2 text-sm text-gray-400">Upload a CSV to begin.</p>
      </section>
    )
  }

  const { profile } = dataset
  return (
    <section
      data-testid="profile-panel"
      className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">Profile</h2>
        <span
          data-testid="profile-shape"
          className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600"
        >
          {profile.row_count.toLocaleString()} rows × {profile.col_count} cols
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-xs uppercase tracking-wide text-gray-400">
              <th className="py-2 pr-4 font-medium">Column</th>
              <th className="py-2 pr-4 font-medium">Type</th>
              <th className="py-2 pr-4 font-medium">Non-null</th>
              <th className="py-2 pr-4 font-medium">Missing %</th>
              <th className="py-2 pr-4 font-medium">Min</th>
              <th className="py-2 pr-4 font-medium">Max</th>
            </tr>
          </thead>
          <tbody data-testid="profile-rows">
            {profile.columns.map((c) => (
              <tr key={c.name} className="border-b border-gray-100 last:border-0">
                <td className="py-2 pr-4 font-medium text-gray-800">{c.name}</td>
                <td className="py-2 pr-4">
                  <span className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-xs text-gray-600">
                    {c.dtype}
                  </span>
                </td>
                <td className="py-2 pr-4 text-gray-700">{c.non_null.toLocaleString()}</td>
                <td className="py-2 pr-4 text-gray-700">
                  {(c.missing_pct * 100 < 0.01 && c.missing_pct > 0
                    ? '<0.01'
                    : (c.missing_pct * 100).toFixed(2)) + '%'}
                </td>
                <td className="py-2 pr-4 font-mono text-xs text-gray-600">{fmt(c.min)}</td>
                <td className="py-2 pr-4 font-mono text-xs text-gray-600">{fmt(c.max)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4">
        <StubPanel title="Column annotations" testId="annotations-stub">
          Describe columns to guide the agent — editing coming soon.
        </StubPanel>
      </div>
    </section>
  )
}
