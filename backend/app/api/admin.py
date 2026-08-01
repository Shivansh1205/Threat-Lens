"""Admin/dev convenience endpoints.

NOT auth-gated — this project has no authentication yet (Phase 7 future
work, see PHASES.md). ``POST /admin/decay-now`` is deliberately simple: a
thin HTTP wrapper around ``run_decay_pass()`` for testing and for
demonstrating time-based risk decay live during a project review, since
waiting a real 24h interval mid-demo isn't an option.

Before any real deployment, this router should be auth-gated (admin-only)
or removed entirely — it lets any caller force a DB write pass over every
user's risk score with no rate limiting or access control.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.decay import DecaySummary
from app.scoring.decay_job import run_decay_pass

router = APIRouter(tags=["admin"])


@router.post("/admin/decay-now", response_model=DecaySummary)
def decay_now(db: Session = Depends(get_db)) -> DecaySummary:
    """Run one time-based risk-decay pass synchronously and return a summary.

    Reuses ``run_decay_pass`` directly — the same function the scheduled job
    calls (see main.py's lifespan handler) — rather than duplicating the
    decay logic here. ``run_decay_pass`` only flushes; this endpoint owns
    the commit, matching the request-scoped-session pattern used by every
    other endpoint in this codebase.
    """
    summary = run_decay_pass(db)
    db.commit()
    return DecaySummary(**summary)
