"""Thin async client for the Gemini REST API.

Kept deliberately dumb: prompt in, text out. All prompt engineering lives in
the feature services (tailoring.py, cover_letter.py) so swapping the LLM
provider later means changing only this file.
"""
import asyncio
import base64
import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """The LLM call failed or returned an unusable response."""


async def upload_file(data: bytes, mime_type: str, display_name: str = "upload") -> str:
    """Upload a file to Gemini's Files API and return its file_uri.

    inline_data (see generate()) embeds bytes directly in the request body
    as base64, which Google caps around ~20MB inline — fine for resumes/PDF
    text, not for lecture-length audio. The Files API is a separate
    upload-then-reference flow with a much higher ceiling. Files
    auto-expire on Google's side after 48h, so there's nothing to clean up
    here."""
    settings = get_settings()
    if not settings.llm_api_key:
        raise LLMError("LLM_API_KEY is not configured")

    upload_base = settings.llm_base_url.replace("/v1beta", "/upload/v1beta")
    timeout = httpx.Timeout(300.0, connect=15.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        start = await client.post(
            f"{upload_base}/files",
            headers={
                "x-goog-api-key": settings.llm_api_key,
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(len(data)),
                "X-Goog-Upload-Header-Content-Type": mime_type,
                "Content-Type": "application/json",
            },
            json={"file": {"display_name": display_name}},
        )
        if start.status_code != 200:
            logger.error("File upload init HTTP %s: %s", start.status_code, start.text[:500])
            raise LLMError(f"File upload init failed with HTTP {start.status_code}")
        upload_url = start.headers.get("x-goog-upload-url")
        if not upload_url:
            raise LLMError("File upload init did not return an upload URL")

        uploaded = await client.post(
            upload_url,
            headers={
                "Content-Length": str(len(data)),
                "X-Goog-Upload-Offset": "0",
                "X-Goog-Upload-Command": "upload, finalize",
            },
            content=data,
        )
        if uploaded.status_code != 200:
            logger.error("File upload HTTP %s: %s", uploaded.status_code, uploaded.text[:500])
            raise LLMError(f"File upload failed with HTTP {uploaded.status_code}")

        file_info = uploaded.json().get("file", {})
        file_uri = file_info.get("uri")
        file_name = file_info.get("name")
        state = file_info.get("state")
        if not file_uri or not file_name:
            raise LLMError("File upload returned an unexpected response shape")

        # Audio/video needs a moment to finish processing before it can be
        # referenced in a generateContent call.
        for _ in range(60):
            if state == "ACTIVE":
                return file_uri
            if state == "FAILED":
                raise LLMError("Gemini failed to process the uploaded file")
            await asyncio.sleep(1)
            status = await client.get(
                f"{settings.llm_base_url}/{file_name}",
                headers={"x-goog-api-key": settings.llm_api_key},
            )
            state = status.json().get("state")

    raise LLMError("Timed out waiting for Gemini to process the uploaded file")


_JSON_SAFE_ESCAPE_CHARS = set('"\\/')


def _escape_stray_backslashes(text: str) -> str:
    """Repair pass for a common failure mode: a model asked to embed LaTeX
    in a JSON string often forgets that JSON requires backslashes doubled
    (\\frac instead of the valid \\\\frac), making the whole response fail
    to parse. Double any backslash that isn't already part of a real JSON
    escape (\\", \\\\, \\/, \\uXXXX). Note this deliberately treats \\n/\\t/
    \\r/\\f/\\b as NOT valid here — callers of this repair path only ever
    contain single-line prose, never legitimate control characters, and
    those letters are common LaTeX command starts (\\tau, \\forall, ...)."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            nxt = text[i + 1]
            if nxt in _JSON_SAFE_ESCAPE_CHARS:
                out.append(text[i : i + 2])
                i += 2
                continue
            if nxt == "u" and i + 6 <= n and all(c in "0123456789abcdefABCDEF" for c in text[i + 2 : i + 6]):
                out.append(text[i : i + 6])
                i += 6
                continue
            out.append("\\\\")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


async def generate(
    prompt: str,
    *,
    system: str | None = None,
    json_mode: bool = False,
    temperature: float = 0.4,
    inline_data: tuple[bytes, str] | None = None,
    file_ref: tuple[str, str] | None = None,
    max_output_tokens: int | None = None,
    timeout_seconds: float = 240.0,
) -> str:
    """inline_data, if given, is (raw_bytes, mime_type) attached alongside
    the text prompt — e.g. a small audio clip for the model to listen to.
    file_ref, if given, is (file_uri, mime_type) from upload_file() — use
    this instead for anything too large for inline_data (~20MB)."""
    settings = get_settings()
    if not settings.llm_api_key:
        raise LLMError("LLM_API_KEY is not configured")

    model = settings.llm_audio_model if (inline_data or file_ref) else settings.llm_model
    url = f"{settings.llm_base_url}/models/{model}:generateContent"
    parts: list[dict[str, Any]] = [{"text": prompt}]
    if inline_data:
        data, mime_type = inline_data
        parts.append(
            {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(data).decode()}}
        )
    if file_ref:
        file_uri, mime_type = file_ref
        parts.append({"fileData": {"mimeType": mime_type, "fileUri": file_uri}})
    payload: dict[str, Any] = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": temperature},
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"
    if max_output_tokens:
        payload["generationConfig"]["maxOutputTokens"] = max_output_tokens

    # Big prompts (full resume + job description, JSON output) can take the
    # model a few minutes. One automatic retry on timeout/connection errors.
    timeout = httpx.Timeout(timeout_seconds, connect=15.0)
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

    body = response.json()
    try:
        candidate = body["candidates"][0]
        if candidate.get("finishReason") == "MAX_TOKENS":
            raise LLMError(
                "LLM response was cut off at the output token limit — "
                "try a shorter source or raise max_output_tokens"
            )
        return candidate["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise LLMError("LLM returned an unexpected response shape") from exc


async def generate_json(
    prompt: str,
    *,
    system: str | None = None,
    temperature: float = 0.4,
    inline_data: tuple[bytes, str] | None = None,
    file_ref: tuple[str, str] | None = None,
    max_output_tokens: int | None = None,
    timeout_seconds: float = 240.0,
) -> dict[str, Any]:
    """Generate with JSON output mode and parse the result."""
    text = await generate(
        prompt,
        system=system,
        json_mode=True,
        temperature=temperature,
        inline_data=inline_data,
        file_ref=file_ref,
        max_output_tokens=max_output_tokens,
        timeout_seconds=timeout_seconds,
    )
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: the model likely embedded LaTeX (or similar) with un-doubled
    # backslashes. Repair and retry once before giving up.
    try:
        return json.loads(_escape_stray_backslashes(text))
    except json.JSONDecodeError as exc:
        raise LLMError("LLM returned invalid JSON") from exc
