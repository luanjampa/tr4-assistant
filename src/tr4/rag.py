"""Retrieve context from Postgres/pgvector and answer with Groq."""

from __future__ import annotations

import re
from pathlib import Path

from tr4.budget import BUDGET_EXCEEDED_REPLY, check_budget_ok, record_usage
from tr4.chat_groq import chat_complete
from tr4.config import Settings, get_settings
from tr4.embeddings import embed_texts
from tr4.gaps import is_gap, record_gap
from tr4.guardrails import OFF_TOPIC_REPLY, looks_in_scope
from tr4.store import count_rows_async, query_similar_async

# whatsapp_window/facebook_post chunks are lines of "[timestamp] Sender: text"
# (see ingest/whatsapp.py, ingest/facebook_batch.py) — real first/last names of
# group members. The system prompt asks the model not to repeat them, but an
# 8B model won't reliably hold that under every phrasing, so this is a
# backend-enforced safety net: pull every sender name out of the chunks that
# were actually retrieved for this question, and scrub them from the reply
# text regardless of what the model did.
_SENDER_LINE_RE = re.compile(r"^\[[^\]]*\]\s*([^:\n]+):", re.MULTILINE)
# WhatsApp prefixes senders not in the address book with "~ " (or a plain
# "- "), and export apps sometimes tack on an emoji from the contact's
# display name — strip both so the extracted name actually matches how the
# model writes it in prose ("~ Well Soares🏍" in the chunk vs "Well Soares"
# in the reply).
_NAME_PREFIX_RE = re.compile(r"^[~\-–\s]+")
_TRAILING_EMOJI_RE = re.compile(
    "[" "\U0001f300-\U0001faff" "\U0001f000-\U0001f0ff" "☀-➿" "︀-️" r"\s" "]+$"
)


def _extract_person_names(text: str) -> set[str]:
    names = set()
    for m in _SENDER_LINE_RE.finditer(text):
        name = _TRAILING_EMOJI_RE.sub("", _NAME_PREFIX_RE.sub("", m.group(1).strip())).strip()
        if len(name) >= 2:
            names.add(name)
    return names


def _redact_names(reply: str, names: set[str]) -> str:
    for name in sorted(names, key=len, reverse=True):
        # Word boundaries: an unbounded substring match would corrupt normal
        # text whenever a name happens to be a substring of an unrelated word
        # (e.g. "Ana" inside "banana", "análise").
        reply = re.sub(
            rf"\b{re.escape(name)}\b", "um usuário do grupo", reply, flags=re.IGNORECASE
        )
    return reply


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
    person_names: set[str] = set()
    for r in results:
        doc = r["text"]
        meta = r["metadata"] or {}
        src = str(meta.get("source") or "")
        kind = str(meta.get("kind") or "fonte")
        label = f"[{kind} | {src}]" if src else f"[{kind}]"
        context_parts.append(f"{label}\n{doc}")
        previews.append(doc[:280] + ("…" if len(doc) > 280 else ""))
        person_names |= _extract_person_names(doc)

    context = "\n\n---\n\n".join(context_parts) if context_parts else "(sem contexto recuperado)"
    system_template = _load_system_template()
    system_content = system_template.replace("{context}", context)

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_message},
    ]
    reply, usage = await chat_complete(messages, settings)
    await record_usage(usage["prompt_tokens"], usage["completion_tokens"], settings)
    if person_names:
        reply = _redact_names(reply, person_names)

    best_distance = results[0]["distance"] if results else None
    if is_gap(reply, best_distance, settings):
        await record_gap(user_message, best_distance, reply, settings)

    return reply, previews
