import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Brush,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getThreatType } from "../../constants/threatTypes";
import { useTheme } from "../../context/ThemeContext";

const BUCKET_MS = 30 * 60 * 1000;

export default function ThreatActivityChart({ alerts = [], activity = [], height = 280, showTimelineControl = false }) {
  const { theme } = useTheme();
  const [hiddenTypes, setHiddenTypes] = useState(() => new Set());

  const { data, types } = useMemo(() => {
    if (activity.length > 0) {
      const discovered = new Set();
      const firstTime = new Date(activity[0].time).getTime();
      const lastTime = new Date(activity[activity.length - 1].time).getTime();
      const multiDay = lastTime - firstTime > 24 * 60 * 60 * 1000;
      const rows = activity.map((point) => {
        const date = new Date(point.time);
        const row = {
          time: multiDay
            ? date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit" })
            : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          total: point.total,
        };
        for (const [type, count] of Object.entries(point.by_type || {})) {
          discovered.add(type);
          row[type] = count;
        }
        return row;
      });
      return { data: rows, types: Array.from(discovered) };
    }

    const buckets = new Map();
    const discovered = new Set();
    for (const alert of alerts) {
      const timestamp = new Date(alert.created_at).getTime();
      if (Number.isNaN(timestamp)) continue;
      const bucket = Math.floor(timestamp / BUCKET_MS) * BUCKET_MS;
      discovered.add(alert.alert_type);
      const row = buckets.get(bucket) || {};
      row[alert.alert_type] = (row[alert.alert_type] || 0) + 1;
      buckets.set(bucket, row);
    }
    const typeList = Array.from(discovered);
    return {
      types: typeList,
      data: Array.from(buckets.entries())
        .sort(([a], [b]) => a - b)
        .map(([timestamp, counts]) => ({
          time: new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          ...Object.fromEntries(typeList.map((type) => [type, counts[type] || 0])),
        })),
    };
  }, [activity, alerts]);

  if (data.length === 0 || types.length === 0) {
    return <p className="flex items-center justify-center text-sm text-slate-500" style={{ height }}>No threat activity in this period.</p>;
  }

  const axis = theme === "dark" ? "#64748b" : "#64748b";
  const grid = theme === "dark" ? "#1e293b" : "#e2e8f0";
  const tooltip = theme === "dark"
    ? { background: "#0f172a", border: "1px solid #334155", color: "#e2e8f0" }
    : { background: "#ffffff", border: "1px solid #e2e8f0", color: "#0f172a" };

  function toggleSeries(entry) {
    const type = entry.dataKey;
    setHiddenTypes((current) => {
      const next = new Set(current);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 12, right: 12, left: -18, bottom: 4 }}>
        <defs>
          {types.map((type) => {
            const meta = getThreatType(type);
            return (
              <linearGradient key={type} id={`threat-${type}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={meta.color} stopOpacity={0.75} />
                <stop offset="95%" stopColor={meta.color} stopOpacity={0.12} />
              </linearGradient>
            );
          })}
        </defs>
        <CartesianGrid strokeDasharray="4 4" stroke={grid} vertical={false} />
        <XAxis dataKey="time" stroke={axis} tickLine={false} axisLine={false} fontSize={11} minTickGap={28} />
        <YAxis stroke={axis} tickLine={false} axisLine={false} fontSize={11} allowDecimals={false} />
        <Tooltip
          contentStyle={{ ...tooltip, borderRadius: 10, fontSize: 12, boxShadow: "0 12px 32px rgba(15,23,42,.15)" }}
          labelStyle={{ color: tooltip.color, fontWeight: 600 }}
          formatter={(value, name) => [value, getThreatType(name).label]}
        />
        <Legend
          onClick={toggleSeries}
          formatter={(value) => (
            <span className={hiddenTypes.has(value) ? "text-slate-400 line-through" : "text-slate-600 dark:text-slate-300"}>
              {getThreatType(value).label}
            </span>
          )}
          wrapperStyle={{ cursor: "pointer", fontSize: 12, paddingTop: 10 }}
        />
        {types.map((type) => {
          const meta = getThreatType(type);
          return (
            <Area
              key={type}
              type="monotone"
              dataKey={type}
              stackId="threats"
              stroke={meta.color}
              strokeWidth={2}
              fill={`url(#threat-${type})`}
              hide={hiddenTypes.has(type)}
              activeDot={{ r: 4, strokeWidth: 0 }}
            />
          );
        })}
        {showTimelineControl && data.length > 1 && (
          <Brush
            dataKey="time"
            height={24}
            stroke={axis}
            fill={theme === "dark" ? "#0f172a" : "#f8fafc"}
            travellerWidth={10}
            tickFormatter={(value) => value}
          />
        )}
      </AreaChart>
    </ResponsiveContainer>
  );
}
