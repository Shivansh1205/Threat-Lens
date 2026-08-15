import { useEffect, useState } from "react";
import { buildMetricsQuery } from "../utils/reporting";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8002";

export function useThreatMetrics(filters, enabled = true) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const query = buildMetricsQuery(filters);

  useEffect(() => {
    if (!enabled) {
      setData(null);
      setLoading(false);
      setError(null);
      return undefined;
    }
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    fetch(`${API_URL}/api/v1/metrics/threats?${query}`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`Analytics request failed (HTTP ${response.status})`);
        return response.json();
      })
      .then((value) => {
        if (active) {
          setData(value);
          setError(null);
        }
      })
      .catch((err) => {
        if (active && err.name !== "AbortError") setError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [query, enabled]);

  return { data, loading, error, query };
}
