// Single source of truth for talking to ThreatLens /api/v1/log.
// Payload shape must match backend/app/schemas/log_event.py::LogEventIn exactly.
// Required: user_id, ip, timestamp, event_type, status
// Optional: port, endpoint, user_agent, country
// extra="forbid" on the backend — do NOT add fields here without checking schema first.

const THREATLENS_URL =
  import.meta.env.VITE_THREATLENS_URL || "http://localhost:8002";

const VALID_EVENT_TYPES = [
  "LOGIN_SUCCESS",
  "LOGIN_FAILURE",
  "API_CALL",
  "PORT_ACCESS",
  "LOGOUT",
];

/**
 * Send one log event to ThreatLens.
 * @param {Object} event
 * @param {string} event.userId
 * @param {string} event.eventType - one of VALID_EVENT_TYPES
 * @param {string} event.status
 * @param {string} [event.endpoint]
 * @param {string} [event.userAgent]
 * @param {number} [event.port]
 * @param {string} [event.country]
 */
export async function sendLogEvent({
  userId,
  eventType,
  status,
  endpoint,
  userAgent,
  port,
  country,
  ip,
  timestamp,
}) {
  if (!VALID_EVENT_TYPES.includes(eventType)) {
    console.error(`[logClient] invalid event_type: ${eventType}`);
    return;
  }

  const resolvedIp = ip || (await getClientIp(userId));

  const body = {
    user_id: userId,
    ip: resolvedIp,
    timestamp: timestamp || new Date().toISOString(),
    event_type: eventType,
    status: status != null ? String(status) : "ok",
  };

  if (port !== undefined && port !== null) body.port = Number(port);
  if (endpoint !== undefined && endpoint !== null) body.endpoint = String(endpoint);
  if (userAgent !== undefined && userAgent !== null) body.user_agent = String(userAgent);
  if (country !== undefined && country !== null) body.country = String(country);

  try {
    const res = await fetch(`${THREATLENS_URL}/api/v1/log`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      console.error(`[logClient] ${res.status}`, await res.text());
    }
    return res.ok;
  } catch (err) {
    console.error("[logClient] request failed", err);
    return false;
  }
}

// Demo-only IP resolution: map per user so multi-user activity has distinct source IPs.
const userIpMap = new Map();
let fallbackIp = null;

async function getClientIp(userId) {
  if (userId) {
    if (!userIpMap.has(userId)) {
      // Deterministic/consistent IP per username in 192.168.1.x subnet
      let hash = 0;
      for (let i = 0; i < userId.length; i++) {
        hash = (hash << 5) - hash + userId.charCodeAt(i);
        hash |= 0;
      }
      const lastOctet = (Math.abs(hash) % 200) + 10;
      userIpMap.set(userId, `192.168.1.${lastOctet}`);
    }
    return userIpMap.get(userId);
  }

  if (fallbackIp) return fallbackIp;
  fallbackIp = `10.0.${Math.floor(Math.random() * 200) + 1}.${
    Math.floor(Math.random() * 200) + 1
  }`;
  return fallbackIp;
}

