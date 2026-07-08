"""Cloudflare Workers AI embeddings (bge-m3) — no server to host, unlike Ollama."""

from __future__ import annotations

import asyncio
import time

import httpx

from tr4.config import Settings

# The AI Gateway's 50 req/min limit (see CLAUDE.md) is a non-issue for a single
# live /chat query (one embed_texts call), but batch ingestion (tr4-sync) can
# easily need hundreds of requests — guaranteed to hit it partway through
# without retrying. Same idea as chat_groq.py's 429 handling, but looped since
# a batch job needs to survive being rate-limited repeatedly, not just once.
_MAX_RETRIES = 8
_MAX_RETRY_WAIT_SECONDS = 30.0


def _retry_wait_seconds(resp: httpx.Response) -> float:
    for header in ("retry-after", "x-ratelimit-reset-requests"):
        value = resp.headers.get(header)
        if not value:
            continue
        try:
            return min(float(value.rstrip("s")), _MAX_RETRY_WAIT_SECONDS)
        except ValueError:
            continue
    return 5.0


def _url(settings: Settings) -> str:
    return (
        f"https://api.cloudflare.com/client/v4/accounts/{settings.cloudflare_account_id}"
        f"/ai/run/{settings.cloudflare_embed_model}"
    )


def _headers(settings: Settings) -> dict[str, str]:
    if not settings.cloudflare_account_id or not settings.cloudflare_api_token:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN não configuradas.")
    headers = {"Authorization": f"Bearer {settings.cloudflare_api_token}"}
    # Routes through an AI Gateway (dash.cloudflare.com > IA > Gateway de AI) when
    # configured, so the gateway's monthly spend limit actually applies — calling
    # Workers AI directly bypasses any budget configured there. Optional: falls
    # back to calling Workers AI directly if not set.
    if settings.cloudflare_gateway_id:
        headers["cf-aig-gateway-id"] = settings.cloudflare_gateway_id
    if settings.cloudflare_gateway_token:
        headers["cf-aig-authorization"] = f"Bearer {settings.cloudflare_gateway_token}"
    return headers


def _parse_batch(data: dict) -> list[list[float]]:
    if not data.get("success"):
        raise RuntimeError(f"Workers AI embedding falhou: {data.get('errors')}")
    return data["result"]["data"]


def _batches(texts: list[str], size: int) -> list[list[str]]:
    return [texts[i : i + size] for i in range(0, len(texts), size)]


async def embed_texts(texts: list[str], settings: Settings) -> list[list[float]]:
    if not texts:
        return []
    out: list[list[float]] = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        for batch in _batches(texts, settings.embed_batch_size):
            resp = await client.post(_url(settings), headers=_headers(settings), json={"text": batch})
            for _ in range(_MAX_RETRIES):
                if resp.status_code != 429:
                    break
                await asyncio.sleep(_retry_wait_seconds(resp))
                resp = await client.post(_url(settings), headers=_headers(settings), json={"text": batch})
            resp.raise_for_status()
            out.extend(_parse_batch(resp.json()))
    return out


def embed_texts_sync(texts: list[str], settings: Settings) -> list[list[float]]:
    if not texts:
        return []
    out: list[list[float]] = []
    with httpx.Client(timeout=60.0) as client:
        for batch in _batches(texts, settings.embed_batch_size):
            resp = client.post(_url(settings), headers=_headers(settings), json={"text": batch})
            for _ in range(_MAX_RETRIES):
                if resp.status_code != 429:
                    break
                time.sleep(_retry_wait_seconds(resp))
                resp = client.post(_url(settings), headers=_headers(settings), json={"text": batch})
            resp.raise_for_status()
            out.extend(_parse_batch(resp.json()))
    return out
