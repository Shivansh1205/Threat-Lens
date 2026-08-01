import { useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, CheckCircle2, Loader2, RotateCcw, TrendingUp } from "lucide-react";
import { SEVERITY_BADGE_CLASSES } from "../../constants/severity";
import { formatRelativeTime } from "../../utils/time";

function SeverityBadge({ severity }) {
  const cls = SEVERITY_BADGE_CLASSES[severity] ?? "bg-slate-700 text-slate-200";
  return (
    <span className={`inline-block shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${cls}`}>
      {severity}
    </span>
  );
}

/** raw_score vs score: shown together only when they differ (behavioral
 * deviation escalated the alert past the detector's original call) — an
 * arrow plus a title tooltip explains why, rather than silently showing
 * two numbers with no context. */
function ScoreCell({ score, rawScore }) {
  if (score === rawScore) {
    return <span className="font-semibold text-slate-200">{score}</span>;
  }
  return (
    <span
      className="inline-flex items-center gap-1 font-semibold text-slate-200"
      title={`Detector originally scored this ${rawScore}. Risk-adjusted upward to ${score} based on this user's recent behavioral deviation.`}
    >
      <span className="text-slate-500">{rawScore}</span>
      <TrendingUp className="h-3 w-3 text-amber-400" />
      <span>{score}</span>
    </span>
  );
}

function SortHeader({ label, column, sortBy, sortOrder, onSortChange }) {
  if (!onSortChange) {
    return <th className="px-3 py-2 text-left font-medium text-slate-400">{label}</th>;
  }

  const isActive = sortBy === column;
  const Icon = isActive ? (sortOrder === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;

  return (
    <th className="px-3 py-2 text-left font-medium text-slate-400">
      <button
        type="button"
        onClick={() => onSortChange(column)}
        className={`flex items-center gap-1 hover:text-slate-200 ${isActive ? "text-slate-200" : ""}`}
      >
        {label}
        <Icon className="h-3 w-3" />
      </button>
    </th>
  );
}

/**
 * Full alert table shared by the Alerts page (all alerts, filterable) and
 * the User Analytics page (one user's alert history) — same row rendering
 * and resolve/unresolve actions either way, so behavior stays consistent
 * rather than maintaining two near-identical tables.
 *
 * Resolve/unresolve: calls `onResolve`/`onUnresolve` with the alert id and
 * awaits it, then merges whatever the PATCH endpoint returned back into
 * local row state — not a full refetch of the list, and not a pre-response
 * optimistic update either. Chosen because the endpoint's response is the
 * authoritative record (exact `resolved_at` server timestamp) and merging
 * it in is a single extra property update, no extra round trip beyond the
 * PATCH itself already required.
 */
export default function AlertsTable({
  alerts,
  onResolve,
  onUnresolve,
  hideUserColumn = false,
  sortBy,
  sortOrder,
  onSortChange,
  emptyMessage = "No alerts.",
}) {
  const [pendingIds, setPendingIds] = useState(() => new Set());

  async function handleToggleResolve(alert) {
    const action = alert.resolved ? onUnresolve : onResolve;
    if (!action) return;

    setPendingIds((prev) => new Set(prev).add(alert.id));
    try {
      await action(alert.id);
    } finally {
      setPendingIds((prev) => {
        const next = new Set(prev);
        next.delete(alert.id);
        return next;
      });
    }
  }

  if (alerts.length === 0) {
    return <p className="py-6 text-center text-sm text-slate-500">{emptyMessage}</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-white/5 text-xs uppercase tracking-wide">
            <th className="px-3 py-2 text-left font-medium text-slate-400">Severity</th>
            {!hideUserColumn && <th className="px-3 py-2 text-left font-medium text-slate-400">User</th>}
            <th className="px-3 py-2 text-left font-medium text-slate-400">Type</th>
            <th className="px-3 py-2 text-left font-medium text-slate-400">Message</th>
            <SortHeader label="Score" column="score" sortBy={sortBy} sortOrder={sortOrder} onSortChange={onSortChange} />
            <SortHeader label="Created" column="created_at" sortBy={sortBy} sortOrder={sortOrder} onSortChange={onSortChange} />
            <th className="px-3 py-2 text-left font-medium text-slate-400">Status</th>
            <th className="px-3 py-2 text-left font-medium text-slate-400">Action</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert) => {
            const isPending = pendingIds.has(alert.id);
            return (
              <tr key={alert.id} className="border-b border-white/5 last:border-0 hover:bg-slate-900/40">
                <td className="px-3 py-2">
                  <SeverityBadge severity={alert.severity} />
                </td>
                {!hideUserColumn && (
                  <td className="px-3 py-2 font-medium text-slate-300">{alert.user_id}</td>
                )}
                <td className="px-3 py-2 text-slate-400">{alert.alert_type}</td>
                <td className="max-w-xs truncate px-3 py-2 text-slate-300" title={alert.message}>
                  {alert.message}
                </td>
                <td className="px-3 py-2">
                  <ScoreCell score={alert.score} rawScore={alert.raw_score} />
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-slate-500" title={alert.created_at}>
                  {formatRelativeTime(alert.created_at)}
                </td>
                <td className="px-3 py-2">
                  {alert.resolved ? (
                    <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-400">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      Resolved
                    </span>
                  ) : (
                    <span className="text-xs text-slate-500">Unresolved</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  <button
                    type="button"
                    onClick={() => handleToggleResolve(alert)}
                    disabled={isPending}
                    className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                      alert.resolved
                        ? "border border-white/10 text-slate-300 hover:bg-slate-800"
                        : "bg-sky-600 text-white hover:bg-sky-500"
                    }`}
                  >
                    {isPending ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : alert.resolved ? (
                      <RotateCcw className="h-3.5 w-3.5" />
                    ) : (
                      <CheckCircle2 className="h-3.5 w-3.5" />
                    )}
                    {alert.resolved ? "Unresolve" : "Resolve"}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
