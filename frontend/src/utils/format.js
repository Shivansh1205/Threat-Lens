/**
 * Small formatting helpers for behavioral-profile fields, which store raw
 * numeric forms (decimal hour-of-day, seconds) that aren't fit to show
 * directly. Relative-timestamp formatting already lives in `utils/time.js`
 * (`formatRelativeTime`) — not duplicated here.
 */

/** 14.5 -> "2:30 PM". Decimal hour-of-day (0-24, fractional = minutes) as
 * stored in BehaviorProfile.typical_login_hour. */
export function formatHourOfDay(decimalHour) {
  if (decimalHour == null || Number.isNaN(decimalHour)) return "—";

  const totalMinutes = Math.round(decimalHour * 60) % (24 * 60);
  const normalized = totalMinutes < 0 ? totalMinutes + 24 * 60 : totalMinutes;
  const hour24 = Math.floor(normalized / 60);
  const minute = normalized % 60;

  const period = hour24 >= 12 ? "PM" : "AM";
  const hour12 = hour24 % 12 === 0 ? 12 : hour24 % 12;

  return `${hour12}:${String(minute).padStart(2, "0")} ${period}`;
}

/** 5400 -> "1h 30m". Seconds (BehaviorProfile.avg_session_duration_seconds)
 * as a human-readable duration. */
export function formatDuration(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;

  const totalMinutes = Math.round(seconds / 60);
  if (totalMinutes < 60) return `${totalMinutes}m`;

  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes === 0 ? `${hours}h` : `${hours}h ${minutes}m`;
}

/** 2.3 -> "2.3 days" / 0.5 -> "12h". Days (BehaviorProfile.
 * typical_days_between_logins) as a human-readable span. */
export function formatDaySpan(days) {
  if (days == null || Number.isNaN(days)) return "—";
  if (days < 1) return formatDuration(days * 86400);
  return `${days.toFixed(1)} day${days === 1 ? "" : "s"}`;
}
