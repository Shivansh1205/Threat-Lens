import { useState } from "react";
import { Search } from "lucide-react";
import AlertsTable from "../components/AlertsTable/AlertsTable";
import PageLayout from "../components/PageLayout/PageLayout";
import { useAlertsQuery } from "../hooks/useAlertsQuery";
import { useHighRiskUsers } from "../hooks/useHighRiskUsers";
import { useUserProfile } from "../hooks/useUserProfile";
import { formatDaySpan, formatDuration, formatHourOfDay } from "../utils/format";

// Rough risk tiers for the summary card's color, not tied to the backend's
// severity buckets (those score alerts 0-100 by SEVERITY_LOW/MEDIUM/HIGH_MAX
// config; user_risk_score is a different, unbounded-but-clamped-to-100
// rolling metric — reusing the alert severity thresholds here would imply a
// precision this number doesn't have). Picked as reasonable defaults, not
// derived from any config value.
function riskTier(score) {
  if (score >= 50) return { label: "High", className: "text-red-400" };
  if (score >= 20) return { label: "Elevated", className: "text-amber-400" };
  return { label: "Low", className: "text-emerald-400" };
}

function SummaryCard({ label, value, hint, accentClassName = "text-slate-100" }) {
  return (
    <div className="rounded-xl border border-white/5 bg-slate-900/60 p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${accentClassName}`}>{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-slate-500">{hint}</p>}
    </div>
  );
}

/**
 * Inspect a single user's full behavioral profile — the deep-dive view the
 * compact Dashboard `HighRiskUsers` list doesn't provide (that's a ranked
 * summary across many users; this is everything about one). Read-only, per
 * scope: no editing, and no historical risk-score time series, since the DB
 * only ever stores the CURRENT `user_risk_score` — there's no history table
 * to reconstruct one from (see `BehaviorProfile` — a single row per user,
 * mutated in place, not an append-only log). Noted here rather than faked.
 */
export default function UserAnalytics() {
  const [inputValue, setInputValue] = useState("");
  const [selectedUserId, setSelectedUserId] = useState("");

  const { users: highRiskUsers } = useHighRiskUsers(20);
  const { profile, notFound, loading, error } = useUserProfile(selectedUserId);

  const alertsParams = selectedUserId
    ? { user_id: selectedUserId, limit: 50, sort_by: "created_at", sort_order: "desc" }
    : null;
  const {
    alerts,
    loading: alertsLoading,
    resolveAlert,
    unresolveAlert,
  } = useAlertsQuery(alertsParams);

  function handleSubmit(e) {
    e.preventDefault();
    const trimmed = inputValue.trim();
    if (trimmed) setSelectedUserId(trimmed);
  }

  return (
    <PageLayout title="User Analytics" subtitle="Inspect a single user's behavioral baseline">
      <div className="rounded-xl border border-white/5 bg-slate-900/40 p-4">
        <form onSubmit={handleSubmit} className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[220px] max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Enter a user_id..."
              className="w-full rounded-lg border border-white/10 bg-slate-900 py-2 pl-9 pr-3 text-sm text-slate-100 placeholder:text-slate-600 focus:border-sky-500 focus:outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={!inputValue.trim()}
            className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Inspect
          </button>

          {highRiskUsers.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <span>Quick pick:</span>
              {highRiskUsers.slice(0, 8).map((u) => (
                <button
                  key={u.user_id}
                  type="button"
                  onClick={() => {
                    setInputValue(u.user_id);
                    setSelectedUserId(u.user_id);
                  }}
                  className="rounded-full border border-white/10 px-2.5 py-1 text-slate-300 hover:border-sky-500 hover:text-sky-300"
                >
                  {u.user_id}
                </button>
              ))}
            </div>
          )}
        </form>
      </div>

      {!selectedUserId && (
        <p className="rounded-xl border border-white/5 bg-slate-900/40 p-6 text-center text-sm text-slate-500">
          Enter a user_id above, or pick one from the quick-pick list, to inspect their profile.
        </p>
      )}

      {selectedUserId && loading && (
        <p className="rounded-xl border border-white/5 bg-slate-900/40 p-6 text-center text-sm text-slate-500">
          Loading profile for <span className="font-medium text-slate-300">{selectedUserId}</span>...
        </p>
      )}

      {selectedUserId && !loading && notFound && (
        <p className="rounded-xl border border-amber-500/20 bg-amber-950/20 p-6 text-center text-sm text-amber-300">
          No behavioral profile found for <span className="font-medium">{selectedUserId}</span> — this
          user_id has never sent a login event.
        </p>
      )}

      {selectedUserId && !loading && error && (
        <p className="rounded-xl border border-red-500/30 bg-red-950/30 p-6 text-center text-sm text-red-300">
          Could not load profile: {error}
        </p>
      )}

      {profile && (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <SummaryCard
              label="Risk score"
              value={profile.user_risk_score.toFixed(1)}
              hint={riskTier(profile.user_risk_score).label}
              accentClassName={riskTier(profile.user_risk_score).className}
            />
            <SummaryCard label="Deviation score" value={profile.deviation_score.toFixed(2)} hint="0.0 – 1.0, most recent event" />
            <SummaryCard label="Login count" value={profile.login_count} />
            <SummaryCard label="Total sessions" value={profile.total_sessions} />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <section className="rounded-xl border border-white/5 bg-slate-900/40 p-4">
              <h2 className="mb-3 text-sm font-semibold text-slate-300">Behavioral baseline</h2>
              <dl className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <dt className="text-slate-500">Typical login time</dt>
                  <dd className="text-slate-200">{formatHourOfDay(profile.typical_login_hour)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">Avg. session duration</dt>
                  <dd className="text-slate-200">{formatDuration(profile.avg_session_duration_seconds)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">Typical days between logins</dt>
                  <dd className="text-slate-200">{formatDaySpan(profile.typical_days_between_logins)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">First seen</dt>
                  <dd className="text-slate-200">{profile.days_since_first_seen.toFixed(1)} days ago</dd>
                </div>
              </dl>
              <p className="mt-3 border-t border-white/5 pt-3 text-[11px] text-slate-600">
                Historical risk-score trend isn't shown — the database keeps only the current
                value, not a time series, so there's nothing to chart.
              </p>
            </section>

            <section className="rounded-xl border border-white/5 bg-slate-900/40 p-4">
              <h2 className="mb-3 text-sm font-semibold text-slate-300">
                Known IPs ({profile.known_ips.length})
              </h2>
              {profile.known_ips.length === 0 ? (
                <p className="text-sm text-slate-500">No known IPs yet.</p>
              ) : (
                <ul className="flex flex-wrap gap-2">
                  {profile.known_ips.map((ip) => (
                    <li
                      key={ip}
                      className="rounded-full border border-white/10 bg-slate-950/60 px-2.5 py-1 font-mono text-xs text-slate-300"
                    >
                      {ip}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          <section className="rounded-xl border border-white/5 bg-slate-900/40 p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-300">Alert history</h2>
            {alertsLoading ? (
              <p className="py-6 text-center text-sm text-slate-500">Loading...</p>
            ) : (
              <AlertsTable
                alerts={alerts}
                onResolve={resolveAlert}
                onUnresolve={unresolveAlert}
                hideUserColumn
                emptyMessage="This user has no alerts."
              />
            )}
          </section>
        </>
      )}
    </PageLayout>
  );
}
