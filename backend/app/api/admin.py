"""API-key-protected administrative operations."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.detection.registry import reset_registry
from app.detection.settings import (
    DetectionThresholds,
    apply_detection_thresholds,
    get_detection_thresholds,
    restore_environment_thresholds,
    thresholds_from_environment,
)
from app.models.detection_settings import DetectionSettingsRecord
from app.schemas.decay import DecaySummary
from app.scoring.decay_job import run_decay_pass
from app.security import require_admin_key

router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin_key)])


class DetectionSettingsResponse(BaseModel):
    values: DetectionThresholds
    defaults: DetectionThresholds
    is_overridden: bool
    updated_at: datetime | None


def _settings_response(
    record: DetectionSettingsRecord | None,
) -> DetectionSettingsResponse:
    return DetectionSettingsResponse(
        values=get_detection_thresholds(),
        defaults=thresholds_from_environment(),
        is_overridden=record is not None,
        updated_at=record.updated_at if record else None,
    )


@router.get("/admin/detection-settings", response_model=DetectionSettingsResponse)
def get_detection_settings(db: Session = Depends(get_db)) -> DetectionSettingsResponse:
    return _settings_response(db.get(DetectionSettingsRecord, 1))


@router.put("/admin/detection-settings", response_model=DetectionSettingsResponse)
def update_detection_settings(
    payload: DetectionThresholds,
    db: Session = Depends(get_db),
) -> DetectionSettingsResponse:
    record = db.get(DetectionSettingsRecord, 1)
    if record is None:
        record = DetectionSettingsRecord(id=1, values=payload.model_dump(mode="json"))
    else:
        record.values = payload.model_dump(mode="json")
    db.add(record)
    db.commit()
    db.refresh(record)

    apply_detection_thresholds(payload)
    reset_registry()
    return _settings_response(record)


@router.delete("/admin/detection-settings", response_model=DetectionSettingsResponse)
def reset_detection_settings(db: Session = Depends(get_db)) -> DetectionSettingsResponse:
    record = db.get(DetectionSettingsRecord, 1)
    if record is not None:
        db.delete(record)
        db.commit()
    restore_environment_thresholds()
    reset_registry()
    return _settings_response(None)


@router.post("/admin/decay-now", response_model=DecaySummary)
def decay_now(db: Session = Depends(get_db)) -> DecaySummary:
    """Run one time-based risk-decay pass synchronously and commit it."""
    summary = run_decay_pass(db)
    db.commit()
    return DecaySummary(**summary)
