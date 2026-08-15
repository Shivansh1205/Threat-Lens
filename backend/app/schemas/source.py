from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SourceHeartbeat(BaseModel):
    name: str = Field(default="Nginx website", min_length=1, max_length=200)
    source_type: str = Field(default="nginx", min_length=1, max_length=50)
    malformed_lines: int = Field(default=0, ge=0)
    delivery_failures: int = Field(default=0, ge=0)


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_id: str
    name: str
    source_type: str
    last_event_at: datetime | None
    last_heartbeat_at: datetime | None
    events_received: int
    malformed_lines: int
    delivery_failures: int
    status: str
