"""Ollama embedding API."""

from __future__ import annotations

import httpx

from tr4.config import Settings


async def embed_texts(
    texts: list[str],
    settings: Settings,
) -> list[list[float]]:
    if not texts:
        return []
    base = settings.ollama_base_url.rstrip("/")
    out: list[list[float]] = []
    async with httpx.AsyncClient(timeout=120.0) as client:
        for t in texts:
            data = await _post_embed(client, base, settings.ollama_embed_model, t)
            out.append(_parse_embedding_vector(data))
    return out


def embed_texts_sync(texts: list[str], settings: Settings) -> list[list[float]]:
    if not texts:
        return []
    base = settings.ollama_base_url.rstrip("/")
    out: list[list[float]] = []
    with httpx.Client(timeout=120.0) as client:
        for t in texts:
            data = _post_embed_sync(client, base, settings.ollama_embed_model, t)
            out.append(_parse_embedding_vector(data))
    return out


def _parse_embedding_vector(data: dict) -> list[float]:
    emb = data.get("embeddings")
    if emb is None and "embedding" in data:
        emb = [data["embedding"]]
    if not emb:
        raise RuntimeError(f"Unexpected embed response keys: {list(data.keys())}")
    first = emb[0]
    return first if isinstance(first, list) else emb  # type: ignore[return-value]


async def _post_embed(client: httpx.AsyncClient, base: str, model: str, text: str) -> dict:
    url = f"{base}/api/embed"
    resp = await client.post(url, json={"model": model, "input": text})
    if resp.status_code == 404:
        resp = await client.post(
            f"{base}/api/embeddings",
            json={"model": model, "prompt": text},
        )
    resp.raise_for_status()
    return resp.json()


def _post_embed_sync(client: httpx.Client, base: str, model: str, text: str) -> dict:
    url = f"{base}/api/embed"
    resp = client.post(url, json={"model": model, "input": text})
    if resp.status_code == 404:
        resp = client.post(
            f"{base}/api/embeddings",
            json={"model": model, "prompt": text},
        )
    resp.raise_for_status()
    return resp.json()
