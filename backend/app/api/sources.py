from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.monitoring_source import MonitoringSource
from app.schemas.source import SourceOut

router = APIRouter(tags=["sources"])


@router.get("/sources", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db)) -> list[SourceOut]:
    now = datetime.now(timezone.utc)
    stale_seconds = get_settings().SOURCE_STALE_SECONDS
    output: list[SourceOut] = []
    for source in db.query(MonitoringSource).order_by(MonitoringSource.name).all():
        heartbeat = source.last_heartbeat_at
        if heartbeat is not None and heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=timezone.utc)
        is_live = (
            heartbeat is not None and (now - heartbeat).total_seconds() <= stale_seconds
        )
        output.append(
            SourceOut(
                source_id=source.source_id,
                name=source.name,
                source_type=source.source_type,
                last_event_at=source.last_event_at,
                last_heartbeat_at=source.last_heartbeat_at,
                events_received=source.events_received,
                malformed_lines=source.malformed_lines,
                delivery_failures=source.delivery_failures,
                status="live" if is_live else "stale",
            )
        )
    return output
