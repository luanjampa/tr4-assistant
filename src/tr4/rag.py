"""Retrieve context from Postgres/pgvector and answer with Groq."""

from __future__ import annotations

from pathlib import Path

from tr4.budget import BUDGET_EXCEEDED_REPLY, check_budget_ok, record_usage
from tr4.chat_groq import chat_complete
from tr4.config import Settings, get_settings
from tr4.embeddings import embed_texts
from tr4.gaps import is_gap, record_gap
from tr4.guardrails import OFF_TOPIC_REPLY, looks_in_scope
from tr4.store import count_rows_async, query_similar_async


def _load_system_template() -> str:
    path = Path(__file__).resolve().parent / "prompts" / "system.txt"
    return path.read_text(encoding="utf-8")


async def answer_question(
    user_message: str,
    *,
    settings: Settings | None = None,
) -> tuple[str, list[str]]:
    """
    Returns (reply, source_snippets_preview).
    Does not persist user messages into the knowledge base.
    """
    settings = settings or get_settings()

    if not await check_budget_ok(settings):
        return BUDGET_EXCEEDED_REPLY, []

    in_scope, scope_usage = await looks_in_scope(user_message, settings)
    if scope_usage is not None:
        await record_usage(scope_usage["prompt_tokens"], scope_usage["completion_tokens"], settings)
    if not in_scope:
        return OFF_TOPIC_REPLY, []

    count = await count_rows_async(settings.database_url)
    if count == 0:
        return (
            "A base de conhecimento ainda está vazia. Corre o job de sincronização (`tr4-sync`) "
            "com WhatsApp, JSON do Facebook, manuais (`--docs`) e/ou fontes web (`--web-seeds`).",
            [],
        )

    q_emb = (await embed_texts([user_message], settings))[0]
    results = await query_similar_async(settings.database_url, q_emb, min(settings.rag_top_k, count))

    context_parts: list[str] = []
    previews: list[str] = []
    for r in results:
        doc = r["text"]
        meta = r["metadata"] or {}
        src = str(meta.get("source") or "")
        kind = str(meta.get("kind") or "fonte")
        label = f"[{kind} | {src}]" if src else f"[{kind}]"
        context_parts.append(f"{label}\n{doc}")
        previews.append(doc[:280] + ("…" if len(doc) > 280 else ""))

    context = "\n\n---\n\n".join(context_parts) if context_parts else "(sem contexto recuperado)"
    system_template = _load_system_template()
    system_content = system_template.replace("{context}", context)

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_message},
    ]
    reply, usage = await chat_complete(messages, settings)
    await record_usage(usage["prompt_tokens"], usage["completion_tokens"], settings)

    best_distance = results[0]["distance"] if results else None
    if is_gap(reply, best_distance, settings):
        await record_gap(user_message, best_distance, reply, settings)

    return reply, previews
