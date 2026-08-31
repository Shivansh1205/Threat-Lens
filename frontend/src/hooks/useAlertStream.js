import { useCallback, useEffect, useRef, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8002";
const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8002/ws/alerts";
const MAX_ALERTS = 200;
const INITIAL_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30000;

/** Live detection feed. Explanations are requested separately by admins. */
export function useAlertStream() {
  const [alerts, setAlerts] = useState([]);
  const [error, setError] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState("connecting");
  const wsRef = useRef(null);
  const backoffRef = useRef(INITIAL_BACKOFF_MS);
  const reconnectTimeoutRef = useRef(null);
  const closedByUsRef = useRef(false);
  const hasConnectedBeforeRef = useRef(false);

  useEffect(() => {
    let active = true;
    async function fetchInitial() {
      try {
        const res = await fetch(`${API_URL}/api/v1/alerts?limit=${MAX_ALERTS}`);
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
    fetchInitial();
    return () => { active = false; };
  }, []);

  const connect = useCallback(() => {
    closedByUsRef.current = false;
    setConnectionStatus(hasConnectedBeforeRef.current ? "reconnecting" : "connecting");
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;
    ws.onopen = () => {
      hasConnectedBeforeRef.current = true;
      backoffRef.current = INITIAL_BACKOFF_MS;
      setConnectionStatus("connected");
    };
    ws.onmessage = (event) => {
      try {
        const alert = JSON.parse(event.data);
        setAlerts((prev) => [alert, ...prev].slice(0, MAX_ALERTS));
      } catch {
        // Ignore malformed push messages.
      }
    };
    ws.onclose = () => {
      wsRef.current = null;
      if (closedByUsRef.current) return;
      setConnectionStatus("disconnected");
      const delay = backoffRef.current;
      backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
      reconnectTimeoutRef.current = setTimeout(connect, delay);
    };
    ws.onerror = () => ws.close();
  }, []);

  useEffect(() => {
    connect();
    return () => {
      closedByUsRef.current = true;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { alerts, error, connectionStatus };
}
