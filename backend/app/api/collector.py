"""Authenticated batch ingestion and collector heartbeat endpoints."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.api.logs import persist_event, publish_alerts
from app.config import get_settings
from app.database import get_db
from app.models.log_event import LogEvent
from app.models.monitoring_source import MonitoringSource
from app.schemas.log_event import LogEventIn
from app.schemas.source import SourceHeartbeat
from app.security import require_ingest_key

router = APIRouter(tags=["collectors"], dependencies=[Depends(require_ingest_key)])


class EventBatch(BaseModel):
    source_id: str = Field(min_length=1, max_length=100)
    source_name: str = Field(default="Nginx website", min_length=1, max_length=200)
    events: list[LogEventIn]

    @model_validator(mode="after")
    def _validate_events(self) -> "EventBatch":
        limit = get_settings().MAX_BATCH_SIZE
        if not self.events or len(self.events) > limit:
            raise ValueError(f"events must contain between 1 and {limit} items")
        if any(not event.external_event_id for event in self.events):
            raise ValueError("every collector event requires external_event_id")
        return self


class BatchResult(BaseModel):
    accepted: int
    duplicates: int
    event_ids: list[UUID]
    alert_ids: list[UUID]


def _source(db: Session, source_id: str, name: str) -> MonitoringSource:
    source = db.get(MonitoringSource, source_id)
    if source is None:
        source = MonitoringSource(source_id=source_id, name=name, source_type="nginx")
        db.add(source)
        db.flush()
    else:
        source.name = name
    return source


@router.post("/events/batch", response_model=BatchResult)
def ingest_batch(
    payload: EventBatch,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> BatchResult:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    oldest = now - timedelta(hours=settings.MAX_EVENT_AGE_HOURS)
    newest = now + timedelta(seconds=settings.MAX_EVENT_FUTURE_SKEW_SECONDS)
    source = _source(db, payload.source_id, payload.source_name)
    accepted: list[LogEvent] = []
    alerts: list = []
    duplicates = 0

    for incoming in payload.events:
        if incoming.timestamp < oldest or incoming.timestamp > newest:
            raise HTTPException(
                status_code=422, detail="event timestamp outside accepted range"
            )
        duplicate = (
            db.query(LogEvent.id)
            .filter(
                LogEvent.source_id == payload.source_id,
                LogEvent.external_event_id == incoming.external_event_id,
            )
            .first()
        )
        if duplicate:
            duplicates += 1
            continue
        normalized = incoming.model_copy(update={"source_id": payload.source_id})
        event, event_alerts = persist_event(normalized, db)
        accepted.append(event)
        alerts.extend(event_alerts)

    source.events_received += len(accepted)
    source.last_heartbeat_at = now
    if accepted:
        source.last_event_at = max(event.timestamp for event in accepted)
    db.add(source)
    db.commit()
    publish_alerts(alerts, background_tasks)
    return BatchResult(
        accepted=len(accepted),
        duplicates=duplicates,
        event_ids=[event.id for event in accepted],
        alert_ids=[alert.id for alert in alerts],
    )


@router.post("/sources/{source_id}/heartbeat")
def heartbeat(
    source_id: str,
    payload: SourceHeartbeat,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    source = _source(db, source_id, payload.name)
    source.source_type = payload.source_type
    source.last_heartbeat_at = datetime.now(timezone.utc)
    source.malformed_lines = payload.malformed_lines
    source.delivery_failures = payload.delivery_failures
    db.commit()
    return {"status": "ok"}
