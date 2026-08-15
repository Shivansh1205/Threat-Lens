export const THREAT_TYPES = [
  { value: "brute_force", label: "Brute Force", color: "#f97316" },
  { value: "brute_force_success", label: "Compromised Login", color: "#ef4444" },
  { value: "port_scan", label: "Port Scan", color: "#8b5cf6" },
  { value: "unusual_ip", label: "Unusual IP", color: "#06b6d4" },
  { value: "request_flood", label: "Request Flood", color: "#eab308" },
  { value: "path_probe", label: "Path Probe", color: "#ec4899" },
  { value: "server_error_spike", label: "Server Error Spike", color: "#6366f1" },
];

const BY_VALUE = new Map(THREAT_TYPES.map((type) => [type.value, type]));
const FALLBACK_COLORS = ["#14b8a6", "#a855f7", "#84cc16", "#f43f5e"];

export function humanizeThreatType(value) {
  return (value || "unknown")
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function getThreatType(value) {
  const known = BY_VALUE.get(value);
  if (known) return known;
  const hash = Array.from(value || "unknown").reduce((sum, char) => sum + char.charCodeAt(0), 0);
  return {
    value: value || "unknown",
    label: humanizeThreatType(value),
    color: FALLBACK_COLORS[hash % FALLBACK_COLORS.length],
  };
}
