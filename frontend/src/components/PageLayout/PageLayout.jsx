import Sidebar from "../Sidebar/Sidebar";

/**
 * Shared shell for every page besides Dashboard (which keeps its own
 * bespoke TopBar with live connection status — that's specific to the
 * WebSocket feed and doesn't apply here). Alerts / User Analytics /
 * Assistant all just need a sidebar, a simple title header, and a
 * scrollable main area, so this avoids repeating that structure three
 * times.
 */
export default function PageLayout({ title, subtitle, children }) {
  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      <Sidebar />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-white/5 bg-slate-950/60 px-6 py-4">
          <h1 className="text-lg font-semibold text-slate-100">{title}</h1>
          {subtitle && <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>}
        </header>

        <main className="flex-1 space-y-6 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
