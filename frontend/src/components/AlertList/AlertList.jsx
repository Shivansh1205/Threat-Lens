const SEVERITY_STYLES = {
  LOW: "bg-sky-900 text-sky-200",
  MEDIUM: "bg-yellow-900 text-yellow-200",
  HIGH: "bg-orange-900 text-orange-200",
  CRITICAL: "bg-red-900 text-red-200",
};

function SeverityBadge({ severity }) {
  const style = SEVERITY_STYLES[severity] ?? "bg-gray-700 text-gray-200";
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-semibold ${style}`}>
      {severity}
    </span>
  );
}

/**
 * Minimal table of alerts. Phase 2 proof-of-flow — Phase 6 builds the real
 * dashboard (charts, high-risk users, chatbot).
 */
export default function AlertList({ alerts }) {
  if (!alerts || alerts.length === 0) {
    return <p className="text-gray-400">No alerts yet.</p>;
  }

  return (
    <table className="w-full border-collapse text-left text-sm">
      <thead>
        <tr className="border-b border-gray-700 text-gray-400">
          <th className="p-2">Time</th>
          <th className="p-2">User</th>
          <th className="p-2">Type</th>
          <th className="p-2">Severity</th>
          <th className="p-2">Score</th>
          <th className="p-2">Message</th>
        </tr>
      </thead>
      <tbody>
        {alerts.map((a) => (
          <tr key={a.id} className="border-b border-gray-800">
            <td className="p-2 text-gray-400">
              {new Date(a.created_at).toLocaleString()}
            </td>
            <td className="p-2">{a.user_id}</td>
            <td className="p-2">{a.alert_type}</td>
            <td className="p-2">
              <SeverityBadge severity={a.severity} />
            </td>
            <td className="p-2">{a.score}</td>
            <td className="p-2">{a.message}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
