"""Thin HTTP boundary around Ollama's `/api/generate` endpoint.

This is deliberately the *only* place in the codebase that knows Ollama's
wire format. Everything above it (ExplainabilityEngine, ChatbotModule) just
calls ``generate(prompt, timeout)`` and gets text back or ``None``.

Boundary contract: this function never raises. Connection errors, timeouts,
non-200 responses, and malformed JSON envelopes are all caught here and
turned into a ``None`` return + a WARNING-level log line. Callers should
never need a try/except around this call — that's the whole point of having
a boundary function, and it's what makes the rest of the AI layer testable
without a real Ollama instance (mock this one function and every caller's
graceful-degradation path is exercised for free).

Uses ``httpx`` (already a project dependency) rather than Ollama's own
Python SDK, to keep the dependency footprint unchanged.
"""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


async def generate(prompt: str, timeout: float) -> str | None:
    """POST ``prompt`` to Ollama and return the generated text, or ``None``.

    Failure modes all collapse to the same ``None`` return — callers treat
    "Ollama is down", "Ollama timed out", and "Ollama sent garbage" as one
    case: try later, don't block on it now. No retry logic here (see
    ExplainabilityEngine/ChatbotModule module docstrings) — a TODO for
    retry-with-backoff belongs in a future phase, not this boundary.
    """
    settings = get_settings()
    url = f"{settings.OLLAMA_HOST.rstrip('/')}/api/generate"
    payload = {"model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
    except httpx.TimeoutException:
        logger.warning("Ollama request timed out after %.1fs (model=%s)", timeout, settings.OLLAMA_MODEL)
        return None
    except httpx.RequestError as exc:
        logger.warning("Ollama request failed: %s", exc)
        return None

    if response.status_code != 200:
        logger.warning(
            "Ollama returned non-200 status %s: %s", response.status_code, response.text[:500]
        )
        return None

    try:
        body = response.json()
    except ValueError:
        logger.warning("Ollama response was not valid JSON: %s", response.text[:500])
        return None

    text = body.get("response")
    if not isinstance(text, str):
        logger.warning("Ollama response envelope missing string 'response' field: %r", body)
        return None

    return text
