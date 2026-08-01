"""FastAPI application entrypoint.

Mounts the REST routers under ``/api/v1`` and the WebSocket alert-push route
at the app root (``/ws/alerts`` — see app/api/websocket.py for why it isn't
versioned the same way). The lifespan handler below captures the app's main
asyncio event loop into the WebSocketManager singleton at startup — that's
what lets the (sync) ``POST /api/v1/log`` endpoint, running on Starlette's
threadpool, safely hand a broadcast back to the loop that actually owns the
live WebSocket connections (see app/realtime/websocket_manager.py's
``schedule_broadcast`` docstring for the full reasoning). The same lifespan
handler also starts/stops an in-process APScheduler that runs the
time-based risk-decay job (see app/scoring/decay_job.py) — chosen over a
real task queue (Celery/arq) as infrastructure overkill for this project's
single-process deployment; APScheduler is a lightweight, in-process
scheduling library that integrates directly with this same async lifespan.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, alerts, chat, logs, users, websocket
from app.config import get_settings
from app.database import SessionLocal
from app.realtime.websocket_manager import get_ws_manager
from app.scoring.decay_job import run_decay_pass

logger = logging.getLogger(__name__)

settings = get_settings()

# Session factory for the scheduled/startup decay pass, which is NOT
# request-scoped and so can't go through FastAPI's `Depends(get_db)`
# machinery the way endpoint handlers do (see app/ai/explainability.py's
# generate_explanation_task for the same "background code needs its own
# session factory" situation). Kept as a module-level name — rather than
# captured as a local inside the lifespan closure — specifically so tests
# can monkeypatch `app.main._decay_db_session_factory` to the test DB's
# sessionmaker BEFORE the TestClient triggers lifespan startup (see
# tests/conftest.py's `client` fixture). Without this indirection, every
# test that spins up a TestClient would otherwise open a real connection to
# the configured DATABASE_URL (Postgres) on startup and on every scheduled
# tick — exactly what this feature's test constraints rule out.
_decay_db_session_factory = SessionLocal


def _run_decay_job() -> None:
    """Scheduler/startup entry point: own session in, commit, close.

    Mirrors generate_explanation_task's session-factory pattern for the same
    reason — this isn't tied to any HTTP request, so it can't reuse a
    request-scoped session. Reads `_decay_db_session_factory` as a module
    global (not a captured parameter) so a test's monkeypatch takes effect
    on every call, including ones the scheduler itself makes later. Never
    lets an exception escape: a failed decay pass must not crash the
    scheduler's executor thread, or (for the startup call) app startup
    itself.
    """
    db = _decay_db_session_factory()
    try:
        summary = run_decay_pass(db, settings)
        db.commit()
        logger.info(
            "Risk-decay pass complete: profiles_processed=%d profiles_decayed=%d "
            "total_score_removed=%.4f",
            summary["profiles_processed"],
            summary["profiles_decayed"],
            summary["total_score_removed"],
        )
    except Exception:  # noqa: BLE001 - scheduler/startup boundary, must never raise
        db.rollback()
        logger.exception("Risk-decay pass failed")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Runs on the loop uvicorn actually serves requests on. Async endpoints
    # (like the /ws/alerts websocket route) and this lifespan handler run
    # directly on this loop; sync endpoints run on a threadpool that hands
    # work back to this same loop via schedule_broadcast().
    get_ws_manager().set_loop(asyncio.get_running_loop())

    # Time-based user_risk_score decay (see app/scoring/decay_job.py).
    # Interval trigger rather than a fixed wall-clock time (e.g. "run at
    # 03:00") — simpler, avoids timezone questions, adequate at this
    # project's scale. A production deployment would likely prefer a fixed
    # low-traffic hour instead of a rolling interval, so restarts don't
    # drift the schedule.
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_decay_job,
        "interval",
        hours=settings.DECAY_JOB_INTERVAL_HOURS,
        id="risk_score_decay",
    )
    scheduler.start()
    # Also run once immediately on startup — decay shouldn't be purely
    # theoretical if the server restarts frequently during development/demo,
    # and this gives something to observe without waiting a full interval.
    _run_decay_job()

    try:
        yield
    finally:
        # wait=False: don't block app shutdown on any in-flight decay pass —
        # this is a best-effort background job, not something a shutting-
        # down server needs to wait on. Verified directly (not assumed) that
        # this doesn't leave a hung process: APScheduler's default
        # ThreadPoolExecutor-backed executor may show a transient idle
        # worker thread for a brief moment after shutdown (standard
        # behavior of Python's stdlib ThreadPoolExecutor, which lets idle
        # workers self-terminate rather than requiring instant teardown),
        # but this does not block interpreter/process exit.
        scheduler.shutdown(wait=False)


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# Must be added before the app starts handling requests so every response
# (including error responses) gets CORS headers — added right after app
# creation, before router inclusion. Starlette's middleware stack is order
# sensitive for *multiple* middlewares (each wraps the next), but with only
# one middleware here, and add_middleware() building the stack lazily on
# first request regardless of include_router() call order, this could also
# safely go after the routers; it's placed first anyway as the conventional,
# least-surprising spot.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(logs.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(websocket.router)  # /ws/alerts — no /api/v1 prefix, see module docstring


@app.get("/health")
def health_check() -> dict[str, str]:
    """Liveness check. Returns a static ok — no dependency checks yet."""
    return {"status": "ok"}
