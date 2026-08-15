import { useMemo } from "react";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { SEVERITY_COLORS, SEVERITY_ORDER } from "../../constants/severity";
import { useTheme } from "../../context/ThemeContext";

/** Donut chart of the loaded alert feed, grouped by severity. */
export default function SeverityBreakdown({ alerts }) {
  const { theme } = useTheme();
  const data = useMemo(() => {
    const counts = Object.fromEntries(SEVERITY_ORDER.map((s) => [s, 0]));
    for (const alert of alerts) {
      if (counts[alert.severity] !== undefined) counts[alert.severity] += 1;
    }
    return SEVERITY_ORDER.map((severity) => ({ name: severity, value: counts[severity] }));
  }, [alerts]);

  const total = data.reduce((sum, d) => sum + d.value, 0);

  if (total === 0) {
    return (
      <p className="flex h-[220px] items-center justify-center text-sm text-slate-500">No alerts yet.</p>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          innerRadius={55}
          outerRadius={80}
          paddingAngle={2}
          stroke="none"
        >
          {data.map((entry) => (
            <Cell key={entry.name} fill={SEVERITY_COLORS[entry.name]} />
          ))}
        </Pie>
        <Tooltip contentStyle={{ background: theme === "dark" ? "#0f172a" : "#fff", color: theme === "dark" ? "#e2e8f0" : "#0f172a", border: `1px solid ${theme === "dark" ? "#334155" : "#e2e8f0"}`, borderRadius: 10, fontSize: 12 }} />
        <Legend wrapperStyle={{ color: theme === "dark" ? "#cbd5e1" : "#475569", fontSize: 12 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}
