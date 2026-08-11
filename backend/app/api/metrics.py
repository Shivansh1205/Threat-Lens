from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.alert import Alert
from app.models.log_event import LogEvent
from app.models.user import User

router = APIRouter(tags=["metrics"])


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _filtered_alert_query(
    db: Session,
    start: datetime,
    end: datetime,
    severity: str | None,
    alert_type: str | None,
    resolved: bool | None,
):
    query = db.query(Alert).filter(Alert.created_at >= start, Alert.created_at < end)
    if severity:
        query = query.filter(Alert.severity == severity)
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type)
    if resolved is not None:
        query = query.filter(Alert.resolved == resolved)
    return query


@router.get("/metrics/summary")
def summary(db: Session = Depends(get_db)) -> dict[str, int]:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return {
        "events_24h": db.query(func.count(LogEvent.id))
        .filter(LogEvent.timestamp >= since)
        .scalar()
        or 0,
        "alerts_24h": db.query(func.count(Alert.id))
        .filter(Alert.created_at >= since)
        .scalar()
        or 0,
        "active_threats": db.query(func.count(Alert.id))
        .filter(Alert.resolved.is_(False))
        .scalar()
        or 0,
        "high_critical_24h": db.query(func.count(Alert.id))
        .filter(Alert.created_at >= since, Alert.severity.in_(["HIGH", "CRITICAL"]))
        .scalar()
        or 0,
        "total_users": db.query(func.count(User.id)).scalar() or 0,
    }


@router.get("/metrics/activity")
def activity(
    hours: int = Query(default=24, ge=1, le=168),
    bucket_minutes: int = Query(default=5, ge=1, le=60),
    db: Session = Depends(get_db),
) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = db.query(Alert.created_at).filter(Alert.created_at >= since).all()
    bucket_seconds = bucket_minutes * 60
    counts: Counter[datetime] = Counter()
    for (created_at,) in rows:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        epoch = int(created_at.timestamp())
        start = datetime.fromtimestamp(epoch - epoch % bucket_seconds, tz=timezone.utc)
        counts[start] += 1
    return [{"time": key, "count": counts[key]} for key in sorted(counts)]


@router.get("/metrics/threats")
def threat_metrics(
    start: datetime | None = None,
    end: datetime | None = None,
    bucket_minutes: int = Query(default=30, ge=1, le=1440),
    severity: str | None = None,
    alert_type: str | None = None,
    resolved: bool | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Return exact filtered threat totals and a type-grouped timeline.

    ``end`` is exclusive. The response discovers alert types from the data,
    so newly added detectors automatically appear without an API change.
    """
    now = datetime.now(timezone.utc)
    end_utc = _as_utc(end or now)
    start_utc = _as_utc(start or (end_utc - timedelta(hours=24)))
    if start_utc >= end_utc:
        raise HTTPException(status_code=422, detail="start must be before end")

    rows = _filtered_alert_query(
        db, start_utc, end_utc, severity, alert_type, resolved
    ).all()
    type_counts: Counter[str] = Counter()
    severity_counts: Counter[str] = Counter()
    bucket_counts: dict[datetime, Counter[str]] = defaultdict(Counter)
    bucket_seconds = bucket_minutes * 60

    for alert in rows:
        type_counts[alert.alert_type] += 1
        severity_value = getattr(alert.severity, "value", alert.severity)
        severity_counts[str(severity_value)] += 1
        created_at = _as_utc(alert.created_at)
        epoch = int(created_at.timestamp())
        bucket = datetime.fromtimestamp(epoch - epoch % bucket_seconds, tz=timezone.utc)
        bucket_counts[bucket][alert.alert_type] += 1

    types = sorted(type_counts)
    start_epoch = int(start_utc.timestamp())
    first_bucket = datetime.fromtimestamp(
        start_epoch - start_epoch % bucket_seconds, tz=timezone.utc
    )
    timeline = []
    cursor = first_bucket
    while cursor < end_utc:
        counts = bucket_counts.get(cursor, Counter())
        timeline.append(
            {
                "time": cursor,
                "total": sum(counts.values()),
                "by_type": {name: counts.get(name, 0) for name in types},
            }
        )
        cursor += timedelta(seconds=bucket_seconds)

    scores = [alert.score for alert in rows]
    return {
        "summary": {
            "total": len(rows),
            "unresolved": sum(not alert.resolved for alert in rows),
            "high_critical": sum(
                getattr(alert.severity, "value", alert.severity) in {"HIGH", "CRITICAL"}
                for alert in rows
            ),
            "average_score": round(sum(scores) / len(scores), 1) if scores else 0,
        },
        "by_type": [
            {"alert_type": name, "count": count}
            for name, count in sorted(
                type_counts.items(), key=lambda item: (-item[1], item[0])
            )
        ],
        "by_severity": [
            {"severity": name, "count": severity_counts.get(name, 0)}
            for name in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        ],
        "timeline": timeline,
    }
