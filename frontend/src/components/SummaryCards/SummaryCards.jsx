import { Activity, AlertTriangle, ShieldAlert, Users } from "lucide-react";

const ONE_DAY_MS = 24 * 60 * 60 * 1000;

/**
 * Four top-line KPI cards, all computed client-side from the currently
 * loaded (capped-at-200, see useAlertStream) alert feed — there's no
 * dedicated aggregation endpoint, so these are honest approximations
 * bounded by what's actually in memory, not true all-time totals. Each
 * card's subtitle says so explicitly rather than implying more precision
 * than the data supports. Definitions (documented per the prompt's "your
 * call" on exact metrics):
 *
 * - Total Alerts (24h): loaded alerts created within the last 24h.
 * - Active Threats: loaded alerts with resolved === false. No resolution
 *   workflow exists yet (PHASES.md Phase 7 — admin controls), so nothing
 *   currently ever sets resolved=true; this will typically equal the total
 *   loaded count today, but is wired correctly for when that workflow lands.
 * - Total Users: distinct user_id values seen across the loaded feed — NOT
 *   a true system-wide user count (no GET /api/v1/users endpoint exists to
 *   back that), labeled with a subtitle to make the scope clear.
 * - Suspicious Activity: loaded alerts with severity HIGH or CRITICAL.
 */
export default function SummaryCards({ alerts }) {
  const now = Date.now();
  const last24h = alerts.filter((a) => now - new Date(a.created_at).getTime() <= ONE_DAY_MS);
  const active = alerts.filter((a) => !a.resolved);
  const distinctUsers = new Set(alerts.map((a) => a.user_id));
  const suspicious = alerts.filter((a) => a.severity === "HIGH" || a.severity === "CRITICAL");

  const cards = [
    {
      label: "Total Alerts (24h)",
      hint: "in current feed",
      value: last24h.length,
      icon: AlertTriangle,
      accent: "text-sky-400",
    },
    {
      label: "Active Threats",
      hint: "unresolved, in feed",
      value: active.length,
      icon: ShieldAlert,
      accent: "text-red-400",
    },
    {
      label: "Total Users",
      hint: "distinct, in feed",
      value: distinctUsers.size,
      icon: Users,
      accent: "text-emerald-400",
    },
    {
      label: "Suspicious Activity",
      hint: "HIGH + CRITICAL",
      value: suspicious.length,
      icon: Activity,
      accent: "text-amber-400",
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map(({ label, hint, value, icon: Icon, accent }) => (
        <div
          key={label}
          className="rounded-xl border border-white/5 bg-slate-900/60 p-4 shadow-lg shadow-black/20"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</span>
            <Icon className={`h-4 w-4 ${accent}`} />
          </div>
          <p className="mt-2 text-2xl font-semibold text-slate-50">{value}</p>
          <p className="mt-0.5 text-[11px] text-slate-500">{hint}</p>
        </div>
      ))}
    </div>
  );
}
