#!/usr/bin/env python3
"""
One-off migration: re-embed everything already in tr4_kb with a new
embedding provider/dimension, without re-running ingestion (no re-fetching
web pages, no re-parsing WhatsApp, no re-running the Groq relevance
classifier that took ~40-60min the first time). Reuses whatever text and
metadata is already indexed, drops+recreates tr4_kb with the new vector
dimension, and re-embeds in place.

Run this once after switching embedding providers (e.g. Ollama -> Cloudflare
Workers AI). Not needed for routine `tr4-sync` runs.
"""

from __future__ import annotations

from tr4.config import get_settings
from tr4.embeddings import embed_texts_sync
from tr4.store import TABLE, ensure_schema_sync, get_sync_conn, upsert_rows_sync


def main() -> None:
    settings = get_settings()
    conn = get_sync_conn(settings.database_url)

    rows = conn.execute(f"SELECT id, text, metadata FROM {TABLE}").fetchall()
    print(f"Lidas {len(rows)} linhas existentes de {TABLE}.")
    if not rows:
        print("Nada para migrar.")
        return

    conn.execute(f"DROP TABLE {TABLE} CASCADE")
    ensure_schema_sync(conn, dim=settings.embedding_dim)
    print(f"Tabela recriada com vector({settings.embedding_dim}).")

    ids = [r[0] for r in rows]
    texts = [r[1] for r in rows]
    metadatas = [r[2] for r in rows]

    print(f"Re-embedando {len(texts)} textos via {settings.cloudflare_embed_model}...")
    embeddings = embed_texts_sync(texts, settings)

    new_rows = [
        {"id": i, "text": t, "metadata": m, "embedding": e}
        for i, t, m, e in zip(ids, texts, metadatas, embeddings)
    ]
    upsert_rows_sync(conn, new_rows)
    print(f"Migração concluída: {len(new_rows)} linhas re-embedadas em {TABLE}.")


if __name__ == "__main__":
    main()
