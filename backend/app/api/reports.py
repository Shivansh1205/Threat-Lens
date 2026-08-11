"""Downloadable analyst reports."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.alert import Alert

router = APIRouter(tags=["reports"])


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _safe_cell(value: object) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


@router.get("/reports/alerts.csv")
def alerts_csv(
    start: datetime | None = None,
    end: datetime | None = None,
    severity: str | None = None,
    alert_type: str | None = None,
    resolved: bool | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    now = datetime.now(timezone.utc)
    end_utc = _as_utc(end or now)
    start_utc = _as_utc(start or (end_utc - timedelta(hours=24)))
    if start_utc >= end_utc:
        raise HTTPException(status_code=422, detail="start must be before end")

    query = db.query(Alert).filter(Alert.created_at >= start_utc, Alert.created_at < end_utc)
    if severity:
        query = query.filter(Alert.severity == severity)
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type)
    if resolved is not None:
        query = query.filter(Alert.resolved == resolved)

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "created_at",
            "severity",
            "alert_type",
            "score",
            "raw_score",
            "user_id",
            "resolved",
            "message",
            "evidence",
        ]
    )
    for alert in query.order_by(Alert.created_at.desc()).all():
        severity_value = getattr(alert.severity, "value", alert.severity)
        writer.writerow(
            [
                alert.created_at.isoformat(),
                severity_value,
                _safe_cell(alert.alert_type),
                alert.score,
                alert.raw_score,
                _safe_cell(alert.user_id),
                alert.resolved,
                _safe_cell(alert.message),
                _safe_cell(json.dumps(alert.evidence or {}, sort_keys=True)),
            ]
        )

    filename = f"threatlens-alerts-{now:%Y%m%d-%H%M%S}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
