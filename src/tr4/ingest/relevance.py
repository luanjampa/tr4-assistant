"""
Filters bulk group-chat content (WhatsApp today) down to TR4-relevant windows
before indexing. Group exports mix everything — jokes, stickers, meetup
logistics — with real TR4 knowledge; indexing the noise wastes storage and
dilutes retrieval quality.

Same two-tier idea as guardrails.py (free keyword fast-path, Groq classifier
for the rest) but for bulk content instead of a live user question. The
keyword check here must run on message BODIES ONLY, not sender names — some
real senders in a TR4 group have "tr4" in their own display name and would
otherwise get a free pass regardless of what they actually wrote.
"""

from __future__ import annotations

import asyncio
import logging

from tr4.chat_groq import chat_complete
from tr4.config import Settings
from tr4.guardrails import TR4_SCOPE_HINTS

logger = logging.getLogger(__name__)

_CLASSIFY_SYSTEM = (
    "Responda apenas SIM ou NAO, nada mais.\n"
    "O trecho de conversa de grupo abaixo contém alguma informação real sobre um "
    "veículo/carro — peça, manutenção, preço, modificação, problema mecânico, "
    "dúvida técnica? Ou é só conversa sem relação (bate-papo pessoal, piada, "
    "combinar encontro, saudação, etc)?\n"
    "SIM = tem conteúdo real sobre o carro. NAO = é só conversa sem relação."
)


def _mentions_tr4(body_only_text: str) -> bool:
    s = body_only_text.lower()
    return any(h in s for h in TR4_SCOPE_HINTS)


async def _classify(body_only_text: str, settings: Settings) -> bool:
    try:
        reply, _usage = await chat_complete(
            [
                {"role": "system", "content": _CLASSIFY_SYSTEM},
                {"role": "user", "content": body_only_text[:2000]},
            ],
            settings,
            max_tokens=5,
        )
    except Exception as e:
        logger.warning("Classificador de relevância falhou, mantendo por padrão: %s", e)
        return True  # fail open — losing real data permanently is worse than a bit of noise
    return reply.strip().strip(".").upper().startswith("SIM")


async def filter_relevant(
    docs: list[dict],
    body_only_texts: list[str],
    settings: Settings,
    *,
    delay_seconds: float = 1.0,
) -> list[dict]:
    """docs[i] and body_only_texts[i] must correspond to the same window."""
    kept: list[dict] = []
    classified = 0
    for doc, body_text in zip(docs, body_only_texts):
        if _mentions_tr4(body_text):
            kept.append(doc)
            continue
        if classified > 0:
            await asyncio.sleep(delay_seconds)
        classified += 1
        if await _classify(body_text, settings):
            kept.append(doc)
    return kept
