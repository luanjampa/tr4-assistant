"""Build indexed rows from raw documents (chunking + stable ids)."""

from __future__ import annotations

from tr4.chunks import chunk_text
from tr4.config import Settings


def flatten_metadata(meta: dict | None) -> dict[str, str]:
    if not meta:
        return {}
    out: dict[str, str] = {}
    for k, v in meta.items():
        if v is None:
            continue
        out[str(k)] = str(v)
    return out


def expand_documents_to_rows(
    documents: list[dict],
    settings: Settings,
) -> list[dict]:
    """
    Each input document: {id, text, metadata?}.
    Output rows: {id, text, metadata} ready for embedding and Postgres/pgvector.
    """
    rows: list[dict] = []
    for d in documents:
        doc_id = str(d["id"])
        text = str(d["text"]).strip()
        meta = flatten_metadata(d.get("metadata"))
        if not text:
            continue

        if len(text) <= settings.rag_chunk_size:
            rows.append({"id": doc_id, "text": text, "metadata": meta})
            continue

        parts = chunk_text(
            text,
            chunk_size=settings.rag_chunk_size,
            overlap=settings.rag_chunk_overlap,
        )
        for j, part in enumerate(parts):
            sub_id = f"{doc_id}__c{j}"
            sub_meta = {**meta, "chunk": str(j)}
            rows.append({"id": sub_id, "text": part, "metadata": sub_meta})
    return rows
