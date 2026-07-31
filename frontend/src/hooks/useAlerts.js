import { useEffect, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const POLL_INTERVAL_MS = 5000;

/**
 * Fetch alerts from the backend on mount and poll every 5 seconds.
 *
 * Phase 2 proof-of-flow only — polling is a placeholder. Phase 6 replaces this
 * with the WebSocket alert stream (see PHASES.md).
 */
export function useAlerts() {
  const [alerts, setAlerts] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;

    async function fetchAlerts() {
      try {
        const res = await fetch(`${API_URL}/api/v1/alerts`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (active) {
          setAlerts(data);
          setError(null);
        }
      } catch (err) {
        if (active) setError(err.message);
      }
    }

    fetchAlerts();
    const id = setInterval(fetchAlerts, POLL_INTERVAL_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  return { alerts, error };
}
