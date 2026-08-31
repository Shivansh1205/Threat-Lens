import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { SEVERITY_BADGE_CLASSES } from "../../constants/severity";
import { formatRelativeTime } from "../../utils/time";

function SeverityBadge({ severity }) {
  const cls = SEVERITY_BADGE_CLASSES[severity] ?? "bg-slate-700 text-slate-200";
  return (
    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${cls}`}>
      {severity}
    </span>
  );
}

function AlertRow({ alert }) {
  const [expanded, setExpanded] = useState(false);
  const hasExplanation = alert.explanation != null;
  const mitigationSteps = Array.isArray(alert.mitigation_steps) ? alert.mitigation_steps : [];

  return (
    <li className="rounded-lg border border-white/5 bg-slate-900/40 px-3 py-2">
      <button
        type="button"
        onClick={() => hasExplanation && setExpanded((e) => !e)}
        className={`flex w-full items-center gap-3 text-left ${hasExplanation ? "cursor-pointer" : "cursor-default"}`}
      >
        {hasExplanation ? (
          expanded ? (
            <ChevronDown className="h-4 w-4 shrink-0 text-slate-500" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-slate-500" />
          )
        ) : (
          <span className="h-4 w-4 shrink-0" />
        )}
        <SeverityBadge severity={alert.severity} />
        <span className="min-w-0 flex-1 truncate text-sm text-slate-200">{alert.message}</span>
        <span className="shrink-0 text-xs font-medium text-slate-400">{alert.user_id}</span>
        <span className="hidden shrink-0 text-xs text-slate-500 sm:inline">{alert.alert_type}</span>
        <span className="shrink-0 text-xs font-semibold text-slate-300">{alert.score}</span>
        <span className="shrink-0 text-xs text-slate-500">{formatRelativeTime(alert.created_at)}</span>
      </button>

      {expanded && hasExplanation && (
        <div className="mt-2 space-y-2 border-t border-white/5 pl-7 pt-2 text-sm">
          <p className="text-slate-300">{alert.explanation}</p>
          {mitigationSteps.length > 0 && (
            <ul className="list-disc space-y-1 pl-4 text-slate-400">
              {mitigationSteps.map((step, i) => (
                <li key={i}>
                  <span className="font-medium text-slate-300">{step.action}</span>
                  {step.justification && <span> — {step.justification}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {!hasExplanation && (
        <div className="mt-1 pl-7 text-xs text-slate-500">
          Detection recorded. Ask the administrator assistant for analysis.
        </div>
      )}
      {alert.evidence && (
        <div className="mt-2 flex flex-wrap gap-2 pl-7 text-[11px] text-slate-400">
          {alert.evidence.method && <span>{alert.evidence.method}</span>}
          {alert.evidence.endpoint && <span className="max-w-xs truncate text-sky-300">{alert.evidence.endpoint}</span>}
          {alert.evidence.http_status && <span>HTTP {alert.evidence.http_status}</span>}
          {alert.evidence.ip && <span>{alert.evidence.ip}</span>}
          {alert.evidence.count && <span>{alert.evidence.count} events / {alert.evidence.window_seconds}s</span>}
        </div>
      )}
    </li>
  );
}

/**
 * Live-updating alert list. `alerts` is owned by useAlertStream (Dashboard
 * passes it down) — most recent first, WebSocket-supplemented, capped at
 * 200. Detection and scoring happen locally; an administrator can request
 * deeper analysis from the assistant when needed.
 */
export default function AlertFeed({ alerts }) {
  if (alerts.length === 0) {
    return <p className="text-sm text-slate-500">No alerts yet.</p>;
  }

  return (
    <ul className="max-h-[520px] space-y-2 overflow-y-auto pr-1">
      {alerts.map((alert) => (
        <AlertRow key={alert.id} alert={alert} />
      ))}
    </ul>
  );
}
