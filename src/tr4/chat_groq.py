"""Groq chat completion (OpenAI-compatible API). No GPU needed."""

from __future__ import annotations

import asyncio

import httpx

from tr4.config import Settings

# Free-tier per-minute token limits are shared across the whole API key, not
# per-user — a couple of concurrent real /chat calls (system prompt + several
# retrieved chunks easily reaches 1.5-2.5k input tokens each) can trip a low
# cap (seen as low as 6000 tokens/min on llama-3.1-8b-instant). One bounded
# retry, waiting for the window the response tells us about, turns a
# transient 429 into a slower answer instead of a hard error.
_MAX_RETRY_WAIT_SECONDS = 30.0


def _retry_wait_seconds(resp: httpx.Response) -> float:
    for header in ("retry-after", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
        value = resp.headers.get(header)
        if not value:
            continue
        try:
            return min(float(value.rstrip("s")), _MAX_RETRY_WAIT_SECONDS)
        except ValueError:
            continue
    return 5.0


async def chat_complete(
    messages: list[dict[str, str]],
    settings: Settings,
    *,
    max_tokens: int | None = None,
) -> tuple[str, dict[str, int]]:
    """Returns (reply, usage) where usage = {"prompt_tokens", "completion_tokens"}."""
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY não configurada.")

    base = settings.groq_base_url.rstrip("/")
    url = f"{base}/chat/completions"
    payload = {
        "model": settings.groq_chat_model,
        "messages": messages,
        "max_tokens": max_tokens or settings.max_tokens_per_reply,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code == 429:
            await asyncio.sleep(_retry_wait_seconds(resp))
            resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    choice = (data.get("choices") or [{}])[0]
    content = ((choice.get("message") or {}).get("content") or "").strip()
    usage = data.get("usage") or {}
    return content, {
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
    }
