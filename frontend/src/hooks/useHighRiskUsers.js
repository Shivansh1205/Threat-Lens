import { useEffect, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8002";
const POLL_INTERVAL_MS = 15000; // this ranking doesn't need to be instant-real-time

/**
 * Fetches GET /api/v1/users/high-risk on mount and every 15s thereafter.
 * Unlike the alert feed, high-risk ranking isn't pushed over WebSocket —
 * it changes gradually (rolling risk score, decayed per-alert) rather than
 * event-by-event, so periodic polling is a reasonable fit here.
 */
export function useHighRiskUsers(limit = 10) {
  const [users, setUsers] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;

    async function fetchHighRiskUsers() {
      try {
        const res = await fetch(`${API_URL}/api/v1/users/high-risk?limit=${limit}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (active) {
          setUsers(data);
          setError(null);
        }
      } catch (err) {
        if (active) setError(err.message);
      }
    }

    fetchHighRiskUsers();
    const id = setInterval(fetchHighRiskUsers, POLL_INTERVAL_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [limit]);

  return { users, error };
}
