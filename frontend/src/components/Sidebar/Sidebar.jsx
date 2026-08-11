import { Bell, Bot, FileText, LayoutDashboard, Radar, Settings, ShieldCheck, Users } from "lucide-react";
import { NavLink } from "react-router-dom";

const NAV_ITEMS = [
  { label: "Dashboard", icon: LayoutDashboard, to: "/" },
  { label: "Threat Feed", icon: Radar, to: "/threat-feed" },
  { label: "User Analytics", icon: Users, to: "/users" },
  { label: "Alerts", icon: Bell, to: "/alerts" },
  { label: "Assistant", icon: Bot, to: "/assistant" },
  { label: "Reports", icon: FileText, to: "/reports" },
  { label: "Settings", icon: Settings, to: "/settings" },
];

export default function Sidebar() {
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-slate-200 bg-white/90 px-3 py-4 dark:border-white/5 dark:bg-slate-950/80">
      <div className="mb-6 flex items-center gap-2 px-2">
        <ShieldCheck className="h-6 w-6 text-sky-400" />
        <span className="text-lg font-bold text-slate-900 dark:text-slate-50">ThreatLens</span>
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
                  isActive
                    ? "bg-sky-500/10 text-sky-700 dark:text-sky-300"
                    : "text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-200"
                }`
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ) : null
        )}
      </nav>

      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:border-white/5 dark:bg-slate-900/60">
        Final-year project — BIT CSE 2025–26
      </div>
    </aside>
  );
}
