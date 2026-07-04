// Left rail. Sessions list + daily-cost total are STUBS in Phase 1
// (greyed, "Coming soon"). See spec/ui.md.
import { ComingSoonBadge } from './Stub'

export function Sidebar() {
  return (
    <aside
      data-testid="sessions-sidebar"
      data-stub="true"
      className="hidden w-64 shrink-0 border-r border-gray-200 bg-white p-4 md:block"
    >
      <div className="flex items-center">
        <h2 className="text-sm font-semibold text-gray-500">Sessions</h2>
        <ComingSoonBadge />
      </div>

      <div className="pointer-events-none mt-4 select-none space-y-2 opacity-60">
        {['Untitled analysis', 'Sales Q3', 'Churn review'].map((name) => (
          <div
            key={name}
            className="rounded-lg border border-dashed border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-400"
          >
            {name}
          </div>
        ))}
      </div>

      <div
        data-testid="daily-cost-total"
        data-stub="true"
        className="pointer-events-none mt-6 select-none rounded-lg border border-dashed border-gray-200 bg-gray-50 p-3 opacity-60"
      >
        <div className="flex items-center">
          <span className="text-xs font-semibold text-gray-500">Daily cost total</span>
          <ComingSoonBadge />
        </div>
        <div className="mt-1 text-lg font-semibold text-gray-300">$—.——</div>
      </div>
    </aside>
  )
}
