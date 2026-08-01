"""Concurrency regression tests for BruteForceDetector and PortScanDetector.

Every other detector test in this suite calls ``check()`` sequentially, which
can never exercise a race condition — Python only reveals races when two
threads genuinely interleave inside the same read-decide-write section. These
tests use real OS threads (never asyncio) to reproduce the duplicate-alert
bug found during Phase 4 live verification: concurrent requests for the same
user_id/ip could both read a stale ``last_emitted`` before either wrote the
update, so both emitted an alert at the same threshold — and unguarded
concurrent writes to the same window could corrupt state outright (see the
``deque mutated during iteration`` crash below, which explains the missing
CRITICAL alert in the original live run).

Two different techniques are used, because the two detectors' critical
sections are different widths:

- PortScanDetector's distinct-port count *iterates the whole window*
  (``len({sn.port for sn in window})``), a wide target — natural concurrent
  execution (many threads released together via a ``threading.Barrier``, with
  a shortened GIL switch interval to encourage interleaving) reproduces this
  reliably; see ``test_concurrent_port_scan_no_duplicate_or_missing_alerts``.
- BruteForceDetector's threshold check is a single dict ``get()`` / compare /
  ``__setitem__`` — a much narrower target. In testing, natural thread
  scheduling under CPython's GIL essentially never landed inside that window
  (0 failures across 90+ attempts at various thread counts and switch
  intervals), even though the race is real and mechanistically identical.
  ``test_concurrent_brute_force_forced_race_produces_duplicate`` forces the
  exact interleaving deterministically instead of hoping for GIL-timing luck,
  and ``test_concurrent_brute_force_no_duplicate_or_missing_alerts`` is kept
  as a best-effort natural-concurrency stress test alongside it.
"""

from __future__ import annotations

import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from app.detection.base import AlertCandidate
from app.detection.rules.brute_force import BruteForceDetector
from app.detection.rules.port_scan import PortScanDetector
from app.schemas.common import EventType

from tests.test_detection._helpers import make_event

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)

# CPython's default GIL switch interval (5ms) is coarse enough that a narrow
# critical section often finishes within one thread's timeslice even under a
# barrier-synchronized start. Shortening it makes the GIL hand off far more
# often, which is what actually turns a real race into an observable failure.
_FAST_SWITCH_INTERVAL = 1e-6

# A single barrier-synchronized burst catches a race most of the time but not
# every time; repeating the scenario makes a real race show up reliably while
# keeping the locked (fixed) path fast and always green.
_ATTEMPTS = 8


def _run_with_barrier(fn, barrier: threading.Barrier):
    """Block every worker at the barrier so they all release together,
    maximizing the odds of genuine interleaving inside the critical section.
    """
    barrier.wait()
    return fn()


def _fire_concurrently(events, check) -> list[AlertCandidate]:
    n = len(events)
    barrier = threading.Barrier(n)
    all_candidates: list[AlertCandidate] = []

    with ThreadPoolExecutor(max_workers=n) as pool:
        futures = [
            pool.submit(_run_with_barrier, lambda ev=ev: check(ev), barrier) for ev in events
        ]
        for future in futures:
            all_candidates.extend(future.result())

    return all_candidates


def test_concurrent_brute_force_no_duplicate_or_missing_alerts() -> None:
    """Best-effort natural-concurrency stress test: 30 concurrent
    LOGIN_FAILUREs for one user_id, fired via real threads. Passes reliably
    with the fix. See module docstring — this specific race is narrow enough
    that natural GIL scheduling may not reproduce it every run; the
    deterministic test below is the reliable regression guard.
    """
    original_interval = sys.getswitchinterval()
    sys.setswitchinterval(_FAST_SWITCH_INTERVAL)
    try:
        for attempt in range(_ATTEMPTS):
            detector = BruteForceDetector()
            events = [
                make_event(
                    user_id="alice",
                    event_type=EventType.LOGIN_FAILURE,
                    timestamp=BASE + timedelta(seconds=i),
                )
                for i in range(30)
            ]

            all_candidates = _fire_concurrently(events, lambda ev: detector.check(ev, db=None))

            severities = sorted(c.severity.name for c in all_candidates)
            assert severities == ["CRITICAL", "HIGH", "MEDIUM"], (
                f"attempt {attempt}: expected exactly one MEDIUM, one HIGH, "
                f"one CRITICAL — got {severities}"
            )
            assert all(c.alert_type == "brute_force" for c in all_candidates)
    finally:
        sys.setswitchinterval(original_interval)


class _RacyLastEmitted(dict):
    """Instrumented ``last_emitted`` dict that deterministically forces two
    concurrent ``get()`` callers to both observe the pre-update value.

    The first caller to reach ``get()`` blocks (briefly) until a second caller
    has also called ``get()``, guaranteeing both see the same stale value
    before either writes the update — reproducing "two threads both read
    last_emitted=0 before either writes it" on demand, rather than hoping
    GIL scheduling happens to land there (see module docstring for why that
    doesn't work reliably for this particular critical section).
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._first_read = threading.Event()
        self._second_read = threading.Event()
        self._call_lock = threading.Lock()
        self._calls = 0

    def get(self, *args, **kwargs):
        with self._call_lock:
            self._calls += 1
            is_first = self._calls == 1

        value = super().get(*args, **kwargs)

        if is_first:
            self._first_read.set()
            # Give the second caller a chance to also read the stale value.
            # Short timeout: with the fix in place, the lock in check() means
            # the second caller never even reaches get() while this call is
            # in flight, so this just times out quickly and we proceed
            # (correctly single-threaded from here on, since the lock
            # serializes the rest of the call).
            self._second_read.wait(timeout=0.3)
        else:
            self._second_read.set()

        return value


def test_concurrent_brute_force_forced_race_produces_duplicate() -> None:
    """Deterministic reproduction of the exact race: force two threads to
    both read ``last_emitted`` before either writes it, on the event that
    crosses the MEDIUM threshold. With the lock in place, ``check()``
    serializes the two threads entirely (the second thread can't even reach
    the instrumented ``get()`` until the first releases the lock), so only
    one MEDIUM candidate is produced.
    """
    detector = BruteForceDetector()

    # 4 sequential failures — one below the MEDIUM threshold (5).
    for i in range(4):
        detector.check(
            make_event("alice", EventType.LOGIN_FAILURE, BASE + timedelta(seconds=i)), db=None
        )

    detector._last_emitted = _RacyLastEmitted(detector._last_emitted)

    results: list[list[AlertCandidate]] = []
    results_lock = threading.Lock()

    def worker(offset_ms: int) -> None:
        ev = make_event(
            "alice",
            EventType.LOGIN_FAILURE,
            BASE + timedelta(seconds=4, milliseconds=offset_ms),
        )
        candidates = detector.check(ev, db=None)
        with results_lock:
            results.append(candidates)

    t1 = threading.Thread(target=worker, args=(0,))
    t2 = threading.Thread(target=worker, args=(1,))

    t1.start()
    assert detector._last_emitted._first_read.wait(timeout=1), "thread 1 never reached the read"
    t2.start()
    t1.join(timeout=2)
    t2.join(timeout=2)

    all_candidates = [c for r in results for c in r]
    severities = sorted(c.severity.name for c in all_candidates)
    assert severities == ["MEDIUM"], (
        f"expected exactly one MEDIUM despite forced concurrent reads — got {severities}"
    )


def test_concurrent_port_scan_no_duplicate_or_missing_alerts() -> None:
    """60 concurrent PORT_ACCESS events across 60 distinct ports for one IP
    must produce exactly one HIGH and one CRITICAL candidate in total.
    """
    original_interval = sys.getswitchinterval()
    sys.setswitchinterval(_FAST_SWITCH_INTERVAL)
    try:
        for attempt in range(_ATTEMPTS):
            detector = PortScanDetector()
            ip = "198.51.100.42"
            events = [
                make_event(
                    user_id="scanner",
                    event_type=EventType.PORT_ACCESS,
                    timestamp=BASE + timedelta(seconds=i * 0.01),
                    ip=ip,
                    port=i + 1,
                )
                for i in range(60)
            ]

            all_candidates = _fire_concurrently(events, lambda ev: detector.check(ev, db=None))

            severities = sorted(c.severity.name for c in all_candidates)
            assert severities == ["CRITICAL", "HIGH"], (
                f"attempt {attempt}: expected exactly one HIGH and one "
                f"CRITICAL — got {severities}"
            )
            assert all(c.alert_type == "port_scan" for c in all_candidates)
    finally:
        sys.setswitchinterval(original_interval)
