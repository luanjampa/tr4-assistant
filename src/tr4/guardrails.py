"""
Scope check before answering (TR4-only).

Neither an allowlist nor a blocklist of keywords actually solves this: a car
part allowlist never ends (motor, catalisador, trizeta, bandeja, cardã...),
and a "clearly off-topic" blocklist is just as unbounded in the other
direction (cachorro, drogas, futebol, religião... every non-car topic there
is). So keyword lists are kept ONLY as a cheap, zero-latency fast path for
the obvious majority of messages; anything that hits neither list is
genuinely ambiguous and gets a real judgment call from a tiny, cheap Groq
classification request instead of a guess.

A raw pgvector-distance threshold was tried and rejected as a classifier:
calibration showed a clearly off-topic query ("como emagrecer") scoring a
*closer* distance to the knowledge base than a legitimately in-scope one
("trizeta fazendo barulho") — short-phrase embeddings don't separate topics
reliably enough here to be a safety signal on their own.
"""

from __future__ import annotations

from tr4.chat_groq import chat_complete
from tr4.config import Settings

TR4_SCOPE_HINTS = (
    "tr4",
    "tr-4",
    "pajero",
    "grupo",
    "whatsapp",
    "facebook",
)

OFF_TOPIC_HINTS = (
    "receita",
    "bolo",
    "culinária",
    "culinaria",
    "clima",
    "previsão do tempo",
    "previsao do tempo",
    "política",
    "politica",
    "eleição",
    "eleicao",
    "presidente",
    "futebol",
    "novela",
    "celebridade",
    "horóscopo",
    "horoscopo",
    "signo",
    "piada",
    "poema",
    "tradução",
    "traducao",
    "emagrecer",
    "dieta",
    "capital de",
    "capital da",
    "quem foi",
    "quem é",
    "quem e",
)

_CLASSIFY_SYSTEM = (
    "Responda apenas SIM ou NAO, nada mais.\n"
    "A mensagem do usuário é sobre o veículo Mitsubishi Pajero TR4 — peças, manutenção, "
    "instalação, preço, modificação/preparação, problema mecânico, ou qualquer assunto "
    "de carro/oficina em geral? Ou é claramente sobre outra coisa (comida, clima, "
    "política, animais, entretenimento, saúde pessoal, etc)?\n"
    "SIM = relacionado a carro/TR4. NAO = claramente outro assunto."
)


def _keyword_hint(user_message: str) -> bool | None:
    """Fast path. Returns True (allow), False (block), or None (ambiguous)."""
    s = user_message.strip().lower()
    if len(s) <= 3:
        return True
    if any(h in s for h in TR4_SCOPE_HINTS):
        return True
    if any(h in s for h in OFF_TOPIC_HINTS):
        return False
    return None


async def looks_in_scope(user_message: str, settings: Settings) -> tuple[bool, dict[str, int] | None]:
    """Returns (in_scope, usage). usage is None when no Groq call was made (fast path or failure)."""
    hint = _keyword_hint(user_message)
    if hint is not None:
        return hint, None

    try:
        reply, usage = await chat_complete(
            [
                {"role": "system", "content": _CLASSIFY_SYSTEM},
                {"role": "user", "content": user_message},
            ],
            settings,
            max_tokens=5,
        )
    except Exception:
        # Classifier failed (e.g. GROQ_API_KEY missing/network) — fail open so a
        # broken classifier doesn't take down the whole bot; the system prompt
        # still refuses off-topic content as a second layer.
        return True, None

    return reply.strip().strip(".").upper().startswith("SIM"), usage


OFF_TOPIC_REPLY = (
    "Só posso ajudar com assuntos relacionados ao TR4 (dúvidas e problemas do produto/grupo). "
    "Reformula a tua pergunta em torno do TR4 ou de um problema concreto que estejas a ter."
)
