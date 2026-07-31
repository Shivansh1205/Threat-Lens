"""PortScanDetector unit tests."""

from datetime import datetime, timedelta, timezone

from app.detection.rules.port_scan import PortScanDetector
from app.schemas.common import EventType, Severity

from tests.test_detection._helpers import make_event

BASE = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)


def _scan(
    detector: PortScanDetector,
    ip: str,
    ports,
    start: float = 0.0,
    step: float = 0.05,
) -> list:
    """Feed a sequence of PORT_ACCESS events, return per-event candidate lists."""
    results = []
    for i, port in enumerate(ports):
        ev = make_event(
            user_id="scanner",
            event_type=EventType.PORT_ACCESS,
            timestamp=BASE + timedelta(seconds=start + i * step),
            ip=ip,
            port=port,
        )
        results.append(detector.check(ev, db=None))
    return results


def test_fourteen_distinct_ports_no_candidate() -> None:
    d = PortScanDetector()
    out = _scan(d, "1.1.1.1", ports=list(range(1, 15)))
    assert all(x == [] for x in out)


def test_fifteenth_distinct_port_emits_high() -> None:
    d = PortScanDetector()
    out = _scan(d, "1.1.1.1", ports=list(range(1, 16)))
    assert all(x == [] for x in out[:14])
    assert len(out[14]) == 1
    assert out[14][0].severity == Severity.HIGH
    assert out[14][0].score == 75


def test_fiftieth_distinct_port_emits_critical() -> None:
    d = PortScanDetector()
    out = _scan(d, "1.1.1.1", ports=list(range(1, 51)), step=0.05)
    emitted = {i: c for i, c in enumerate(out) if c}
    assert set(emitted.keys()) == {14, 49}
    assert emitted[14][0].severity == Severity.HIGH
    assert emitted[49][0].severity == Severity.CRITICAL
    assert emitted[49][0].score == 95


def test_same_port_repeated_no_candidate() -> None:
    d = PortScanDetector()
    # 30 hits, all port 22 → distinct count is 1.
    out = _scan(d, "1.1.1.1", ports=[22] * 30)
    assert all(x == [] for x in out)


def test_two_ips_do_not_cross_contaminate() -> None:
    d = PortScanDetector()
    # Each IP touches 10 distinct ports — both below the 15 threshold.
    out_a = _scan(d, "1.1.1.1", ports=list(range(1, 11)))
    out_b = _scan(d, "2.2.2.2", ports=list(range(100, 110)), start=5.0)
    assert all(x == [] for x in out_a)
    assert all(x == [] for x in out_b)


def test_non_port_access_events_ignored() -> None:
    d = PortScanDetector()
    # A LOGIN_SUCCESS with a "port" set should not count as a scan hit.
    ev = make_event(
        "scanner",
        EventType.LOGIN_SUCCESS,
        BASE,
        ip="1.1.1.1",
        port=22,
    )
    assert d.check(ev, db=None) == []
