import AlertFeed from "../components/AlertFeed/AlertFeed";
import ChatWidget from "../components/ChatWidget/ChatWidget";
import HighRiskUsers from "../components/HighRiskUsers/HighRiskUsers";
import Sidebar from "../components/Sidebar/Sidebar";
import SeverityBreakdown from "../components/SeverityBreakdown/SeverityBreakdown";
import SummaryCards from "../components/SummaryCards/SummaryCards";
import ThreatActivityChart from "../components/ThreatActivityChart/ThreatActivityChart";
import TopBar from "../components/TopBar/TopBar";
import SourceHealth from "../components/SourceHealth/SourceHealth";
import { useAlertStream } from "../hooks/useAlertStream";
import { useSystemOverview } from "../hooks/useSystemOverview";

function Panel({ title, children, className = "" }) {
  return (
    <section
      className={`rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-white/5 dark:bg-slate-900/40 dark:shadow-lg dark:shadow-black/10 ${className}`}
    >
      <h2 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-300">{title}</h2>
      {children}
    </section>
  );
}

/**
 * Live dashboard (Phase 7b). Layout follows the report mockups (Figure
 * 4.11/4.12 style): sidebar nav, top bar with search placeholder +
 * connection status, summary cards, a chart row, alert feed + chatbot side
 * by side, and a high-risk users section.
 *
 * `useAlertStream` is the single source of truth for the alert feed — its
 * `alerts` array is threaded down to every component that needs alert data
 * (SummaryCards, both charts, AlertFeed) so there's exactly one WebSocket
 * connection and one in-memory buffer for the whole page, not one per
 * component. HighRiskUsers and ChatWidget own their own data hooks
 * internally (useHighRiskUsers / useChat) since nothing else on the page
 * needs that data.
 */
export default function Dashboard() {
  const { alerts, error, connectionStatus } = useAlertStream();
  const overview = useSystemOverview();
  const collectorStatus = overview.sources.some((source) => source.status === "live") ? "live" : "stale";

  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <Sidebar />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar connectionStatus={connectionStatus} collectorStatus={collectorStatus} />

        <main className="flex-1 space-y-6 overflow-y-auto p-6">
          {error && (
            <p className="rounded-lg border border-red-500/30 bg-red-950/30 px-4 py-2 text-sm text-red-300">
              Could not load alerts: {error}
            </p>
          )}

          {(overview.error) && <p className="rounded-lg border border-amber-500/30 bg-amber-950/20 px-4 py-2 text-sm text-amber-300">{overview.error}</p>}
          <SummaryCards alerts={alerts} summary={overview.summary} />

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Panel title="Threat Activity">
              <ThreatActivityChart alerts={alerts} activity={overview.activity} />
            </Panel>
            <Panel title="Severity Breakdown">
              <SeverityBreakdown alerts={alerts} />
            </Panel>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Panel title="Live Alert Feed" className="lg:col-span-2">
              <AlertFeed alerts={alerts} />
            </Panel>
            <ChatWidget />
          </div>

          <Panel title="High-Risk Users">
            <HighRiskUsers />
          </Panel>
          <Panel title="Website Collectors">
            <SourceHealth sources={overview.sources} />
          </Panel>
        </main>
      </div>
    </div>
  );
}
