"""Alerts query endpoint: `GET /alerts`."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.alert import Alert
from app.schemas.alert import AlertOut
from app.schemas.common import Severity

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    limit: int = Query(50, ge=1, le=500),
    user_id: str | None = None,
    severity: Severity | None = None,
    db: Session = Depends(get_db),
) -> list[Alert]:
    """Return alerts, most recent first, with optional user/severity filters."""
    query = db.query(Alert)
    if user_id is not None:
        query = query.filter(Alert.user_id == user_id)
    if severity is not None:
        query = query.filter(Alert.severity == severity)

    return query.order_by(Alert.created_at.desc()).limit(limit).all()
