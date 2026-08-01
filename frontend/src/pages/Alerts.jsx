import { useMemo, useState } from "react";
import AlertsTable from "../components/AlertsTable/AlertsTable";
import PageLayout from "../components/PageLayout/PageLayout";
import { SEVERITY_ORDER } from "../constants/severity";
import { useAlertsQuery } from "../hooks/useAlertsQuery";

// Matches this project's four detectors (detection/rules/*.py) — see
// ARCHITECTURE.md's Detection & profiling section. A fixed list rather than
// deriving options purely from loaded data, so the dropdown still offers
// every real type even when the current filtered/paginated result set
// happens not to contain one of them.
const ALERT_TYPES = ["brute_force", "brute_force_success", "port_scan", "unusual_ip"];

const RESOLVED_OPTIONS = [
  { label: "All", value: "" },
  { label: "Unresolved", value: "false" },
  { label: "Resolved", value: "true" },
];

// Capped at 100 rather than true pagination (offset/page params) — this
// project's synthetic-data-scale demo doesn't need more, and the prompt's
// own scope allows "paginate OR at least cap." Documented here rather than
// silently limited: if the alert volume ever legitimately exceeds 100
// under a given filter, the oldest-matching rows beyond the cap won't be
// visible — a real backlog view would need offset-based pagination added
// to GET /api/v1/alerts, which this round of work didn't build.
const FETCH_LIMIT = 100;

function FilterSelect({ label, value, onChange, options }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-slate-400">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-white/10 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/**
 * Full alert history — filterable, sortable, resolvable. Distinct from the
 * Dashboard's compact `AlertFeed` (live, WebSocket-pushed, unfiltered,
 * capped at 200 most-recent): this page is a deliberate one-shot query
 * against GET /api/v1/alerts with server-side filters/sort, re-fetched
 * whenever a filter or sort control changes (see useAlertsQuery).
 */
export default function Alerts() {
  const [severity, setSeverity] = useState("");
  const [resolved, setResolved] = useState("");
  const [alertType, setAlertType] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortOrder, setSortOrder] = useState("desc");

  const params = useMemo(
    () => ({
      limit: FETCH_LIMIT,
      severity: severity || undefined,
      resolved: resolved === "" ? undefined : resolved,
      alert_type: alertType || undefined,
      sort_by: sortBy,
      sort_order: sortOrder,
    }),
    [severity, resolved, alertType, sortBy, sortOrder]
  );

  const { alerts, loading, error, resolveAlert, unresolveAlert } = useAlertsQuery(params);

  function handleSortChange(column) {
    if (column === sortBy) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      setSortOrder("desc");
    }
  }

  return (
    <PageLayout
      title="Alerts"
      subtitle={`${alerts.length} alert${alerts.length === 1 ? "" : "s"} shown (up to ${FETCH_LIMIT})`}
    >
      <div className="flex flex-wrap items-end gap-4 rounded-xl border border-white/5 bg-slate-900/40 p-4">
        <FilterSelect
          label="Severity"
          value={severity}
          onChange={setSeverity}
          options={[{ label: "All", value: "" }, ...SEVERITY_ORDER.map((s) => ({ label: s, value: s }))]}
        />
        <FilterSelect label="Status" value={resolved} onChange={setResolved} options={RESOLVED_OPTIONS} />
        <FilterSelect
          label="Type"
          value={alertType}
          onChange={setAlertType}
          options={[{ label: "All", value: "" }, ...ALERT_TYPES.map((t) => ({ label: t, value: t }))]}
        />
      </div>

      {error && (
        <p className="rounded-lg border border-red-500/30 bg-red-950/30 px-4 py-2 text-sm text-red-300">
          Could not load alerts: {error}
        </p>
      )}

      <div className="rounded-xl border border-white/5 bg-slate-900/40 p-4">
        {loading ? (
          <p className="py-6 text-center text-sm text-slate-500">Loading...</p>
        ) : (
          <AlertsTable
            alerts={alerts}
            onResolve={resolveAlert}
            onUnresolve={unresolveAlert}
            sortBy={sortBy}
            sortOrder={sortOrder}
            onSortChange={handleSortChange}
            emptyMessage="No alerts match the current filters."
          />
        )}
      </div>
    </PageLayout>
  );
}
