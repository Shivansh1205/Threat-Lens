"""Tests for ChatbotModule — all Ollama calls mocked. No real Ollama involved."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import Session

from app.ai.chatbot import MAX_HISTORY_EXCHANGES, ChatbotModule
from app.models.alert import Alert
from app.models.user import User
from app.schemas.common import Severity

BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _seed_alert(db_session: Session, user_id: str, alert_type: str = "brute_force") -> None:
    if db_session.query(User).filter(User.user_id == user_id).one_or_none() is None:
        db_session.add(User(user_id=user_id, first_seen_at=BASE, last_seen_at=BASE))
    db_session.add(
        Alert(
            user_id=user_id,
            alert_type=alert_type,
            severity=Severity.HIGH,
            score=62,
            raw_severity=Severity.MEDIUM,
            raw_score=45,
            message=f"test alert for {user_id}",
        )
    )
    db_session.commit()


# --------------------------------------------------------------- build_context


def test_build_context_no_user_id_includes_general_alerts(db_session: Session) -> None:
    _seed_alert(db_session, "alice")
    _seed_alert(db_session, "bob")
    bot = ChatbotModule()

    context = bot.build_context(db_session, user_id=None, limit=20)

    assert "alice" in context
    assert "bob" in context


def test_build_context_with_user_id_filters(db_session: Session) -> None:
    _seed_alert(db_session, "alice")
    _seed_alert(db_session, "bob")
    bot = ChatbotModule()

    context = bot.build_context(db_session, user_id="alice", limit=20)

    assert "user=alice" in context
    assert "user=bob" not in context


def test_build_context_empty_db(db_session: Session) -> None:
    bot = ChatbotModule()

    context = bot.build_context(db_session, user_id=None, limit=20)

    assert "No recent alerts" in context


# --------------------------------------------------------------- handle_query


@pytest.mark.anyio
async def test_handle_query_returns_mocked_response_and_updates_history(
    db_session: Session,
) -> None:
    bot = ChatbotModule()
    with patch("app.ai.ollama_client.generate", new=AsyncMock(return_value="Here's my answer.")):
        result = await bot.handle_query("session-1", "What happened recently?", db_session)

    assert result == "Here's my answer."
    history = bot._get_history("session-1")
    assert len(history) == 1
    assert history[0]["user"] == "What happened recently?"
    assert history[0]["assistant"] == "Here's my answer."


@pytest.mark.anyio
async def test_handle_query_ollama_down_returns_honest_fallback(db_session: Session) -> None:
    bot = ChatbotModule()
    with patch("app.ai.ollama_client.generate", new=AsyncMock(return_value=None)):
        result = await bot.handle_query("session-2", "Anything suspicious?", db_session)

    assert "unable to reach the AI assistant" in result
    # A failed exchange isn't recorded as real conversation history.
    assert bot._get_history("session-2") == []


@pytest.mark.anyio
async def test_handle_query_detects_mentioned_user_id(db_session: Session) -> None:
    _seed_alert(db_session, "carol")
    _seed_alert(db_session, "dave")
    bot = ChatbotModule()

    captured_prompts = []

    async def _fake_generate(prompt, timeout):
        captured_prompts.append(prompt)
        return "ok"

    with patch("app.ai.ollama_client.generate", new=_fake_generate):
        await bot.handle_query("session-3", "What's going on with carol lately?", db_session)

    assert "user=carol" in captured_prompts[0]
    assert "user=dave" not in captured_prompts[0]


@pytest.mark.anyio
async def test_conversation_history_caps_at_n_exchanges(db_session: Session) -> None:
    bot = ChatbotModule()
    session_id = "session-4"

    async def _fake_generate(prompt, timeout):
        return "reply"

    with patch("app.ai.ollama_client.generate", new=_fake_generate):
        for i in range(MAX_HISTORY_EXCHANGES + 5):
            await bot.handle_query(session_id, f"message {i}", db_session)

    history = bot._get_history(session_id)
    assert len(history) == MAX_HISTORY_EXCHANGES
    # Oldest exchanges dropped — the earliest surviving one is message 5,
    # not message 0.
    first_surviving_index = (MAX_HISTORY_EXCHANGES + 5) - MAX_HISTORY_EXCHANGES
    assert history[0]["user"] == f"message {first_surviving_index}"
    assert history[-1]["user"] == f"message {MAX_HISTORY_EXCHANGES + 4}"
