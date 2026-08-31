from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.ai.admin_query import (
    build_evidence_pack,
    constrain_grounded_response,
    direct_fact_answer,
    plan_admin_query,
)
from app.ai.llm_client import build_grounded_messages
from app.models.alert import Alert
from app.models.behavior_profile import BehaviorProfile
from app.models.log_event import LogEvent
from app.models.user import User
from app.schemas.common import EventType, Severity

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def _seed_activity(db: Session) -> None:
    db.add_all(
        [
            User(user_id="alice", first_seen_at=NOW - timedelta(days=10), last_seen_at=NOW),
            User(user_id="bob", first_seen_at=NOW - timedelta(days=10), last_seen_at=NOW),
        ]
    )
    db.flush()
    event = LogEvent(
        user_id="alice",
        ip="203.0.113.10",
        timestamp=NOW - timedelta(hours=2),
        event_type=EventType.LOGIN_FAILURE,
        status="failure",
        source_id="portal",
        event_metadata={"token": "must-not-leak", "attempt": 7},
        raw_json={"password": "also-must-not-leak"},
    )
    db.add(event)
    db.flush()
    db.add_all(
        [
            BehaviorProfile(user_id="alice", user_risk_score=91, deviation_score=0.8),
            BehaviorProfile(user_id="bob", user_risk_score=10, deviation_score=0.1),
            Alert(
                user_id="alice",
                alert_type="brute_force",
                severity=Severity.CRITICAL,
                score=91,
                raw_severity=Severity.HIGH,
                raw_score=70,
                message="failed login threshold reached",
                evidence={"authorization": "secret", "count": 7},
                triggered_by_event_id=event.id,
                created_at=NOW - timedelta(hours=2),
            ),
            Alert(
                user_id="bob",
                alert_type="path_probe",
                severity=Severity.HIGH,
                score=70,
                raw_severity=Severity.HIGH,
                raw_score=70,
                message="old alert",
                created_at=NOW - timedelta(days=3),
            ),
        ]
    )
    db.commit()


def test_query_planner_extracts_entities_filters_and_default_window(db_session: Session) -> None:
    _seed_activity(db_session)
    scope, clarification = plan_admin_query(
        db_session,
        "Show unresolved critical brute force alerts for alice",
        now=NOW,
    )

    assert clarification is None
    assert scope is not None
    assert scope.user_ids == ("alice",)
    assert scope.severities == ("CRITICAL",)
    assert scope.alert_types == ("brute_force",)
    assert scope.resolved is False
    assert scope.start == NOW - timedelta(hours=24)
    assert scope.end == NOW


def test_query_planner_does_not_match_user_id_as_substring(db_session: Session) -> None:
    db_session.add(User(user_id="al", first_seen_at=NOW, last_seen_at=NOW))
    db_session.commit()

    scope, clarification = plan_admin_query(db_session, "Show all alerts", now=NOW)

    assert clarification is None
    assert scope is not None
    assert scope.user_ids == ()


def test_query_planner_clarifies_unknown_user_with_close_match(db_session: Session) -> None:
    _seed_activity(db_session)

    scope, clarification = plan_admin_query(db_session, "What happened with alise?", now=NOW)

    assert scope is None
    assert clarification is not None
    assert "alice" in clarification


def test_query_planner_does_not_treat_filter_words_as_usernames(db_session: Session) -> None:
    _seed_activity(db_session)

    scope, clarification = plan_admin_query(
        db_session, "Show critical alerts for last week", now=NOW
    )

    assert clarification is None
    assert scope is not None
    assert scope.user_ids == ()
    assert scope.severities == ("CRITICAL",)


def test_follow_up_inherits_time_and_replaces_user(db_session: Session) -> None:
    _seed_activity(db_session)
    first, _ = plan_admin_query(db_session, "Show alice alerts last 7 days", now=NOW)
    assert first is not None

    second, clarification = plan_admin_query(db_session, "What about bob?", first, now=NOW)

    assert clarification is None
    assert second is not None
    assert second.user_ids == ("bob",)
    assert second.start == first.start
    assert second.end == first.end


def test_evidence_pack_uses_exact_database_counts_and_redacts_secrets(db_session: Session) -> None:
    _seed_activity(db_session)
    scope, _ = plan_admin_query(db_session, "Analyze alice login events today", now=NOW)
    assert scope is not None

    pack = build_evidence_pack(db_session, scope, max_chars=8000)

    assert pack.alert_count == 1
    assert pack.event_count == 1
    assert pack.facts["alerts_by_type"] == {"brute_force": 1}
    assert "must-not-leak" not in pack.context
    assert '"token":"[REDACTED]"' in pack.context
    assert '"authorization":"[REDACTED]"' in pack.context
    assert pack.references


def test_simple_count_answer_is_local_and_traceable(db_session: Session) -> None:
    _seed_activity(db_session)
    scope, _ = plan_admin_query(db_session, "How many critical alerts for alice?", now=NOW)
    assert scope is not None
    pack = build_evidence_pack(db_session, scope, max_chars=8000)

    assert direct_fact_answer("How many critical alerts for alice?", pack) == (
        "There are 1 matching alerts, including 1 unresolved alerts."
    )


def test_processing_role_answer_is_local_and_exact(db_session: Session) -> None:
    _seed_activity(db_session)
    scope, _ = plan_admin_query(db_session, "Who analyzes attacks and when is Groq used?", now=NOW)
    assert scope is not None
    pack = build_evidence_pack(db_session, scope, max_chars=8000)

    answer = direct_fact_answer("Who analyzes attacks and when is Groq used?", pack)

    assert answer is not None
    assert "local rule detectors" in answer
    assert "authenticated administrator" in answer


def test_failed_login_count_filters_event_type(db_session: Session) -> None:
    _seed_activity(db_session)
    scope, _ = plan_admin_query(
        db_session, "How many failed login events for alice today?", now=NOW
    )
    assert scope is not None
    assert scope.event_types == ("LOGIN_FAILURE",)

    pack = build_evidence_pack(db_session, scope, max_chars=8000)

    assert pack.event_count == 1
    assert pack.facts["events_by_type"] == {"LOGIN_FAILURE": 1}


def test_exact_record_id_is_retrieved_outside_default_window(db_session: Session) -> None:
    _seed_activity(db_session)
    old_alert = db_session.query(Alert).filter(Alert.user_id == "bob").one()

    scope, _ = plan_admin_query(db_session, f"Explain alert {old_alert.id}", now=NOW)
    assert scope is not None
    pack = build_evidence_pack(db_session, scope, max_chars=8000)

    assert pack.alert_count == 1
    assert str(old_alert.id) in pack.context


def test_trend_context_compares_previous_equal_period(db_session: Session) -> None:
    _seed_activity(db_session)
    scope, _ = plan_admin_query(
        db_session, "Are alerts increasing compared with the previous day?", now=NOW
    )
    assert scope is not None

    pack = build_evidence_pack(db_session, scope, max_chars=8000)

    assert pack.facts["previous_alert_count"] == 0
    assert "alert_change=1" in pack.context


def test_message_budget_never_truncates_final_admin_question() -> None:
    question = "Explain alice's critical alerts and compare them with bob."
    messages = build_grounded_messages(
        system_prompt="system rules " * 1000,
        evidence="evidence record\n" * 2000,
        history="old conversation\n" * 1000,
        question=question,
        max_chars=4000,
    )

    assert question in messages[-1]["content"]
    assert sum(len(message["content"]) for message in messages) <= 4000


def test_response_constraint_removes_unsolicited_actions_and_caps_bullets() -> None:
    response = "\n".join(
        [
            "- fact one",
            "- fact two",
            "- fact three",
            "- fact four",
            "- fact five",
            "- fact six",
            "- Recommended mitigation: lock the account",
        ]
    )

    constrained = constrain_grounded_response(response, ())

    assert "fact five" in constrained
    assert "fact six" not in constrained
    assert "lock the account" not in constrained


def test_response_constraint_accepts_only_applicable_mitigation_vocabulary() -> None:
    response = "\n".join(
        [
            "- temporarily lock account: stop credential abuse",
            "- delete the user: invented action",
            "- block the IP: not allowed for this evidence",
        ]
    )

    constrained = constrain_grounded_response(response, ("temporarily lock account",))

    assert "temporarily lock account" in constrained
    assert "delete the user" not in constrained
    assert "block the IP" not in constrained
