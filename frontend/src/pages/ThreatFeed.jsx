import { Pause, Play, Radio } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import AlertFeed from "../components/AlertFeed/AlertFeed";
import ConnectionStatus from "../components/ConnectionStatus/ConnectionStatus";
import PageLayout from "../components/PageLayout/PageLayout";
import { SEVERITY_ORDER } from "../constants/severity";
import { THREAT_TYPES } from "../constants/threatTypes";
import { useAlertStream } from "../hooks/useAlertStream";

export default function ThreatFeed() {
  const { alerts, error, connectionStatus } = useAlertStream();
  const [paused, setPaused] = useState(false);
  const [snapshot, setSnapshot] = useState([]);
  const [severity, setSeverity] = useState("");
  const [alertType, setAlertType] = useState("");

  useEffect(() => {
    if (!paused) setSnapshot(alerts);
  }, [alerts, paused]);

  const visibleSource = paused ? snapshot : alerts;
  const visibleAlerts = useMemo(
    () => visibleSource.filter((alert) => (!severity || alert.severity === severity) && (!alertType || alert.alert_type === alertType)),
    [visibleSource, severity, alertType]
  );
  const queuedCount = paused
    ? alerts.filter((alert) => !snapshot.some((snapshotAlert) => snapshotAlert.id === alert.id)).length
    : 0;

  function togglePaused() {
    if (!paused) setSnapshot(alerts);
    setPaused((value) => !value);
  }

  return (
    <PageLayout title="Threat Feed" subtitle="Live, read-only stream of detected security threats">
      <div className="flex flex-wrap items-end justify-between gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-white/5 dark:bg-slate-900/40">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs font-medium text-slate-500">
            <span className="mb-1 block">Severity</span>
            <select value={severity} onChange={(event) => setSeverity(event.target.value)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-slate-900">
              <option value="">All severities</option>
              {SEVERITY_ORDER.map((value) => <option key={value}>{value}</option>)}
            </select>
          </label>
          <label className="text-xs font-medium text-slate-500">
            <span className="mb-1 block">Threat type</span>
            <select value={alertType} onChange={(event) => setAlertType(event.target.value)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-slate-900">
              <option value="">All types</option>
              {THREAT_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
            </select>
          </label>
        </div>
        <div className="flex items-center gap-3">
          <ConnectionStatus status={connectionStatus} />
          <button type="button" onClick={togglePaused} className="flex items-center gap-2 rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-500">
            {paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
            {paused ? `Resume${queuedCount ? ` (${queuedCount} new)` : ""}` : "Pause"}
          </button>
        </div>
      </div>

      {error && <p className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-950/30 dark:text-red-300">Could not load threats: {error}</p>}

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-white/5 dark:bg-slate-900/40">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-semibold"><Radio className={`h-4 w-4 text-emerald-500 ${paused ? "" : "animate-pulse"}`} />Live detections</h2>
          <span className="text-xs text-slate-500">{visibleAlerts.length} shown · newest first</span>
        </div>
        <AlertFeed alerts={visibleAlerts} />
      </section>
    </PageLayout>
  );
}
