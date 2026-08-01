import { useMemo } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const BUCKET_MS = 5 * 60 * 1000; // 5-minute buckets

/**
 * Buckets the currently loaded alert feed into 5-minute windows and plots
 * alert count over time. Reflects only what's in memory (capped at 200
 * alerts by useAlertStream) — under heavy traffic the visible time window
 * will be shorter than under light traffic, since the buffer holds a fixed
 * *count* of alerts, not a fixed *time range*. Good enough for "is activity
 * trending up or down right now" at a glance.
 */
export default function ThreatActivityChart({ alerts }) {
  const data = useMemo(() => {
    if (alerts.length === 0) return [];

    const buckets = new Map();
    for (const alert of alerts) {
      const ts = new Date(alert.created_at).getTime();
      if (Number.isNaN(ts)) continue;
      const bucketStart = Math.floor(ts / BUCKET_MS) * BUCKET_MS;
      buckets.set(bucketStart, (buckets.get(bucketStart) ?? 0) + 1);
    }

    return Array.from(buckets.entries())
      .sort(([a], [b]) => a - b)
      .map(([bucketStart, count]) => ({
        time: new Date(bucketStart).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        count,
      }));
  }, [alerts]);

  if (data.length === 0) {
    return <EmptyState />;
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="time" stroke="#64748b" fontSize={11} />
        <YAxis stroke="#64748b" fontSize={11} allowDecimals={false} />
        <Tooltip
          contentStyle={{ background: "#0f172a", border: "1px solid #1e293b", fontSize: 12 }}
          labelStyle={{ color: "#cbd5e1" }}
        />
        <Line type="monotone" dataKey="count" stroke="#38bdf8" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

function EmptyState() {
  return (
    <p className="flex h-[220px] items-center justify-center text-sm text-slate-500">No activity yet.</p>
  );
}
