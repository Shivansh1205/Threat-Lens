import { useEffect, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8002";
const POLL_MS = 10000;

export function useSystemOverview() {
  const [summary, setSummary] = useState(null);
  const [activity, setActivity] = useState([]);
  const [sources, setSources] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    async function refresh() {
      try {
        const [summaryResponse, activityResponse, sourcesResponse] = await Promise.all([
          fetch(`${API_URL}/api/v1/metrics/summary`),
          fetch(`${API_URL}/api/v1/metrics/threats?bucket_minutes=30`),
          fetch(`${API_URL}/api/v1/sources`),
        ]);
        if (![summaryResponse, activityResponse, sourcesResponse].every((response) => response.ok)) {
          throw new Error("Monitoring overview is unavailable");
        }
        const values = await Promise.all([
          summaryResponse.json(), activityResponse.json(), sourcesResponse.json(),
        ]);
        if (active) {
          setSummary(values[0]); setActivity(values[1].timeline); setSources(values[2]); setError(null);
        }
      } catch (err) { if (active) setError(err.message); }
    }
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => { active = false; clearInterval(id); };
  }, []);

  return { summary, activity, sources, error };
}
