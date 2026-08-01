import { Bell, Bot, FileText, LayoutDashboard, Radar, Settings, ShieldCheck, Users } from "lucide-react";
import { NavLink } from "react-router-dom";

// Dashboard, Alerts, User Analytics, and Assistant are now real routes
// (react-router-dom, added this phase). Threat Feed / Reports / Settings
// still have no page behind them, so they stay disabled placeholders
// rather than linking somewhere broken.
const NAV_ITEMS = [
  { label: "Dashboard", icon: LayoutDashboard, to: "/" },
  { label: "Threat Feed", icon: Radar, to: null },
  { label: "User Analytics", icon: Users, to: "/users" },
  { label: "Alerts", icon: Bell, to: "/alerts" },
  { label: "Assistant", icon: Bot, to: "/assistant" },
  { label: "Reports", icon: FileText, to: null },
  { label: "Settings", icon: Settings, to: null },
];

export default function Sidebar() {
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-white/5 bg-slate-950/80 px-3 py-4">
      <div className="mb-6 flex items-center gap-2 px-2">
        <ShieldCheck className="h-6 w-6 text-sky-400" />
        <span className="text-lg font-bold text-slate-50">ThreatLens</span>
      </div>

      <nav className="flex flex-1 flex-col gap-1">
        {NAV_ITEMS.map(({ label, icon: Icon, to }) =>
          to ? (
            <NavLink
              key={label}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive ? "bg-sky-500/10 text-sky-300" : "text-slate-400 hover:text-slate-200"
                }`
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ) : (
            <button
              key={label}
              type="button"
              disabled
              title="Coming soon"
              className="flex cursor-default items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600"
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          )
        )}
      </nav>

      <div className="rounded-lg border border-white/5 bg-slate-900/60 px-3 py-2 text-xs text-slate-500">
        Final-year project — BIT CSE 2025–26
      </div>
    </aside>
  );
}
