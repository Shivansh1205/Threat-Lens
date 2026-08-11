"""Validated, atomically replaceable detection-threshold snapshots."""

from __future__ import annotations

import logging
import threading

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.detection_settings import DetectionSettingsRecord

logger = logging.getLogger(__name__)


class BruteForceLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    window_seconds: int = Field(ge=1, le=3600)
    medium_threshold: int = Field(ge=1, le=100_000)
    high_threshold: int = Field(ge=1, le=100_000)
    critical_threshold: int = Field(ge=1, le=100_000)

    @model_validator(mode="after")
    def validate_order(self) -> BruteForceLimits:
        if not self.medium_threshold < self.high_threshold < self.critical_threshold:
            raise ValueError("brute-force thresholds must satisfy medium < high < critical")
        return self


class EscalatingLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    window_seconds: int = Field(ge=1, le=3600)
    high_threshold: int = Field(ge=1, le=100_000)
    critical_threshold: int = Field(ge=1, le=100_000)

    @model_validator(mode="after")
    def validate_order(self) -> EscalatingLimits:
        if self.high_threshold >= self.critical_threshold:
            raise ValueError("thresholds must satisfy high < critical")
        return self


class UnusualIpLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    bootstrap_count: int = Field(ge=1, le=100_000)


class DetectionThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    brute_force: BruteForceLimits
    port_scan: EscalatingLimits
    unusual_ip: UnusualIpLimits
    request_flood: EscalatingLimits
    path_probe: EscalatingLimits
    server_error_spike: EscalatingLimits


def thresholds_from_environment(settings: Settings | None = None) -> DetectionThresholds:
    s = settings or get_settings()
    return DetectionThresholds(
        brute_force=BruteForceLimits(
            window_seconds=s.BRUTE_FORCE_WINDOW_SECONDS,
            medium_threshold=s.BRUTE_FORCE_MEDIUM_THRESHOLD,
            high_threshold=s.BRUTE_FORCE_HIGH_THRESHOLD,
            critical_threshold=s.BRUTE_FORCE_CRITICAL_THRESHOLD,
        ),
        port_scan=EscalatingLimits(
            window_seconds=s.PORT_SCAN_WINDOW_SECONDS,
            high_threshold=s.PORT_SCAN_HIGH_THRESHOLD,
            critical_threshold=s.PORT_SCAN_CRITICAL_THRESHOLD,
        ),
        unusual_ip=UnusualIpLimits(bootstrap_count=s.UNUSUAL_IP_BOOTSTRAP_COUNT),
        request_flood=EscalatingLimits(
            window_seconds=s.REQUEST_RATE_WINDOW_SECONDS,
            high_threshold=s.REQUEST_RATE_HIGH_THRESHOLD,
            critical_threshold=s.REQUEST_RATE_CRITICAL_THRESHOLD,
        ),
        path_probe=EscalatingLimits(
            window_seconds=s.PATH_PROBE_WINDOW_SECONDS,
            high_threshold=s.PATH_PROBE_HIGH_THRESHOLD,
            critical_threshold=s.PATH_PROBE_CRITICAL_THRESHOLD,
        ),
        server_error_spike=EscalatingLimits(
            window_seconds=s.SERVER_ERROR_WINDOW_SECONDS,
            high_threshold=s.SERVER_ERROR_HIGH_THRESHOLD,
            critical_threshold=s.SERVER_ERROR_CRITICAL_THRESHOLD,
        ),
    )


_state_lock = threading.Lock()
_active_thresholds = thresholds_from_environment()


def get_detection_thresholds() -> DetectionThresholds:
    with _state_lock:
        return _active_thresholds


def apply_detection_thresholds(values: DetectionThresholds) -> None:
    global _active_thresholds
    with _state_lock:
        _active_thresholds = values


def restore_environment_thresholds() -> DetectionThresholds:
    values = thresholds_from_environment()
    apply_detection_thresholds(values)
    return values


def load_persisted_thresholds(
    db: Session,
) -> tuple[DetectionThresholds, DetectionSettingsRecord | None]:
    record = db.get(DetectionSettingsRecord, 1)
    if record is None:
        return restore_environment_thresholds(), None
    try:
        values = DetectionThresholds.model_validate(record.values)
    except ValueError:
        logger.exception("Persisted detection settings are invalid; using environment defaults")
        return restore_environment_thresholds(), record
    apply_detection_thresholds(values)
    return values, record
