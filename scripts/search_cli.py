#!/usr/bin/env python3
"""
Interactive local retrieval test — no Groq, no API server, no cost.

Embeds the question (Cloudflare Workers AI) and shows what pgvector would hand
to the LLM as CONTEXT, so you can check retrieval quality with the data
already indexed without needing a GROQ_API_KEY.
"""

from __future__ import annotations

import asyncio

from tr4.config import get_settings
from tr4.embeddings import embed_texts
from tr4.guardrails import OFF_TOPIC_REPLY, _keyword_hint
from tr4.store import count_rows_async, query_similar_async


async def search(question: str, k: int = 5) -> None:
    settings = get_settings()
    # Fast-path only — the real guardrail falls back to a Groq classifier call
    # for ambiguous messages, but this tool is meant to work with no GROQ_API_KEY
    # and no cost, so it just flags the ambiguous case instead of asking Groq.
    hint = _keyword_hint(question)
    if hint is False:
        print(f"[guardrail bloquearia essa pergunta] {OFF_TOPIC_REPLY}")
        return
    if hint is None:
        print("[guardrail: ambíguo — em produção isso chamaria o Groq pra decidir. Mostrando retrieval mesmo assim:]")

    count = await count_rows_async(settings.database_url)
    if count == 0:
        print("Base de conhecimento vazia — roda `make sync` primeiro.")
        return

    emb = (await embed_texts([question], settings))[0]
    results = await query_similar_async(settings.database_url, emb, min(k, count))
    for r in results:
        meta = r["metadata"] or {}
        print(f"\n[{meta.get('kind')} | {meta.get('source')}] dist={r['distance']:.3f}")
        print(r["text"][:400])


async def main() -> None:
    print("Testa retrieval local (sem Groq, sem custo, sem API rodando).")
    print("'sair' ou Ctrl+C pra encerrar.\n")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q or q.lower() in ("sair", "exit", "quit"):
            break
        await search(q)
        print()


if __name__ == "__main__":
    asyncio.run(main())
