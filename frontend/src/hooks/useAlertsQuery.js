import { useCallback, useEffect, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8002";

/**
 * One-shot(ish) alert query against GET /api/v1/alerts, re-fetched whenever
 * `params` changes (by value, via JSON.stringify — params are always plain
 * strings/numbers/booleans here, never functions/dates, so this is a safe,
 * simple dependency key). Distinct from `useAlertStream` (Dashboard's
 * live/WebSocket feed, capped at 200, always most-recent-first): this hook
 * is for the Alerts and User Analytics pages, which need arbitrary
 * filters/sort/a smaller page-sized cap and no live push — a plain re-fetch
 * on filter change is the right fit, not a persistent socket.
 *
 * Also exposes `resolveAlert`/`unresolveAlert`, which PATCH the resolve
 * endpoints and merge the (authoritative) response back into local state —
 * see AlertsTable's docstring for why that's preferred over a full refetch
 * or a pre-response optimistic update.
 *
 * Pass `null` for `params` to skip fetching entirely (e.g. User Analytics
 * before a user_id has been selected) — returns an empty, non-loading,
 * non-error state rather than firing a request with meaningless params.
 */
export function useAlertsQuery(params) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(params !== null);
  const [error, setError] = useState(null);

  const paramsKey = params === null ? null : JSON.stringify(params);

  useEffect(() => {
    if (paramsKey === null) {
      setAlerts([]);
      setLoading(false);
      setError(null);
      return;
    }

    let active = true;
    setLoading(true);

    async function fetchAlerts() {
      try {
        const entries = Object.entries(JSON.parse(paramsKey)).filter(
          ([, v]) => v !== undefined && v !== null && v !== ""
        );
        const qs = new URLSearchParams(entries);
        const res = await fetch(`${API_URL}/api/v1/alerts?${qs.toString()}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (active) {
          setAlerts(data);
          setError(null);
        }
      } catch (err) {
        if (active) setError(err.message);
      } finally {
        if (active) setLoading(false);
      }
    }

    fetchAlerts();
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- paramsKey IS the dep
  }, [paramsKey]);

  const resolveAlert = useCallback(async (id) => {
    const res = await fetch(`${API_URL}/api/v1/alerts/${id}/resolve`, { method: "PATCH" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const updated = await res.json();
    setAlerts((prev) => prev.map((a) => (a.id === id ? updated : a)));
  }, []);

  const unresolveAlert = useCallback(async (id) => {
    const res = await fetch(`${API_URL}/api/v1/alerts/${id}/unresolve`, { method: "PATCH" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const updated = await res.json();
    setAlerts((prev) => prev.map((a) => (a.id === id ? updated : a)));
  }, []);

  return { alerts, loading, error, resolveAlert, unresolveAlert };
}
