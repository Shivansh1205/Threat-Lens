"""Alerts query + resolution endpoints: `GET /alerts`, `PATCH /alerts/{id}/resolve`,
`PATCH /alerts/{id}/unresolve`.
"""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.alert import Alert
from app.schemas.alert import AlertOut
from app.schemas.common import Severity

router = APIRouter(tags=["alerts"])

# Allowlist for sort_by — never interpolate an arbitrary query param straight
# into a column lookup (that's a column-injection footgun even with an ORM,
# since getattr(Alert, user_input) would happily resolve to any mapped
# attribute, not just the two we intend to support).
_SORT_COLUMNS = {
    "created_at": Alert.created_at,
    "score": Alert.score,
}


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    limit: int = Query(50, ge=1, le=500),
    user_id: str | None = None,
    severity: Severity | None = None,
    resolved: bool | None = Query(
        None, description="Filter by resolution status. Omitted/null = both."
    ),
    alert_type: str | None = None,
    sort_by: Literal["created_at", "score"] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
) -> list[Alert]:
    """Return alerts with optional filters, sorted by ``sort_by``/``sort_order``.

    Defaults (``sort_by="created_at"``, ``sort_order="desc"``, ``resolved``/
    ``alert_type`` both unset) reproduce exactly the pre-existing behavior —
    most-recent-first, no resolution/type filtering — so callers that don't
    pass the new params (e.g. the dashboard's ``useAlertStream`` initial
    fetch, which only ever passes ``limit``) are unaffected.
    """
    query = db.query(Alert)
    if user_id is not None:
        query = query.filter(Alert.user_id == user_id)
    if severity is not None:
        query = query.filter(Alert.severity == severity)
    if resolved is not None:
        query = query.filter(Alert.resolved == resolved)
    if alert_type is not None:
        query = query.filter(Alert.alert_type == alert_type)

    column = _SORT_COLUMNS[sort_by]
    order_fn = asc if sort_order == "asc" else desc
    query = query.order_by(order_fn(column))

    return query.limit(limit).all()


def _get_alert_or_404(alert_id: UUID, db: Session) -> Alert:
    alert = db.query(Alert).filter(Alert.id == alert_id).one_or_none()
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert


@router.patch("/alerts/{alert_id}/resolve", response_model=AlertOut)
def resolve_alert(alert_id: UUID, db: Session = Depends(get_db)) -> Alert:
    """Mark an alert resolved. Idempotent: resolving an already-resolved
    alert is a no-op that still returns 200 — ``resolved_at`` is NOT reset
    to a new timestamp, preserving the original resolution time.
    """
    alert = _get_alert_or_404(alert_id, db)

    if not alert.resolved:
        alert.resolved = True
        alert.resolved_at = datetime.now(timezone.utc)
        db.add(alert)
        db.commit()
        db.refresh(alert)

    return alert


@router.patch("/alerts/{alert_id}/unresolve", response_model=AlertOut)
def unresolve_alert(alert_id: UUID, db: Session = Depends(get_db)) -> Alert:
    """Mark an alert unresolved — for correcting an accidental resolve.
    Also idempotent: unresolving an already-unresolved alert is a no-op.
    """
    alert = _get_alert_or_404(alert_id, db)

    if alert.resolved:
        alert.resolved = False
        alert.resolved_at = None
        db.add(alert)
        db.commit()
        db.refresh(alert)

    return alert
