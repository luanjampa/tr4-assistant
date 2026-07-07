"""Parse WhatsApp exported .txt (Android/iOS common patterns)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class WhatsAppMessage:
    sender: str
    body: str
    raw_ts: str | None


# Examples: [12/03/2024, 14:30:01] Name: text
#           12/03/2024, 14:30 - Name: text
_LINE_RE = re.compile(
    r"^(?:\[)?(?P<d>\d{1,2}[/.]\d{1,2}[/.]\d{2,4})[,\s]+(?P<t>\d{1,2}:\d{2}(?::\d{2})?)\]?\s*[-–]?\s*(?P<name>[^:]+):\s*(?P<body>.*)$"
)

# WhatsApp exports (iOS especially) prefix many lines with invisible bidi
# control characters (U+200E left-to-right mark and friends). Left in place,
# these break the anchored regex above and silently merge real messages into
# the previous one as "continuation" text — confirmed on a real export where
# it ate ~14% of all lines.
_INVISIBLE_MARKS_RE = re.compile("[‎‏‪-‮⁦-⁩]")


def _clean_line(line: str) -> str:
    return _INVISIBLE_MARKS_RE.sub("", line).strip()


# WhatsApp system/media placeholders — not real content, just noise for a
# knowledge base (deleted messages, stickers, system membership events...).
_NOISE_SUBSTRINGS = (
    "mensagem apagada",
    "esta mensagem foi apagada",
    "figurinha omitida",
    "áudio ocultado",
    "audio ocultado",
    "imagem ocultada",
    "imagem omitida",
    "vídeo omitido",
    "video omitido",
    "gif omitido",
    "documento omitido",
    "contato omitido",
    "<mídia oculta>",
    "<media omitted>",
    "criou este grupo",
    "criou o grupo",
    "adicionou você",
    "as mensagens e ligações são protegidas",
    "mudou o nome do grupo",
    "mudou a imagem do grupo",
)


def is_noise_message(body: str) -> bool:
    s = body.strip().lower()
    if not s:
        return True
    return any(sub in s for sub in _NOISE_SUBSTRINGS)


def filter_noise(messages: list[WhatsAppMessage]) -> list[WhatsAppMessage]:
    return [m for m in messages if not is_noise_message(m.body)]


def parse_whatsapp_export(text: str) -> list[WhatsAppMessage]:
    """Split export into messages; continuation lines append to previous body."""
    lines = text.replace("\r\n", "\n").split("\n")
    messages: list[WhatsAppMessage] = []
    current: WhatsAppMessage | None = None

    for raw_line in lines:
        line = _clean_line(raw_line)
        m = _LINE_RE.match(line)
        if m:
            if current:
                messages.append(current)
            raw_ts = f"{m.group('d')} {m.group('t')}"
            current = WhatsAppMessage(
                sender=m.group("name").strip(),
                body=m.group("body").strip(),
                raw_ts=raw_ts,
            )
        elif current and line:
            current = WhatsAppMessage(
                sender=current.sender,
                body=current.body + "\n" + line,
                raw_ts=current.raw_ts,
            )
    if current:
        messages.append(current)

    return messages


def messages_to_documents(
    messages: list[WhatsAppMessage],
    *,
    window: int = 12,
    source_label: str = "whatsapp",
) -> list[dict]:
    """
    Group consecutive messages into sliding windows for richer context.
    Each document: {id, text, metadata}.
    """
    docs: list[dict] = []
    if not messages:
        return docs

    for i in range(0, len(messages), max(1, window // 2)):
        chunk = messages[i : i + window]
        lines = []
        for msg in chunk:
            ts = f"[{msg.raw_ts}] " if msg.raw_ts else ""
            lines.append(f"{ts}{msg.sender}: {msg.body}")
        text = "\n".join(lines)
        doc_id = f"{source_label}_{i}_{len(chunk)}"
        docs.append(
            {
                "id": doc_id,
                "text": text,
                "metadata": {"source": source_label, "kind": "whatsapp_window"},
            }
        )
    return docs


def window_body_texts(messages: list[WhatsAppMessage], *, window: int = 12) -> list[str]:
    """
    Same windowing as `messages_to_documents`, in the same order — but bodies
    only, no sender name/timestamp. Used to judge topic relevance without a
    contaminated sender display name (e.g. "higor tr4") giving a free pass to
    a window whose actual messages have nothing to do with the car.
    """
    texts: list[str] = []
    if not messages:
        return texts
    for i in range(0, len(messages), max(1, window // 2)):
        chunk = messages[i : i + window]
        texts.append("\n".join(msg.body for msg in chunk))
    return texts
