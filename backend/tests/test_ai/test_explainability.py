"""Tests for ExplainabilityEngine — all Ollama calls mocked at the
``app.ai.ollama_client.generate`` boundary. No real Ollama involved.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.ai.explainability import ExplainabilityEngine
from app.models.alert import Alert
from app.models.behavior_profile import BehaviorProfile
from app.models.log_event import LogEvent
from app.models.user import User
from app.schemas.common import EventType, Severity

BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

VALID_RESPONSE = """EXPLANATION: This user triggered a brute-force alert that was escalated because their recent behavior deviates sharply from their established baseline, including logins from unfamiliar IPs.
MITIGATION:
- block IP: the source IP is not associated with this user's normal activity
- force password reset: repeated failures suggest credential compromise
- review recent account activity: confirm no unauthorized access occurred
"""

GARBAGE_RESPONSE = "Sure! Here's my analysis of the situation, hope it helps you out today."


def _seed_alert(
    db_session: Session,
    *,
    deviation_score: float = 0.8,
    raw_score: int = 45,
    score: int = 62,
    raw_severity: Severity = Severity.MEDIUM,
    severity: Severity = Severity.HIGH,
) -> Alert:
    db_session.add(User(user_id="mallory", first_seen_at=BASE, last_seen_at=BASE))
    event = LogEvent(
        id=uuid4(),
        user_id="mallory",
        ip="10.0.0.99",
        timestamp=BASE,
        event_type=EventType.LOGIN_FAILURE,
        status="bad_password",
        raw_json={},
    )
    db_session.add(event)
    db_session.add(
        BehaviorProfile(
            user_id="mallory",
            known_ips=["10.0.0.1"],
            login_count=7,
            deviation_score=deviation_score,
            user_risk_score=41.5,
        )
    )
    db_session.flush()

    alert = Alert(
        user_id="mallory",
        alert_type="brute_force",
        severity=severity,
        score=score,
        raw_severity=raw_severity,
        raw_score=raw_score,
        message="5 failed logins for mallory within the sliding window.",
        triggered_by_event_id=event.id,
    )
    db_session.add(alert)
    db_session.commit()
    return alert


# --------------------------------------------------------------------- explain


@pytest.mark.anyio
async def test_explain_valid_response_updates_alert(db_session: Session) -> None:
    alert = _seed_alert(db_session)
    engine = ExplainabilityEngine(db_session)

    with patch("app.ai.ollama_client.generate", new=AsyncMock(return_value=VALID_RESPONSE)):
        await engine.explain(alert.id)

    db_session.refresh(alert)
    assert alert.explanation is not None
    assert "brute-force" in alert.explanation or "deviat" in alert.explanation
    assert alert.mitigation_steps is not None
    actions = {step["action"] for step in alert.mitigation_steps}
    assert actions == {"block IP", "force password reset", "review recent account activity"}
    for step in alert.mitigation_steps:
        assert step["justification"]  # non-empty


@pytest.mark.anyio
async def test_explain_ollama_unavailable_leaves_fields_null(db_session: Session) -> None:
    alert = _seed_alert(db_session)
    engine = ExplainabilityEngine(db_session)

    with patch("app.ai.ollama_client.generate", new=AsyncMock(return_value=None)):
        await engine.explain(alert.id)  # must not raise

    db_session.refresh(alert)
    assert alert.explanation is None
    assert alert.mitigation_steps is None


@pytest.mark.anyio
async def test_explain_unparseable_response_leaves_fields_null(
    db_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    alert = _seed_alert(db_session)
    engine = ExplainabilityEngine(db_session)

    with patch("app.ai.ollama_client.generate", new=AsyncMock(return_value=GARBAGE_RESPONSE)):
        with caplog.at_level("WARNING"):
            await engine.explain(alert.id)  # must not raise

    db_session.refresh(alert)
    assert alert.explanation is None
    assert alert.mitigation_steps is None
    assert any("Could not parse" in r.message for r in caplog.records)


@pytest.mark.anyio
async def test_explain_response_with_no_valid_mitigation_items_leaves_fields_null(
    db_session: Session,
) -> None:
    """A response with proper markers but zero recognizable vocabulary items
    must still be rejected — accepting it would store unconstrained,
    potentially hallucinated mitigation text (D3).
    """
    alert = _seed_alert(db_session)
    engine = ExplainabilityEngine(db_session)
    bad_response = "EXPLANATION: something happened.\nMITIGATION:\n- launch a counter-hack\n"

    with patch("app.ai.ollama_client.generate", new=AsyncMock(return_value=bad_response)):
        await engine.explain(alert.id)

    db_session.refresh(alert)
    assert alert.explanation is None
    assert alert.mitigation_steps is None


@pytest.mark.anyio
async def test_explain_missing_alert_does_not_raise(db_session: Session) -> None:
    engine = ExplainabilityEngine(db_session)
    with patch("app.ai.ollama_client.generate", new=AsyncMock(return_value=VALID_RESPONSE)):
        await engine.explain(uuid4())  # no such alert — must not raise


# ----------------------------------------------------------------- build_prompt


def test_build_prompt_includes_key_fields(db_session: Session) -> None:
    alert = _seed_alert(db_session, deviation_score=0.8, raw_score=45, score=62)
    engine = ExplainabilityEngine(db_session)
    event = db_session.query(LogEvent).filter(LogEvent.id == alert.triggered_by_event_id).one()
    profile = db_session.query(BehaviorProfile).filter(BehaviorProfile.user_id == "mallory").one()

    prompt = engine.build_prompt(alert, event, profile)

    assert "brute_force" in prompt
    assert "45" in prompt  # raw_score
    assert "62" in prompt  # adjusted score
    assert "0.80" in prompt  # deviation_score
    assert "41.5" in prompt  # user_risk_score
    assert "7" in prompt  # login_count
    assert "10.0.0.99" in prompt  # event ip
    assert "LOGIN_FAILURE" in prompt
    assert "block IP" in prompt  # vocabulary present in prompt


def test_build_prompt_notes_when_score_unchanged(db_session: Session) -> None:
    alert = _seed_alert(
        db_session,
        deviation_score=0.0,
        raw_score=45,
        score=45,
        raw_severity=Severity.MEDIUM,
        severity=Severity.MEDIUM,
    )
    engine = ExplainabilityEngine(db_session)
    event = db_session.query(LogEvent).filter(LogEvent.id == alert.triggered_by_event_id).one()
    profile = db_session.query(BehaviorProfile).filter(BehaviorProfile.user_id == "mallory").one()

    prompt = engine.build_prompt(alert, event, profile)

    assert "matches the detector's original call exactly" in prompt
