"""Detectors designed for structured Nginx access-log events."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.detection.base import AlertCandidate, Detector
from app.detection.settings import DetectionThresholds, get_detection_thresholds
from app.models.log_event import LogEvent
from app.schemas.common import Severity


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class _Request:
    timestamp: datetime
    endpoint: str


class _WindowDetector(Detector):
    def __init__(self) -> None:
        self._windows: dict[str, deque[_Request]] = {}
        self._last_emitted: dict[str, int] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _trim(window: deque[_Request], now: datetime, seconds: int) -> None:
        cutoff = now - timedelta(seconds=seconds)
        while window and window[0].timestamp < cutoff:
            window.popleft()

    def _candidate(
        self,
        event: LogEvent,
        alert_type: str,
        severity: Severity,
        score: int,
        message: str,
        count: int,
        window_seconds: int,
    ) -> AlertCandidate:
        return AlertCandidate(
            alert_type=alert_type,
            severity=severity,
            score=score,
            message=message,
            triggered_by_event_id=event.id,
            evidence={
                "source_id": event.source_id,
                "ip": event.ip,
                "method": event.http_method,
                "endpoint": event.endpoint,
                "http_status": event.http_status,
                "count": count,
                "window_seconds": window_seconds,
            },
        )


class RequestRateDetector(_WindowDetector):
    def check(
        self, event: LogEvent, db: Session, thresholds: DetectionThresholds | None = None
    ) -> list[AlertCandidate]:
        if not event.http_method:
            return []
        limits = (thresholds or get_detection_thresholds()).request_flood
        key = f"{event.source_id or 'legacy'}:{event.ip}"
        now = _utc(event.timestamp)
        with self._lock:
            window = self._windows.setdefault(key, deque())
            window.append(_Request(now, event.endpoint or ""))
            self._trim(window, now, limits.window_seconds)
            count = len(window)
            last = self._last_emitted.get(key, 0)
            if count < limits.high_threshold:
                self._last_emitted.pop(key, None)
                return []
            if (
                count >= limits.critical_threshold
                and last < limits.critical_threshold
            ):
                self._last_emitted[key] = limits.critical_threshold
                return [
                    self._candidate(
                        event,
                        "request_flood",
                        Severity.CRITICAL,
                        90,
                        f"{count} HTTP requests from {event.ip} in "
                        f"{limits.window_seconds}s.",
                        count,
                        limits.window_seconds,
                    )
                ]
            if last < limits.high_threshold:
                self._last_emitted[key] = limits.high_threshold
                return [
                    self._candidate(
                        event,
                        "request_flood",
                        Severity.HIGH,
                        70,
                        f"{count} HTTP requests from {event.ip} in "
                        f"{limits.window_seconds}s.",
                        count,
                        limits.window_seconds,
                    )
                ]
        return []


class PathProbeDetector(_WindowDetector):
    def check(
        self, event: LogEvent, db: Session, thresholds: DetectionThresholds | None = None
    ) -> list[AlertCandidate]:
        if event.http_status != 404 or not event.endpoint:
            return []
        limits = (thresholds or get_detection_thresholds()).path_probe
        key = f"{event.source_id or 'legacy'}:{event.ip}"
        now = _utc(event.timestamp)
        with self._lock:
            window = self._windows.setdefault(key, deque())
            window.append(_Request(now, event.endpoint))
            self._trim(window, now, limits.window_seconds)
            count = len({item.endpoint for item in window})
            last = self._last_emitted.get(key, 0)
            if (
                count >= limits.critical_threshold
                and last < limits.critical_threshold
            ):
                self._last_emitted[key] = limits.critical_threshold
                return [
                    self._candidate(
                        event,
                        "path_probe",
                        Severity.CRITICAL,
                        88,
                        f"{count} distinct missing paths requested from {event.ip}.",
                        count,
                        limits.window_seconds,
                    )
                ]
            if (
                count >= limits.high_threshold
                and last < limits.high_threshold
            ):
                self._last_emitted[key] = limits.high_threshold
                return [
                    self._candidate(
                        event,
                        "path_probe",
                        Severity.HIGH,
                        68,
                        f"{count} distinct missing paths requested from {event.ip}.",
                        count,
                        limits.window_seconds,
                    )
                ]
        return []


class ServerErrorSpikeDetector(_WindowDetector):
    def check(
        self, event: LogEvent, db: Session, thresholds: DetectionThresholds | None = None
    ) -> list[AlertCandidate]:
        if event.http_status is None or event.http_status < 500:
            return []
        limits = (thresholds or get_detection_thresholds()).server_error_spike
        key = f"{event.source_id or 'legacy'}:{event.ip}"
        now = _utc(event.timestamp)
        with self._lock:
            window = self._windows.setdefault(key, deque())
            window.append(_Request(now, event.endpoint or ""))
            self._trim(window, now, limits.window_seconds)
            count = len(window)
            last = self._last_emitted.get(key, 0)
            if (
                count >= limits.critical_threshold
                and last < limits.critical_threshold
            ):
                self._last_emitted[key] = limits.critical_threshold
                return [
                    self._candidate(
                        event,
                        "server_error_spike",
                        Severity.CRITICAL,
                        85,
                        f"{count} server errors observed for requests from {event.ip}.",
                        count,
                        limits.window_seconds,
                    )
                ]
            if (
                count >= limits.high_threshold
                and last < limits.high_threshold
            ):
                self._last_emitted[key] = limits.high_threshold
                return [
                    self._candidate(
                        event,
                        "server_error_spike",
                        Severity.HIGH,
                        65,
                        f"{count} server errors observed for requests from {event.ip}.",
                        count,
                        limits.window_seconds,
                    )
                ]
        return []
