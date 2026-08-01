import { Search } from "lucide-react";
import ConnectionStatus from "../ConnectionStatus/ConnectionStatus";

// Search is a visual placeholder only in this phase — wiring it up to
// actually filter threats/users/IPs is explicitly optional/future per the
// prompt's scope.
export default function TopBar({ connectionStatus }) {
  return (
    <header className="flex items-center justify-between border-b border-white/5 bg-slate-950/60 px-6 py-4">
      <div className="relative w-full max-w-md">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
        <input
          type="text"
          disabled
          placeholder="Search threats, users, IPs... (coming soon)"
          className="w-full rounded-lg border border-white/10 bg-slate-900/60 py-2 pl-9 pr-3 text-sm text-slate-400 placeholder:text-slate-600"
        />
      </div>
      <ConnectionStatus status={connectionStatus} />
    </header>
  );
}
