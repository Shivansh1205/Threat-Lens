"""Log ingestion endpoint: `POST /log`.

The synchronous ingest path — validate, upsert the user, persist the event,
run the detector registry, return what fired. A message queue between ingest
and detection is deliberately skipped (see PHASES.md open question for Phase
2): direct call is fine at our volumes.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database import get_db
from app.detection.registry import get_registry
from app.models.log_event import LogEvent
from app.models.user import User
from app.schemas.log_event import LogEventIn

router = APIRouter(tags=["ingestion"])


class LogIngestResult(BaseModel):
    """Response for a successful ingest: the stored event id and any alerts."""

    event_id: UUID
    alert_ids: list[UUID]


@router.post("/log", status_code=status.HTTP_201_CREATED, response_model=LogIngestResult)
def ingest_log(payload: LogEventIn, db: Session = Depends(get_db)) -> LogIngestResult:
    now = datetime.now(timezone.utc)

    # 1. Upsert the user — ON CONFLICT handles concurrent inserts safely.
    stmt = (
        pg_insert(User)
        .values(user_id=payload.user_id, first_seen_at=now, last_seen_at=now)
        .on_conflict_do_update(
            index_elements=["user_id"],
            set_={"last_seen_at": now},
        )
    )
    db.execute(stmt)
    db.flush()

    # 2. Persist the event, keeping the raw payload verbatim for audit.
    event = LogEvent(
        user_id=payload.user_id,
        ip=payload.ip,
        timestamp=payload.timestamp,
        event_type=payload.event_type,
        status=payload.status,
        port=payload.port,
        endpoint=payload.endpoint,
        user_agent=payload.user_agent,
        country=payload.country,
        raw_json=payload.model_dump(mode="json"),
    )
    db.add(event)
    db.flush()

    # 3. Run the real detectors. Registry owns commit for the alerts it creates.
    alerts = get_registry().run_all(event, db)

    # Ensure the event + user upsert are committed even when no alerts fired.
    db.commit()

    return LogIngestResult(event_id=event.id, alert_ids=[a.id for a in alerts])
