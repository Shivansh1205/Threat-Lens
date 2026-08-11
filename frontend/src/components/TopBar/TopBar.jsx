import { Search } from "lucide-react";
import ConnectionStatus from "../ConnectionStatus/ConnectionStatus";
import ThemeToggle from "../ThemeToggle/ThemeToggle";

// Search is a visual placeholder only in this phase — wiring it up to
// actually filter threats/users/IPs is explicitly optional/future per the
// prompt's scope.
export default function TopBar({ connectionStatus, collectorStatus }) {
  return (
    <header className="flex items-center justify-between gap-4 border-b border-slate-200 bg-white/80 px-6 py-4 backdrop-blur dark:border-white/5 dark:bg-slate-950/60">
      <div className="relative w-full max-w-md">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
        <input
          type="text"
          disabled
          placeholder="Search threats, users, IPs... (coming soon)"
          className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-9 pr-3 text-sm text-slate-500 placeholder:text-slate-400 dark:border-white/10 dark:bg-slate-900/60 dark:text-slate-400 dark:placeholder:text-slate-600"
        />
      </div>
      <div className="flex items-center gap-2"><span className={`hidden rounded-full border px-3 py-1.5 text-xs font-medium sm:inline ${collectorStatus === "live" ? "border-emerald-500/20 text-emerald-600 dark:text-emerald-300" : "border-amber-500/20 text-amber-600 dark:text-amber-300"}`}>Collector {collectorStatus}</span><ConnectionStatus status={connectionStatus} /><ThemeToggle /></div>
    </header>
  );
}
