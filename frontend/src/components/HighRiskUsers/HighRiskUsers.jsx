import { useHighRiskUsers } from "../../hooks/useHighRiskUsers";

/**
 * Ranked list of users by rolling risk score (GET /api/v1/users/high-risk).
 * Owns its own data hook (unlike AlertFeed, which receives `alerts` as a
 * prop) since no other component on this dashboard needs this data —
 * keeping the fetch local avoids threading an unused prop through Dashboard.
 */
export default function HighRiskUsers() {
  const { users, error } = useHighRiskUsers(10);

  if (error) {
    return <p className="text-sm text-red-400">Could not load high-risk users: {error}</p>;
  }

  if (users.length === 0) {
    return <p className="text-sm text-slate-500">No high-risk users right now.</p>;
  }

  const maxScore = Math.max(...users.map((u) => u.user_risk_score), 1);

  return (
    <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {users.map((u) => (
        <li key={u.user_id} className="space-y-1.5 rounded-lg border border-white/5 bg-slate-900/40 p-3">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium text-slate-200">{u.user_id}</span>
            <span className="text-xs text-slate-400">{u.login_count} logins</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800">
              <div
                className="h-full rounded-full bg-gradient-to-r from-amber-500 to-red-500"
                style={{ width: `${(u.user_risk_score / maxScore) * 100}%` }}
              />
            </div>
            <span className="w-10 shrink-0 text-right text-xs font-semibold text-slate-300">
              {u.user_risk_score.toFixed(0)}
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}
