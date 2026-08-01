"""Unusual-IP detector.

Phase 4: fully stateless. Known IPs and the bootstrap counter now live in the
persistent BehaviorProfile (via BehaviorProfiler), not in this class — they
survive a uvicorn restart, unlike the Phase 3 in-memory {user_id: set[ip]}
dict this replaced.

Pipeline ordering matters here: `api/logs.py` runs detection *before* calling
`BehaviorProfiler.update()` for the same event. `update()` unconditionally
adds the event's IP to `known_ips` — if detection ran afterward, this
detector would always find its own event's IP already "known" and never
fire. Running detection first means this detector reads known_ips/login_count
as they stood prior to the current event, which is what makes novelty
detection possible. See `app/profiling/profiler.py`'s module docstring for
the full explanation.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.detection.base import AlertCandidate, Detector
from app.models.log_event import LogEvent
from app.profiling.profiler import BehaviorProfiler
from app.schemas.common import EventType, Severity

_LOGIN_TYPES = {EventType.LOGIN_SUCCESS, EventType.LOGIN_FAILURE}


class UnusualIpDetector(Detector):
    """Per-user known-IP detector, backed entirely by the persistent profile."""

    def check(self, event: LogEvent, db: Session) -> list[AlertCandidate]:
        if event.event_type not in _LOGIN_TYPES:
            return []

        profiler = BehaviorProfiler(db)

        if not profiler.is_past_bootstrap(event.user_id):
            return []

        known_ips = profiler.get_known_ips(event.user_id)
        if event.ip in known_ips:
            return []

        return [
            AlertCandidate(
                alert_type="unusual_ip",
                severity=Severity.LOW,
                score=30,
                message=(
                    f"Login for {event.user_id} from previously-unseen IP "
                    f"{event.ip}."
                ),
                triggered_by_event_id=event.id,
            )
        ]
