"""Unusual-IP detector.

Tracks the set of source IPs seen for each user across their login events.
The first ``UNUSUAL_IP_BOOTSTRAP_COUNT`` events establish the known-IP set
silently (no alerts, no cold-start noise). After that, any login from a
previously-unseen IP fires a LOW candidate, then the IP joins the known set so
we don't re-alert on subsequent logins from it.

TODO(Phase 4): move known-IP tracking into the BehaviorProfiler with proper
persistence — right now the set only lives for the lifetime of the process,
which is a known limitation logged in PHASES.md Phase 3 open questions.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.detection.base import AlertCandidate, Detector
from app.models.log_event import LogEvent
from app.schemas.common import EventType, Severity

_LOGIN_TYPES = {EventType.LOGIN_SUCCESS, EventType.LOGIN_FAILURE}


class UnusualIpDetector(Detector):
    """Per-user known-IP-set detector with a cold-start bootstrap."""

    def __init__(self) -> None:
        # TODO(Phase 6+): move to Redis for horizontal scaling.
        # TODO(Phase 4): fold into BehaviorProfiler with DB-backed persistence.
        self._known_ips: dict[str, set[str]] = {}
        self._login_counts: dict[str, int] = {}
        self._settings = get_settings()

    def check(self, event: LogEvent, db: Session) -> list[AlertCandidate]:
        if event.event_type not in _LOGIN_TYPES:
            return []

        self._login_counts[event.user_id] = self._login_counts.get(event.user_id, 0) + 1
        known = self._known_ips.setdefault(event.user_id, set())

        if self._login_counts[event.user_id] <= self._settings.UNUSUAL_IP_BOOTSTRAP_COUNT:
            known.add(event.ip)
            return []

        if event.ip in known:
            return []

        # Unknown IP for this user post-bootstrap — flag once, then remember.
        known.add(event.ip)
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
