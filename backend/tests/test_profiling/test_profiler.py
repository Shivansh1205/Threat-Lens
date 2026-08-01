"""BehaviorProfiler unit tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.user import User
from app.profiling.profiler import BehaviorProfiler
from app.schemas.common import EventType

from tests.test_detection._helpers import make_event

BASE = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)


def _ensure_user(db: Session, user_id: str) -> None:
    if db.query(User).filter(User.user_id == user_id).one_or_none() is None:
        db.add(User(user_id=user_id, first_seen_at=BASE, last_seen_at=BASE))
        db.commit()


def _login(user_id: str, ts: datetime, ip: str = "10.0.0.1") -> object:
    return make_event(user_id, EventType.LOGIN_SUCCESS, ts, ip=ip)


def _logout(user_id: str, ts: datetime, ip: str = "10.0.0.1") -> object:
    return make_event(user_id, EventType.LOGOUT, ts, ip=ip)


# ---------------------------------------------------------------- a, b


def test_get_or_create_new_user(db_session: Session) -> None:
    _ensure_user(db_session, "alice")
    profiler = BehaviorProfiler(db_session, alpha=0.05)

    profile = profiler.get_or_create("alice")

    assert profile.login_count == 0
    assert profile.known_ips == []
    assert profile.deviation_score == 0.0
    assert profile.typical_login_hour is None
    assert profile.login_hour_variance is None
    assert profile.typical_days_between_logins is None
    assert profile.avg_session_duration_seconds is None
    assert profile.last_login_at is None
    assert profile.last_logout_at is None
    assert profile.last_event_at is None
    assert profile.total_sessions == 0


def test_get_or_create_existing_user(db_session: Session) -> None:
    _ensure_user(db_session, "alice")
    profiler = BehaviorProfiler(db_session, alpha=0.05)

    first = profiler.get_or_create("alice")
    first_id = first.id
    second = profiler.get_or_create("alice")

    assert second.id == first_id
    from app.models.behavior_profile import BehaviorProfile

    assert db_session.query(BehaviorProfile).count() == 1


# ------------------------------------------------------------------- c


def test_update_login_success(db_session: Session) -> None:
    _ensure_user(db_session, "alice")
    profiler = BehaviorProfiler(db_session, alpha=0.05)

    event = _login("alice", BASE, ip="10.0.0.5")
    profile = profiler.update(event)

    assert profile.login_count == 1
    assert "10.0.0.5" in profile.known_ips
    assert profile.typical_login_hour == 9.0
    assert profile.last_login_at is not None
    assert profile.last_event_at is not None


# ------------------------------------------------------------------- d


def test_update_multiple_logins_ema(db_session: Session) -> None:
    _ensure_user(db_session, "alice")
    # Higher alpha than the config default so 10 events produce a clear signal.
    profiler = BehaviorProfiler(db_session, alpha=0.3)

    hours = [9, 10, 9, 10, 9, 10, 14, 9, 10, 9]
    deviation_before_outlier = None
    deviation_at_outlier = None

    for day, hour in enumerate(hours, start=1):
        ts = BASE.replace(hour=hour) + timedelta(days=day - 1)
        profile = profiler.update(_login("alice", ts))
        if day == 6:  # last event before the hour-14 outlier
            deviation_before_outlier = profile.deviation_score
        if day == 7:  # the hour-14 outlier itself
            deviation_at_outlier = profile.deviation_score

    final_profile = profiler.get_or_create("alice")

    assert 7.0 <= final_profile.typical_login_hour <= 11.5
    assert final_profile.login_hour_variance > 0
    assert deviation_at_outlier > deviation_before_outlier


# ------------------------------------------------------------------- e


def test_update_logout_session_duration(db_session: Session) -> None:
    _ensure_user(db_session, "alice")
    profiler = BehaviorProfiler(db_session, alpha=0.05)

    profiler.update(_login("alice", BASE))
    profile = profiler.update(_logout("alice", BASE + timedelta(seconds=1800)))

    assert profile.avg_session_duration_seconds == 1800.0
    assert profile.total_sessions == 1


# ------------------------------------------------------------------- f


def test_update_logout_without_login(db_session: Session) -> None:
    _ensure_user(db_session, "alice")
    profiler = BehaviorProfiler(db_session, alpha=0.05)

    profile = profiler.update(_logout("alice", BASE))

    assert profile.avg_session_duration_seconds is None
    assert profile.total_sessions == 0


# ------------------------------------------------------------------- g


def test_dedup_same_timestamp(db_session: Session) -> None:
    _ensure_user(db_session, "alice")
    profiler = BehaviorProfiler(db_session, alpha=0.05)

    profiler.update(_login("alice", BASE))
    profile = profiler.update(_login("alice", BASE))  # exact same timestamp again

    assert profile.login_count == 1


# ------------------------------------------------------------------- h


def test_known_ips_accumulate(db_session: Session) -> None:
    _ensure_user(db_session, "alice")
    profiler = BehaviorProfiler(db_session, alpha=0.05)

    ips = ["10.0.0.1", "10.0.0.2", "10.0.0.1", "10.0.0.3", "10.0.0.2"]
    for i, ip in enumerate(ips):
        profiler.update(_login("alice", BASE + timedelta(days=i), ip=ip))

    profile = profiler.get_or_create("alice")
    assert sorted(profile.known_ips) == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]


# ------------------------------------------------------------------- i


def test_deviation_score_ip_novelty(db_session: Session) -> None:
    _ensure_user(db_session, "alice")
    profiler = BehaviorProfiler(db_session, alpha=0.05)

    # 4 logins from IP A — past the default bootstrap count (3).
    for i in range(4):
        profiler.update(_login("alice", BASE + timedelta(days=i), ip="10.0.0.1"))

    profile = profiler.update(_login("alice", BASE + timedelta(days=4), ip="10.0.0.99"))

    assert profile.deviation_score > 0.0


# ------------------------------------------------------------------- j


def test_deviation_score_hour_outlier(db_session: Session) -> None:
    _ensure_user(db_session, "alice")
    profiler = BehaviorProfiler(db_session, alpha=0.3)

    # Small natural jitter around hour 9 so login_hour_variance is nonzero —
    # a perfectly identical hour every day never builds any variance, and
    # hour_deviation is defined as 0 when there's "not enough data" (variance
    # still 0), which would hide the hour-3 outlier entirely.
    baseline_hours = [9, 10, 9, 8, 9, 10, 9, 8, 9, 10]
    last_normal_score = None
    for day, hour in enumerate(baseline_hours):
        ts = BASE.replace(hour=hour) + timedelta(days=day)
        profile = profiler.update(_login("alice", ts))
        last_normal_score = profile.deviation_score

    outlier_ts = BASE.replace(hour=3) + timedelta(days=len(baseline_hours))
    outlier_profile = profiler.update(_login("alice", outlier_ts))

    assert outlier_profile.deviation_score > last_normal_score
    assert outlier_profile.deviation_score > 0.5


# ------------------------------------------------------------------- k


def test_deviation_score_frequency_outlier(db_session: Session) -> None:
    _ensure_user(db_session, "alice")
    profiler = BehaviorProfiler(db_session, alpha=0.05)

    last_normal_score = None
    for day in range(7):
        ts = BASE.replace(hour=9) + timedelta(days=day)
        profile = profiler.update(_login("alice", ts))
        last_normal_score = profile.deviation_score

    late_ts = BASE.replace(hour=9) + timedelta(days=6 + 30)
    late_profile = profiler.update(_login("alice", late_ts))

    assert late_profile.deviation_score > last_normal_score
    assert late_profile.deviation_score > 0.0
