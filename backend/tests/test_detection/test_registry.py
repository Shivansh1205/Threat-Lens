"""DetectorRegistry integration tests — the persistence boundary."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.detection.registry import DetectorRegistry
from app.detection.rules import BruteForceDetector, PortScanDetector, UnusualIpDetector
from app.models.alert import Alert
from app.models.user import User
from app.schemas.common import EventType

from tests.test_detection._helpers import make_event


def _fresh_registry() -> DetectorRegistry:
    return DetectorRegistry(
        [BruteForceDetector(), PortScanDetector(), UnusualIpDetector()]
    )


def _persist_user_and_event(db_session: Session, event) -> None:
    """The registry writes Alerts referencing user_id and event.id — those FKs
    must resolve, so we persist the user and the event first."""
    if db_session.query(User).filter(User.user_id == event.user_id).one_or_none() is None:
        db_session.add(
            User(
                user_id=event.user_id,
                first_seen_at=datetime.now(timezone.utc),
                last_seen_at=datetime.now(timezone.utc),
            )
        )
    db_session.add(event)
    db_session.commit()


def test_single_failure_persists_no_alert(db_session: Session) -> None:
    reg = _fresh_registry()
    ev = make_event("alice", EventType.LOGIN_FAILURE, datetime(2026, 1, 1, tzinfo=timezone.utc))
    _persist_user_and_event(db_session, ev)

    alerts = reg.run_all(ev, db_session)
    assert alerts == []
    assert db_session.query(Alert).count() == 0


def test_five_rapid_failures_persists_one_medium(db_session: Session) -> None:
    reg = _fresh_registry()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    last_alerts: list[Alert] = []
    for i in range(5):
        ev = make_event(
            "alice", EventType.LOGIN_FAILURE, base.replace(second=i * 2)
        )
        _persist_user_and_event(db_session, ev)
        last_alerts = reg.run_all(ev, db_session)

    assert len(last_alerts) == 1
    assert last_alerts[0].severity.name == "MEDIUM"
    assert last_alerts[0].alert_type == "brute_force"
    assert db_session.query(Alert).count() == 1


def test_triggered_by_event_id_is_linked(db_session: Session) -> None:
    reg = _fresh_registry()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    events = []
    for i in range(5):
        ev = make_event(
            "alice", EventType.LOGIN_FAILURE, base.replace(second=i * 2)
        )
        _persist_user_and_event(db_session, ev)
        alerts = reg.run_all(ev, db_session)
        events.append((ev, alerts))

    # The 5th event (index 4) is the one that triggered the MEDIUM alert.
    ev5, alerts5 = events[4]
    assert len(alerts5) == 1
    assert alerts5[0].triggered_by_event_id == ev5.id


def test_stub_detector_not_registered() -> None:
    """Guard against accidental re-registration of the retired stub."""
    from app.detection.registry import get_registry

    names = {d.name() for d in get_registry().detectors}
    assert names == {"BruteForceDetector", "PortScanDetector", "UnusualIpDetector"}


def test_port_scan_60_events_no_crash_two_alerts(db_session: Session) -> None:
    """Regression: 60 sequential PORT_ACCESS events must not raise DetachedInstanceError.

    Before the fix, the registry committed after the HIGH alert, expiring the
    ORM LogEvent instances still held in the detector's sliding window. The next
    check() call accessed .port on an expired instance → DetachedInstanceError.
    """
    from datetime import timedelta

    reg = _fresh_registry()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ip = "198.51.100.42"

    # Persist the user once up front.
    db_session.add(
        User(
            user_id="scanner",
            first_seen_at=base,
            last_seen_at=base,
        )
    )
    db_session.commit()

    all_alerts: list[Alert] = []
    for i in range(60):
        ev = make_event(
            user_id="scanner",
            event_type=EventType.PORT_ACCESS,
            timestamp=base + timedelta(seconds=i * 0.03),
            ip=ip,
            port=i + 1,
        )
        db_session.add(ev)
        db_session.flush()
        alerts = reg.run_all(ev, db_session)
        db_session.commit()  # simulates what the ingest endpoint does
        all_alerts.extend(alerts)

    severities = sorted(a.severity.name for a in all_alerts)
    assert severities == ["CRITICAL", "HIGH"], f"Expected HIGH+CRITICAL, got {severities}"
    assert db_session.query(Alert).count() == 2
