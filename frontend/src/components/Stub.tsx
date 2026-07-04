// Labelled NON-FUNCTIONAL stubs. Every not-yet-built surface renders here,
// visibly greyed with a "Coming soon" badge, so a stub is never mistaken for a
// bug. See spec/ui.md "Stub discipline".

export function ComingSoonBadge() {
  return (
    <span
      data-testid="coming-soon-badge"
      className="ml-2 inline-flex items-center rounded-full bg-gray-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gray-500"
    >
      Coming soon
    </span>
  )
}

interface StubProps {
  title: string
  children?: React.ReactNode
  testId?: string
}

// A greyed-out, non-interactive placeholder panel.
export function StubPanel({ title, children, testId }: StubProps) {
  return (
    <section
      data-testid={testId}
      data-stub="true"
      aria-disabled="true"
      className="pointer-events-none select-none rounded-xl border border-dashed border-gray-300 bg-gray-50 p-4 opacity-60"
    >
      <div className="flex items-center">
        <h3 className="text-sm font-semibold text-gray-500">{title}</h3>
        <ComingSoonBadge />
      </div>
      {children && <div className="mt-2 text-xs text-gray-400">{children}</div>}
    </section>
  )
}

// A greyed-out inline stub button/chip.
export function StubButton({ label, testId }: { label: string; testId?: string }) {
  return (
    <span
      data-testid={testId}
      data-stub="true"
      aria-disabled="true"
      className="pointer-events-none inline-flex cursor-not-allowed select-none items-center rounded-lg border border-dashed border-gray-300 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-400 opacity-70"
    >
      {label}
      <ComingSoonBadge />
    </span>
  )
}
