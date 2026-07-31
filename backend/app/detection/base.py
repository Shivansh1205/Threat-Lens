"""Abstract detector interface and the candidate-alert value type.

Detectors are *pure*: they observe events and yield ``AlertCandidate``s. They
never touch the database. The ``DetectorRegistry`` is the only place that
converts candidates to ``Alert`` rows and commits them.

Keeping detection stateless-with-respect-to-the-DB makes each rule trivial to
test (feed it events, assert on the returned list) and keeps transaction
control in a single place.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.log_event import LogEvent
from app.schemas.common import Severity


@dataclass
class AlertCandidate:
    """A detector's intent to raise an alert. Not yet persisted."""

    alert_type: str
    severity: Severity
    score: int
    message: str
    triggered_by_event_id: UUID


class Detector(ABC):
    """Base class for every rule-based detector."""

    @abstractmethod
    def check(self, event: LogEvent, db: Session) -> list[AlertCandidate]:
        """Inspect ``event`` and return zero or more candidates."""

    def name(self) -> str:
        return self.__class__.__name__
