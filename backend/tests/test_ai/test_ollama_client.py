"""Tests for the Ollama HTTP boundary function — no real Ollama involved.

Mocks ``httpx.AsyncClient`` itself (one level below ``generate()``) rather
than ``generate()``, since this is the one module that's actually
responsible for talking to Ollama's wire format. A hand-written fake client
(rather than ``unittest.mock.MagicMock``) sidesteps the usual headaches of
mocking Python's async-context-manager dunder methods.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.ai import llm_client
from app.config import get_settings


class _FakeResponse:
    def __init__(
        self, status_code: int = 200, json_data=None, text: str = "", headers=None
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.headers = headers or {}

    def json(self):
        if self._json_data is _MALFORMED:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._json_data


_MALFORMED = object()


class _FakeAsyncClient:
    """Stands in for ``httpx.AsyncClient`` as an async context manager."""

    def __init__(
        self,
        response: _FakeResponse | None = None,
        raise_exc: Exception | None = None,
        responses: list[_FakeResponse] | None = None,
    ):
        self._response = response
        self._raise_exc = raise_exc
        self._responses = list(responses or [])
        self.last_json = None

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def post(self, url, json=None, headers=None):
        if self._raise_exc is not None:
            raise self._raise_exc
        self.last_json = json
        if self._responses:
            return self._responses.pop(0)
        return self._response


def _patch_client(**kwargs):
    """Patch ``httpx.AsyncClient`` (as used inside llm_client) to ignore
    its constructor args and always return a preconfigured fake client.
    """
    fake = _FakeAsyncClient(**kwargs)
    return patch("app.ai.llm_client.httpx.AsyncClient", return_value=fake)


@pytest.mark.anyio
async def test_generate_success() -> None:
    """A well-formed 200 response returns the 'response' text field."""
    response = _FakeResponse(
        200, {"choices": [{"message": {"content": "this alert looks like a brute-force attempt"}}]}
    )
    with _patch_client(response=response), patch.object(get_settings(), "LLM_API_KEY", "test-key"):
        result = await llm_client.generate("some prompt", timeout=5.0)

    assert result == "this alert looks like a brute-force attempt"


@pytest.mark.anyio
async def test_generate_connection_error_returns_none() -> None:
    """A connection error (Ollama not running) must return None, not raise."""
    with (
        _patch_client(raise_exc=httpx.ConnectError("connection refused")),
        patch.object(get_settings(), "LLM_API_KEY", "test-key"),
    ):
        result = await llm_client.generate("some prompt", timeout=5.0)

    assert result is None


@pytest.mark.anyio
async def test_generate_timeout_returns_none() -> None:
    """A timeout must return None within the configured timeout, not raise
    and not hang.
    """
    with (
        _patch_client(raise_exc=httpx.TimeoutException("timed out")),
        patch.object(get_settings(), "LLM_API_KEY", "test-key"),
    ):
        result = await llm_client.generate("some prompt", timeout=5.0)

    assert result is None


@pytest.mark.anyio
async def test_generate_malformed_json_returns_none() -> None:
    """A 200 response whose body isn't valid JSON must return None, not raise."""
    response = _FakeResponse(200, _MALFORMED, text="not json at all")
    with _patch_client(response=response), patch.object(get_settings(), "LLM_API_KEY", "test-key"):
        result = await llm_client.generate("some prompt", timeout=5.0)

    assert result is None


@pytest.mark.anyio
async def test_generate_non_200_returns_none() -> None:
    response = _FakeResponse(500, text="internal server error")
    with _patch_client(response=response), patch.object(get_settings(), "LLM_API_KEY", "test-key"):
        result = await llm_client.generate("some prompt", timeout=5.0)

    assert result is None


@pytest.mark.anyio
async def test_generate_missing_response_field_returns_none() -> None:
    """A 200 with valid JSON but no 'response' string field must return None."""
    response = _FakeResponse(200, {"unexpected": "shape"})
    with _patch_client(response=response), patch.object(get_settings(), "LLM_API_KEY", "test-key"):
        result = await llm_client.generate("some prompt", timeout=5.0)

    assert result is None


@pytest.mark.anyio
async def test_generate_retries_rate_limit_once() -> None:
    limited = _FakeResponse(429, text="rate limited", headers={"Retry-After": "0"})
    success = _FakeResponse(200, {"choices": [{"message": {"content": "grounded"}}]})
    with (
        _patch_client(responses=[limited, success]),
        patch.object(get_settings(), "LLM_API_KEY", "test-key"),
    ):
        result = await llm_client.generate("some prompt", timeout=5.0)

    assert result == "grounded"


@pytest.mark.anyio
async def test_generate_retries_empty_content_once() -> None:
    empty = _FakeResponse(200, {"choices": [{"message": {"content": ""}}]})
    success = _FakeResponse(200, {"choices": [{"message": {"content": "complete"}}]})
    with (
        _patch_client(responses=[empty, success]),
        patch.object(get_settings(), "LLM_API_KEY", "test-key"),
    ):
        result = await llm_client.generate("some prompt", timeout=5.0)

    assert result == "complete"


@pytest.mark.anyio
async def test_gpt_oss_uses_low_reasoning_effort() -> None:
    response = _FakeResponse(200, {"choices": [{"message": {"content": "complete"}}]})
    fake = _FakeAsyncClient(response=response)
    with (
        patch("app.ai.llm_client.httpx.AsyncClient", return_value=fake),
        patch.object(get_settings(), "LLM_API_KEY", "test-key"),
        patch.object(get_settings(), "LLM_MODEL", "openai/gpt-oss-20b"),
    ):
        await llm_client.generate("some prompt", timeout=5.0)

    assert fake.last_json["reasoning_effort"] == "low"
