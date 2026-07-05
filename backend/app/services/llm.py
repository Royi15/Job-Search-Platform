"""Thin async client for the Gemini REST API.

Kept deliberately dumb: prompt in, text out. All prompt engineering lives in
the feature services (tailoring.py, cover_letter.py) so swapping the LLM
provider later means changing only this file.
"""
import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """The LLM call failed or returned an unusable response."""


async def generate(
    prompt: str,
    *,
    system: str | None = None,
    json_mode: bool = False,
    temperature: float = 0.4,
) -> str:
    settings = get_settings()
    if not settings.llm_api_key:
        raise LLMError("LLM_API_KEY is not configured")

    url = f"{settings.llm_base_url}/models/{settings.llm_model}:generateContent"
    payload: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    # Big prompts (full resume + job description, JSON output) can take the
    # model a few minutes. One automatic retry on timeout/connection errors.
    timeout = httpx.Timeout(240.0, connect=15.0)
    response = None
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    url, json=payload, headers={"x-goog-api-key": settings.llm_api_key}
                )
            break
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if attempt == 2:
                raise LLMError(f"LLM request failed twice: {type(exc).__name__}") from exc
            logger.warning("LLM request %s — retrying once", type(exc).__name__)

    if response.status_code != 200:
        logger.error("LLM HTTP %s: %s", response.status_code, response.text[:500])
        raise LLMError(f"LLM request failed with HTTP {response.status_code}")

    try:
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise LLMError("LLM returned an unexpected response shape") from exc


async def generate_json(
    prompt: str, *, system: str | None = None, temperature: float = 0.4
) -> dict[str, Any]:
    """Generate with JSON output mode and parse the result."""
    text = await generate(
        prompt, system=system, json_mode=True, temperature=temperature
    )
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError("LLM returned invalid JSON") from exc
