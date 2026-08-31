"""Deterministic, privacy-safe context for external model requests."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime

from app.models.alert import Alert
from app.models.behavior_profile import BehaviorProfile
from app.models.log_event import LogEvent


def _relative_bucket(value: datetime | None) -> str:
    if value is None:
        return "unknown time"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    age = max(0, (datetime.now(UTC) - value).total_seconds())
    if age < 3600:
        return "within the last hour"
    if age < 86400:
        return "within the last day"
    return "older than one day"


def _risk_band(score: float | int | None) -> str:
    if score is None:
        return "unknown"
    if score >= 76:
        return "critical"
    if score >= 51:
        return "high"
    if score >= 26:
        return "medium"
    return "low"


def _opaque_label(index: int, kind: str) -> str:
    return f"{kind}_{chr(65 + (index % 26))}"


def alert_prompt_context(
    alert: Alert,
    event: LogEvent | None,
    profile: BehaviorProfile | None,
    *,
    max_chars: int = 4000,
) -> str:
    """Return only allowlisted facts for one alert explanation."""

    event_type = event.event_type.value if event is not None else "unknown"
    event_age = _relative_bucket(event.timestamp if event else alert.created_at)
    deviation = profile.deviation_score if profile is not None else None
    if deviation is None:
        deviation_band = "unknown"
    elif deviation >= 0.7:
        deviation_band = "highly unusual"
    elif deviation >= 0.3:
        deviation_band = "unusual"
    else:
        deviation_band = "near baseline"

    lines = [
        "Privacy-safe alert facts:",
        f"- opaque subject: {_opaque_label(0, 'USER')}",
        f"- alert category: {alert.alert_type}",
        f"- final severity: {alert.severity.value} ({_risk_band(alert.score)})",
        f"- final score: {alert.score}/100",
        "- detector score before behavior adjustment: "
        f"{alert.raw_score}/100 ({alert.raw_severity.value})",
        f"- triggering event category: {event_type}",
        f"- event age bucket: {event_age}",
        f"- behavioral deviation: {deviation_band}",
    ]
    if profile is not None:
        lines.extend(
            [
                f"- known network identity count: {len(profile.known_ips or [])}",
                f"- observed login count: {profile.login_count}",
                f"- cumulative risk band: {_risk_band(profile.user_risk_score)}",
            ]
        )
    return "\n".join(lines)[:max_chars]


def alert_list_context(alerts: list[Alert], *, max_chars: int = 4000) -> str:
    """Aggregate alerts without emitting identifiers or raw messages."""

    if not alerts:
        return "Privacy-safe alert facts: no matching alerts were found."

    type_counts = Counter(a.alert_type for a in alerts)
    severity_counts = Counter(a.severity.value for a in alerts)
    scores = [a.score for a in alerts]
    latest = max((a.created_at for a in alerts if a.created_at), default=None)
    lines = [
        "Privacy-safe alert summary:",
        f"- matching alert count: {len(alerts)}",
        "- alert categories: "
        f"{', '.join(f'{key}={value}' for key, value in sorted(type_counts.items()))}",
        "- severity counts: "
        f"{', '.join(f'{key}={value}' for key, value in sorted(severity_counts.items()))}",
        f"- score range: {min(scores)}-{max(scores)} out of 100",
        f"- latest activity: {_relative_bucket(latest)}",
    ]
    return "\n".join(lines)[:max_chars]


def alert_user_routing_context(
    alerts: list[Alert], *, known_user_ids: list[str] | None = None, max_chars: int = 4000
) -> str:
    """Return a bounded user-to-alert routing table for analyst questions.

    User IDs are intentionally included here so the external assistant can
    resolve a question such as "what happened with alice?". The table contains
    only alert metadata; credentials and request secrets are not persisted in
    or emitted by this context.
    """
    if not alerts and not known_user_ids:
        return "User routing table: no users were present in the matching alerts."

    grouped: dict[str, list[Alert]] = {}
    for alert in alerts:
        grouped.setdefault(alert.user_id, []).append(alert)

    all_user_ids = sorted(set(known_user_ids or ()) | set(grouped))
    labels = {
        user_id: f"USER_{chr(65 + (index % 26))}" for index, user_id in enumerate(all_user_ids)
    }
    lines = ["User routing table (monitored user IDs mapped to their matching alerts):"]
    for user_id in all_user_ids:
        user_alerts = grouped.get(user_id, [])
        if not user_alerts:
            lines.append(f"- {labels[user_id]} = {user_id}; alert_count=0; no matching alerts")
            continue
        type_counts = Counter(a.alert_type for a in user_alerts)
        max_score = max(a.score for a in user_alerts)
        severity_counts = Counter(a.severity.value for a in user_alerts)
        lines.append(
            f"- {labels[user_id]} = {user_id}; "
            f"alert_count={len(user_alerts)}; max_score={max_score}/100; "
            f"categories={','.join(f'{k}:{v}' for k, v in sorted(type_counts.items()))}; "
            f"severity={','.join(f'{k}:{v}' for k, v in sorted(severity_counts.items()))}"
        )
    return "\n".join(lines)[:max_chars]


_SECRET_FIELD = re.compile(
    r"password|passwd|token|api[_-]?key|secret|authorization|cookie|session",
    re.IGNORECASE,
)


def redact_context_value(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SECRET_FIELD.search(str(key)) else redact_context_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_context_value(item) for item in value]
    return value


def user_analysis_context(
    user_id: str,
    profile: BehaviorProfile | None,
    alerts: list[Alert],
    events_by_id: dict,
    *,
    max_chars: int = 4000,
) -> str:
    """Build bounded, admin-requested context for one monitored user."""
    lines = [
        "Admin-requested user analysis context:",
        f"- monitored user: {user_id}",
    ]
    if profile is not None:
        lines.extend(
            [
                f"- rolling user risk score: {profile.user_risk_score}/100",
                f"- behavioral deviation score: {profile.deviation_score}",
                f"- observed login count: {profile.login_count}",
                f"- known network identity count: {len(profile.known_ips or [])}",
                f"- total sessions: {profile.total_sessions}",
                "- last event: "
                f"{profile.last_event_at.isoformat() if profile.last_event_at else 'unknown'}",
            ]
        )
    else:
        lines.append("- behavioral profile: unavailable")

    lines.append(f"- included alert count: {len(alerts)} (most recent 50)")
    for alert in alerts:
        event = events_by_id.get(alert.triggered_by_event_id)
        record = {
            "alert_id": str(alert.id),
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
            "alert_type": alert.alert_type,
            "severity": alert.severity.value,
            "score": alert.score,
            "raw_severity": alert.raw_severity.value,
            "raw_score": alert.raw_score,
            "message": alert.message,
            "evidence": redact_context_value(alert.evidence or {}),
            "resolved": alert.resolved,
        }
        if event is not None:
            record["triggering_event"] = {
                "timestamp": event.timestamp.isoformat(),
                "event_type": event.event_type.value,
                "status": event.status,
                "ip": event.ip,
                "port": event.port,
                "endpoint": event.endpoint,
                "user_agent": event.user_agent,
                "country": event.country,
                "source_id": event.source_id,
                "external_event_id": event.external_event_id,
                "http_method": event.http_method,
                "http_status": event.http_status,
                "response_time_ms": event.response_time_ms,
                "bytes_sent": event.bytes_sent,
                "host": event.host,
                "referrer": event.referrer,
                "event_metadata": redact_context_value(event.event_metadata or {}),
            }
        lines.append("- alert record: " + json.dumps(record, default=str, separators=(",", ":")))
    return "\n".join(lines)[:max_chars]


def sanitize_question(question: str, known_user_ids: list[str]) -> str:
    """Mask known user identifiers before a question reaches an external API."""

    sanitized = question[:1000]
    sanitized = re.sub(r"https?://\S+", "[URL]", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[IP]", sanitized)
    sanitized = re.sub(
        r"(?i)\b(password|token|api[_-]?key)\s*[:=]\s*\S+",
        r"\1=[REDACTED]",
        sanitized,
    )
    for index, user_id in enumerate(
        sorted((u for u in known_user_ids if u), key=len, reverse=True)
    ):
        sanitized = re.sub(
            re.escape(user_id),
            _opaque_label(index, "USER"),
            sanitized,
            flags=re.IGNORECASE,
        )
    return sanitized


def sanitize_admin_question(question: str) -> str:
    """Preserve queryable entities while removing credentials from admin text."""

    sanitized = question.strip()[:1000]
    return re.sub(
        r"(?i)\b(password|passwd|token|api[_-]?key|secret|authorization|cookie)\s*[:=]\s*\S+",
        r"\1=[REDACTED]",
        sanitized,
    )
