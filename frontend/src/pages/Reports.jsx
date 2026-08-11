import { Download, FileBarChart, ShieldAlert, Target, TrendingUp } from "lucide-react";
import { useMemo, useState } from "react";
import PageLayout from "../components/PageLayout/PageLayout";
import ThreatActivityChart from "../components/ThreatActivityChart/ThreatActivityChart";
import { SEVERITY_COLORS, SEVERITY_ORDER } from "../constants/severity";
import { THREAT_TYPES, getThreatType } from "../constants/threatTypes";
import { useThreatMetrics } from "../hooks/useThreatMetrics";
import { buildMetricsQuery } from "../utils/reporting";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8002";

function toLocalInput(date) {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

const INITIAL_END = new Date();
const INITIAL_START = new Date(INITIAL_END.getTime() - 24 * 60 * 60 * 1000);

function SummaryCard({ label, value, icon: Icon, color }) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-white/5 dark:bg-slate-900/40">
      <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wide text-slate-500"><span>{label}</span><Icon className={`h-4 w-4 ${color}`} /></div>
      <p className="mt-2 text-2xl font-bold text-slate-900 dark:text-slate-50">{value}</p>
    </article>
  );
}

function Filter({ label, children }) {
  return <label className="text-xs font-medium text-slate-500"><span className="mb-1 block">{label}</span>{children}</label>;
}

export default function Reports() {
  const [preset, setPreset] = useState("24h");
  const [customStart, setCustomStart] = useState(toLocalInput(INITIAL_START));
  const [customEnd, setCustomEnd] = useState(toLocalInput(INITIAL_END));
  const [severity, setSeverity] = useState("");
  const [alertType, setAlertType] = useState("");
  const [resolved, setResolved] = useState("");
  const customRangeValid = preset !== "custom" || (
    customStart && customEnd && new Date(customStart).getTime() < new Date(customEnd).getTime()
  );

  const range = useMemo(() => {
    if (preset === "custom") {
      const start = customStart ? new Date(customStart) : INITIAL_START;
      const end = customEnd ? new Date(customEnd) : INITIAL_END;
      return { start: start.toISOString(), end: end.toISOString(), bucket_minutes: 60 };
    }
    const end = new Date();
    const duration = preset === "7d" ? 7 * 24 : preset === "30d" ? 30 * 24 : 24;
    const bucket = preset === "30d" ? 480 : preset === "7d" ? 120 : 30;
    return { start: new Date(end.getTime() - duration * 60 * 60 * 1000).toISOString(), end: end.toISOString(), bucket_minutes: bucket };
  }, [preset, customStart, customEnd]);

  const filters = useMemo(() => ({ ...range, severity, alert_type: alertType, resolved }), [range, severity, alertType, resolved]);
  const { data, loading, error } = useThreatMetrics(filters, customRangeValid);
  const summary = data?.summary || { total: 0, unresolved: 0, high_critical: 0, average_score: 0 };
  const maxTypeCount = Math.max(...(data?.by_type || []).map((item) => item.count), 1);
  const csvQuery = buildMetricsQuery(filters);

  return (
    <PageLayout title="Reports" subtitle="Analyze threat trends and export exact filtered alert data">
      <section className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-white/5 dark:bg-slate-900/40">
        <Filter label="Range"><select value={preset} onChange={(event) => setPreset(event.target.value)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-slate-900"><option value="24h">Last 24 hours</option><option value="7d">Last 7 days</option><option value="30d">Last 30 days</option><option value="custom">Custom</option></select></Filter>
        {preset === "custom" && <><Filter label="Start"><input type="datetime-local" value={customStart} max={customEnd} onChange={(event) => setCustomStart(event.target.value)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-slate-900" /></Filter><Filter label="End"><input type="datetime-local" value={customEnd} min={customStart} onChange={(event) => setCustomEnd(event.target.value)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-slate-900" /></Filter></>}
        <Filter label="Severity"><select value={severity} onChange={(event) => setSeverity(event.target.value)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-slate-900"><option value="">All</option>{SEVERITY_ORDER.map((value) => <option key={value}>{value}</option>)}</select></Filter>
        <Filter label="Threat type"><select value={alertType} onChange={(event) => setAlertType(event.target.value)} className="max-w-48 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-slate-900"><option value="">All</option>{THREAT_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}</select></Filter>
        <Filter label="Status"><select value={resolved} onChange={(event) => setResolved(event.target.value)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-slate-900"><option value="">All</option><option value="false">Unresolved</option><option value="true">Resolved</option></select></Filter>
        {customRangeValid ? <a href={`${API_URL}/api/v1/reports/alerts.csv?${csvQuery}`} className="ml-auto flex items-center gap-2 rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-500"><Download className="h-4 w-4" />Export CSV</a> : <button type="button" disabled className="ml-auto flex cursor-not-allowed items-center gap-2 rounded-lg bg-slate-300 px-3 py-2 text-sm font-medium text-slate-500 dark:bg-slate-800"><Download className="h-4 w-4" />Export CSV</button>}
      </section>

      {!customRangeValid && <p className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-950/20 dark:text-amber-300">Choose a start time earlier than the end time.</p>}
      {error && <p className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-950/30 dark:text-red-300">{error}</p>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryCard label="Total alerts" value={loading ? "—" : summary.total} icon={FileBarChart} color="text-sky-500" />
        <SummaryCard label="Unresolved" value={loading ? "—" : summary.unresolved} icon={ShieldAlert} color="text-red-500" />
        <SummaryCard label="High + critical" value={loading ? "—" : summary.high_critical} icon={Target} color="text-orange-500" />
        <SummaryCard label="Average score" value={loading ? "—" : summary.average_score} icon={TrendingUp} color="text-violet-500" />
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-white/5 dark:bg-slate-900/40"><h2 className="mb-2 font-semibold">Threat activity by type</h2>{loading ? <p className="flex h-[320px] items-center justify-center text-sm text-slate-500">Loading analytics…</p> : <ThreatActivityChart activity={data?.timeline || []} height={320} />}</section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/5 dark:bg-slate-900/40"><h2 className="mb-4 font-semibold">Threat types</h2>{data?.by_type?.length ? <div className="space-y-4">{data.by_type.map((item) => { const meta = getThreatType(item.alert_type); return <div key={item.alert_type}><div className="mb-1 flex justify-between text-sm"><span>{meta.label}</span><strong>{item.count}</strong></div><div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800"><div className="h-full rounded-full" style={{ width: `${(item.count / maxTypeCount) * 100}%`, backgroundColor: meta.color }} /></div></div>; })}</div> : <p className="text-sm text-slate-500">No threat types in this period.</p>}</section>
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/5 dark:bg-slate-900/40"><h2 className="mb-4 font-semibold">Severity distribution</h2><div className="space-y-3">{(data?.by_severity || []).map((item) => <div key={item.severity} className="flex items-center gap-3"><span className="w-20 text-xs font-semibold text-slate-500">{item.severity}</span><div className="h-3 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800"><div className="h-full rounded-full" style={{ width: `${summary.total ? (item.count / summary.total) * 100 : 0}%`, backgroundColor: SEVERITY_COLORS[item.severity] }} /></div><span className="w-8 text-right text-sm font-semibold">{item.count}</span></div>)}</div></section>
      </div>
    </PageLayout>
  );
}
