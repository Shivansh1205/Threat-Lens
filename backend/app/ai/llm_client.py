"""Provider-neutral OpenAI-compatible client for external model APIs."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


async def generate(prompt: str, timeout: float | None = None) -> str | None:
    """Generate from one legacy prompt without exposing its contents in logs."""

    settings = get_settings()
    return await _request(
        [
            {"role": "system", "content": "You are a concise security analyst."},
            {"role": "user", "content": prompt[: settings.LLM_MAX_CONTEXT_CHARS]},
        ],
        timeout=timeout,
    )


def build_grounded_messages(
    *,
    system_prompt: str,
    evidence: str,
    history: str,
    question: str,
    max_chars: int,
) -> list[dict[str, str]]:
    """Fit messages into a character budget while always preserving the question."""

    safe_question = question.strip()[:1000]
    system_budget = min(3000, max(1000, max_chars // 3))
    bounded_system = system_prompt.strip()[:system_budget]
    history_budget = min(2000, max(0, max_chars - len(bounded_system) - len(safe_question) - 512))
    bounded_history = history.strip()[:history_budget]
    fixed_size = len(bounded_system) + len(bounded_history) + len(safe_question)
    evidence_budget = max(0, max_chars - fixed_size - 192)
    bounded_evidence = evidence[:evidence_budget]
    return [
        {"role": "system", "content": bounded_system},
        {
            "role": "user",
            "content": f"<threatlens_evidence>\n{bounded_evidence}\n</threatlens_evidence>",
        },
        {"role": "user", "content": f"Conversation context (reference only):\n{bounded_history}"},
        {
            "role": "user",
            "content": f"ADMIN QUESTION (answer this exact question):\n{safe_question}",
        },
    ]


async def generate_grounded(
    *,
    system_prompt: str,
    evidence: str,
    history: str,
    question: str,
    timeout: float | None = None,
) -> str | None:
    settings = get_settings()
    messages = build_grounded_messages(
        system_prompt=system_prompt,
        evidence=evidence,
        history=history,
        question=question,
        max_chars=settings.LLM_MAX_CONTEXT_CHARS,
    )
    return await _request(messages, timeout=timeout)


async def _request(messages: list[dict[str, str]], timeout: float | None = None) -> str | None:
    """Call the configured OpenAI-compatible provider."""

    settings = get_settings()
    if not settings.LLM_API_KEY:
        logger.info("External LLM disabled: LLM_API_KEY is not configured")
        return None

    url = f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": settings.LLM_MAX_OUTPUT_TOKENS,
        "stream": False,
    }
    if "gpt-oss" in settings.LLM_MODEL.lower():
        # Keep reasoning from consuming the entire short completion budget.
        payload["reasoning_effort"] = "low"
    request_timeout = timeout or settings.LLM_TIMEOUT_SECONDS

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            for attempt in range(2):
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
                )
                if response.status_code == 429 and attempt == 0:
                    retry_after = getattr(response, "headers", {}).get("Retry-After", "1")
                    try:
                        delay = min(2.0, max(0.0, float(retry_after)))
                    except ValueError:
                        delay = 1.0
                    logger.info("External LLM rate limited; retrying once")
                    await asyncio.sleep(delay)
                    continue
                if response.status_code >= 500 and attempt == 0:
                    logger.info("External LLM server error; retrying once")
                    continue
                if response.status_code != 200:
                    logger.warning(
                        "External LLM returned status %s (provider=%s)",
                        response.status_code,
                        settings.LLM_PROVIDER,
                    )
                    return None

                try:
                    body = response.json()
                    content = body["choices"][0]["message"]["content"]
                except (ValueError, KeyError, IndexError, TypeError):
                    logger.warning("External LLM returned an invalid response envelope")
                    return None

                if not isinstance(content, str):
                    logger.warning("External LLM response content was not text")
                    return None
                if not content.strip():
                    if attempt == 0:
                        logger.info("External LLM returned empty text; retrying once")
                        continue
                    logger.warning("External LLM returned an empty response")
                    return None

                choice = body.get("choices", [{}])[0]
                usage = body.get("usage", {})
                logger.info(
                    "External LLM completed (provider=%s, model=%s, latency_ms=%d, "
                    "finish_reason=%s, prompt_tokens=%s, completion_tokens=%s)",
                    settings.LLM_PROVIDER,
                    settings.LLM_MODEL,
                    int((time.perf_counter() - started) * 1000),
                    choice.get("finish_reason"),
                    usage.get("prompt_tokens"),
                    usage.get("completion_tokens"),
                )
                return content[: settings.LLM_MAX_OUTPUT_TOKENS * 8]
    except httpx.TimeoutException:
        logger.warning(
            "External LLM request timed out (provider=%s, model=%s)",
            settings.LLM_PROVIDER,
            settings.LLM_MODEL,
        )
        return None
    except httpx.RequestError as exc:
        logger.warning("External LLM request failed (provider=%s): %s", settings.LLM_PROVIDER, exc)
        return None
    return None
