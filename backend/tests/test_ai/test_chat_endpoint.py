"""Tests for POST /api/v1/chat — Ollama calls mocked, no real Ollama involved."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def test_chat_endpoint_returns_mocked_response(client: TestClient) -> None:
    with patch("app.ai.ollama_client.generate", new=AsyncMock(return_value="Nothing alarming today.")):
        resp = client.post(
            "/api/v1/chat", json={"session_id": "s1", "message": "Anything I should worry about?"}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"response": "Nothing alarming today."}


def test_chat_endpoint_ollama_down_returns_fallback(client: TestClient) -> None:
    with patch("app.ai.ollama_client.generate", new=AsyncMock(return_value=None)):
        resp = client.post("/api/v1/chat", json={"session_id": "s2", "message": "Status update?"})

    assert resp.status_code == 200
    assert "unable to reach the AI assistant" in resp.json()["response"]


def test_chat_endpoint_missing_session_id_returns_422(client: TestClient) -> None:
    resp = client.post("/api/v1/chat", json={"message": "hello"})

    assert resp.status_code == 422


def test_chat_endpoint_missing_message_returns_422(client: TestClient) -> None:
    resp = client.post("/api/v1/chat", json={"session_id": "s3"})

    assert resp.status_code == 422
