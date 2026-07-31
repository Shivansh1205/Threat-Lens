"""Legacy stub detector — Phase 2 skeleton placeholder.

Kept for reference and quick smoke tests. No longer registered in
``DetectorRegistry``; the real detectors under ``app.detection.rules`` replaced
it in Phase 3.
"""

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.log_event import LogEvent
from app.schemas.common import EventType, Severity


def run_stub_detection(event: LogEvent, db: Session) -> list[Alert]:
    """Any failed login raises a LOW alert. Do not use in production paths."""
    if event.event_type != EventType.LOGIN_FAILURE:
        return []

    alert = Alert(
        user_id=event.user_id,
        alert_type="failed_login",
        severity=Severity.LOW,
        score=15,
        message="Failed login detected",
        triggered_by_event_id=event.id,
    )
    db.add(alert)
    db.flush()
    return [alert]
