// Dependency-free chart primitives for Conversation Intelligence, built as plain
// Tailwind divs (responsive, no chart library). Colors come from the validated
// data-viz palette: a single blue hue for magnitude bars, and the fixed status
// palette (good / muted / critical) for Positive / Neutral / Negative outcomes.
// Every mark is directly labelled, so identity is never carried by color alone,
// and each bar exposes a native tooltip via `title`. Marks are thin with a
// rounded data-end and a recessive track. The app renders light-only.
'use client'

// --- palette (light surface #fcfcfb) ---------------------------------------
export const SERIES_BLUE = '#2a78d6' // categorical slot 1 — magnitude bars
export const OUTCOME_COLOR: Record<string, string> = {
  Positive: '#0ca30c', // status: good
  Neutral: '#898781', // muted ink — semantic "nothing", always label-paired
  Negative: '#d03b3b', // status: critical
}

function fmt(n: number): string {
  return n.toLocaleString()
}

// A horizontal magnitude bar list: one labelled, rounded-end bar per row, widths
// proportional to the largest value. Used for intent breakdown, outcome breakdown
// and the calls-per-caller distribution.
export interface BarDatum {
  label: string
  value: number
  color?: string
  // Optional right-aligned value caption; defaults to the formatted count.
  valueLabel?: string
  // Optional tooltip; defaults to `${label}: ${value}`.
  title?: string
}

export function BarChart({
  data,
  testId,
  emptyLabel = 'No data',
}: {
  data: BarDatum[]
  testId?: string
  emptyLabel?: string
}) {
  const max = Math.max(1, ...data.map((d) => d.value))
  if (data.length === 0) {
    return (
      <p className="py-6 text-center text-xs text-gray-400">{emptyLabel}</p>
    )
  }
  return (
    <div data-testid={testId} className="space-y-2">
      {data.map((d) => {
        const pct = Math.max(d.value > 0 ? 2 : 0, (d.value / max) * 100)
        return (
          <div key={d.label} className="flex items-center gap-3 text-sm">
            <div className="w-32 shrink-0 truncate text-right text-xs font-medium text-gray-600">
              {d.label}
            </div>
            <div className="relative h-4 flex-1 overflow-hidden rounded-sm bg-gray-100">
              <div
                className="h-full rounded-r-sm"
                style={{ width: `${pct}%`, backgroundColor: d.color ?? SERIES_BLUE }}
                title={d.title ?? `${d.label}: ${fmt(d.value)}`}
              />
            </div>
            <div className="w-20 shrink-0 text-right text-xs tabular-nums text-gray-700">
              {d.valueLabel ?? fmt(d.value)}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// A 100%-width stacked bar per row (Positive / Neutral / Negative segments),
// with a 2px gap between fills and a shared legend. Used for the outcome-by-intent
// cross-tab.
export interface StackedSegment {
  name: string
  value: number
  color: string
}

export interface StackedDatum {
  label: string
  segments: StackedSegment[]
}

function Legend({ items }: { items: { name: string; color: string }[] }) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1">
      {items.map((it) => (
        <span key={it.name} className="inline-flex items-center gap-1.5 text-xs text-gray-600">
          <span
            className="inline-block h-2.5 w-2.5 rounded-sm"
            style={{ backgroundColor: it.color }}
          />
          {it.name}
        </span>
      ))}
    </div>
  )
}

export function StackedBarChart({
  data,
  legend,
  testId,
}: {
  data: StackedDatum[]
  legend: { name: string; color: string }[]
  testId?: string
}) {
  return (
    <div data-testid={testId}>
      <Legend items={legend} />
      <div className="space-y-2">
        {data.map((d) => {
          const total = d.segments.reduce((s, seg) => s + seg.value, 0)
          return (
            <div key={d.label} className="flex items-center gap-3 text-sm">
              <div className="w-32 shrink-0 truncate text-right text-xs font-medium text-gray-600">
                {d.label}
              </div>
              <div className="flex h-4 flex-1 gap-[2px] overflow-hidden rounded-sm bg-gray-100">
                {total === 0 ? null : (
                  d.segments.map((seg) => {
                    const pct = (seg.value / total) * 100
                    if (pct <= 0) return null
                    return (
                      <div
                        key={seg.name}
                        className="h-full first:rounded-l-sm last:rounded-r-sm"
                        style={{ width: `${pct}%`, backgroundColor: seg.color }}
                        title={`${d.label} · ${seg.name}: ${fmt(seg.value)}`}
                      />
                    )
                  })
                )}
              </div>
              <div className="w-20 shrink-0 text-right text-xs tabular-nums text-gray-700">
                {fmt(total)}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// A responsive SVG line chart for ordered/time-series data (x is a sequence, y is
// a magnitude). Recessive baseline, 2px line, ≥8px dots, min/max y ticks.
export function LineChart({ data, testId }: { data: BarDatum[]; testId?: string }) {
  if (data.length < 2) return null
  const W = 720
  const H = 200
  const padL = 8
  const padR = 8
  const padT = 12
  const padB = 26
  const values = data.map((d) => d.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const innerW = W - padL - padR
  const innerH = H - padT - padB
  const x = (i: number) => padL + (data.length === 1 ? innerW / 2 : (i / (data.length - 1)) * innerW)
  const y = (v: number) => padT + innerH - ((v - min) / span) * innerH
  const pts = data.map((d, i) => `${x(i)},${y(d.value)}`).join(' ')
  // Label a subset of x ticks to avoid collisions.
  const step = Math.max(1, Math.ceil(data.length / 6))
  return (
    <div data-testid={testId} className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-48 w-full" role="img">
        {/* baseline */}
        <line x1={padL} y1={padT + innerH} x2={W - padR} y2={padT + innerH} stroke="#e1e0d9" strokeWidth={1} />
        <polyline points={pts} fill="none" stroke={SERIES_BLUE} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {data.map((d, i) => (
          <circle key={i} cx={x(i)} cy={y(d.value)} r={4} fill={SERIES_BLUE}>
            <title>{`${d.label}: ${fmt(d.value)}`}</title>
          </circle>
        ))}
        {data.map((d, i) =>
          i % step === 0 || i === data.length - 1 ? (
            <text key={`t${i}`} x={x(i)} y={H - 8} textAnchor="middle" fontSize={11} fill="#898781">
              {d.label.length > 10 ? d.label.slice(0, 9) + '…' : d.label}
            </text>
          ) : null,
        )}
      </svg>
    </div>
  )
}

// Heuristic: does this label sequence read as an ordered axis (dates or an
// increasing numeric/time sequence) → line chart; otherwise categorical → bar.
export function looksOrdered(labels: string[]): boolean {
  if (labels.length < 3) return false
  const dateLike = labels.every((l) => /^\d{4}([-/]\d{1,2}([-/]\d{1,2})?)?$/.test(l) || !Number.isNaN(Date.parse(l)))
  if (dateLike) return true
  const nums = labels.map((l) => Number(l))
  if (nums.every((n) => !Number.isNaN(n))) {
    // monotonic (a real sequence, e.g. hours/months as numbers)
    const inc = nums.every((n, i) => i === 0 || n >= nums[i - 1])
    return inc
  }
  return false
}
