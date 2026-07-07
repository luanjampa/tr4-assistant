"""
Batch sync: ingest WhatsApp / Facebook JSON / manuais / pesquisa web into Postgres (no LLM).

Usage:
  tr4-sync --whatsapp ./data/raw/grupo.txt
  tr4-sync --facebook-json ./data/raw/fb_export.json
  tr4-sync --facebook-manual ./data/facebook_manual
  tr4-sync --docs ./data/manuals
  tr4-sync --owner-notes ./data/notes
  tr4-sync --web-seeds ./data/seeds/tr4_sources.txt
  tr4-sync --whatsapp w.txt --facebook-json f.json --docs ./data/manuals --web-seeds seeds.txt --clear
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from tr4.config import get_settings
from tr4.embeddings import embed_texts_sync
from tr4.indexing import expand_documents_to_rows
from tr4.ingest.docs import load_docs_folder
from tr4.ingest.facebook_batch import facebook_items_to_documents, load_facebook_json_file
from tr4.ingest.relevance import filter_relevant
from tr4.ingest.web import fetch_web_documents, load_seed_urls
from tr4.ingest.whatsapp import filter_noise, messages_to_documents, parse_whatsapp_export, window_body_texts
from tr4.store import clear_table_sync, ensure_schema_sync, get_sync_conn, upsert_rows_sync


def _state_path(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "sync_state.json"


def _write_state(data_dir: Path, sources: list[str]) -> None:
    payload = {
        "last_sync_utc": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
    }
    p = _state_path(data_dir)
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_sync(
    *,
    whatsapp_path: Path | None,
    facebook_json: Path | None,
    docs_folder: Path | None,
    owner_notes_folder: Path | None,
    facebook_manual_folder: Path | None,
    web_seeds: Path | None,
    clear: bool,
) -> None:
    settings = get_settings()
    data_dir = Path(settings.tr4_data_dir)

    docs: list[dict] = []
    sources: list[str] = []

    if whatsapp_path:
        text = whatsapp_path.read_text(encoding="utf-8", errors="replace")
        msgs = filter_noise(parse_whatsapp_export(text))
        wa_docs = messages_to_documents(msgs, source_label="whatsapp")
        body_texts = window_body_texts(msgs)
        print(f"WhatsApp: {len(wa_docs)} janelas, filtrando relevância (chama Groq pras ambíguas)...")
        wa_docs = asyncio.run(filter_relevant(wa_docs, body_texts, settings))
        docs.extend(wa_docs)
        sources.append(f"whatsapp:{whatsapp_path.name}:{len(wa_docs)}/{len(body_texts)}janelas_relevantes")

    if facebook_json:
        items = load_facebook_json_file(facebook_json)
        docs.extend(facebook_items_to_documents(items, source_label="facebook"))
        sources.append(f"facebook:{facebook_json.name}")

    if docs_folder:
        folder_docs = load_docs_folder(docs_folder)
        docs.extend(folder_docs)
        sources.append(f"docs:{docs_folder}:{len(folder_docs)}files_or_pages")

    if owner_notes_folder:
        note_docs = load_docs_folder(owner_notes_folder, kind="owner_note", id_prefix="note")
        docs.extend(note_docs)
        sources.append(f"owner_notes:{owner_notes_folder}:{len(note_docs)}files_or_pages")

    if facebook_manual_folder:
        fb_docs = load_docs_folder(facebook_manual_folder, kind="facebook_post", id_prefix="fbmanual")
        docs.extend(fb_docs)
        sources.append(f"facebook_manual:{facebook_manual_folder}:{len(fb_docs)}files")

    if web_seeds:
        urls = load_seed_urls(web_seeds)
        web_docs = fetch_web_documents(urls)
        docs.extend(web_docs)
        sources.append(f"web:{web_seeds.name}:{len(web_docs)}/{len(urls)}urls")

    if not docs:
        raise SystemExit(
            "Nada para indexar: fornece --whatsapp, --facebook-json, --facebook-manual, "
            "--docs, --owner-notes e/ou --web-seeds."
        )

    rows = expand_documents_to_rows(docs, settings)
    texts = [r["text"] for r in rows]
    embeddings = embed_texts_sync(texts, settings)
    for r, emb in zip(rows, embeddings):
        r["embedding"] = emb

    conn = get_sync_conn(settings.database_url)
    ensure_schema_sync(conn, dim=settings.embedding_dim)
    if clear:
        clear_table_sync(conn)
    upsert_rows_sync(conn, rows)

    _write_state(data_dir, sources)
    print(f"Indexed {len(rows)} chunks into Postgres ({settings.database_url.split('@')[-1]})")
    print(f"State: {_state_path(data_dir)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="TR4 batch index sync (WhatsApp / Facebook JSON / manuais / pesquisa web)"
    )
    parser.add_argument("--whatsapp", type=Path, help="Path to WhatsApp export .txt")
    parser.add_argument("--facebook-json", type=Path, help="Path to Facebook JSON export")
    parser.add_argument(
        "--facebook-manual",
        type=Path,
        help="Pasta com posts do grupo Facebook colados à mão (.txt/.md) — marcados como kind=facebook_post, não oficial",
    )
    parser.add_argument("--docs", type=Path, help="Pasta com manuais oficiais (.pdf/.txt/.md)")
    parser.add_argument(
        "--owner-notes",
        type=Path,
        help="Pasta com relatos do dono/preparador (.pdf/.txt/.md) — marcados como kind=owner_note, não oficial",
    )
    parser.add_argument("--web-seeds", type=Path, help="Arquivo com URLs (uma por linha) para pesquisa web")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Wipe vector table before indexing (full rebuild)",
    )
    args = parser.parse_args()
    run_sync(
        whatsapp_path=args.whatsapp,
        facebook_json=args.facebook_json,
        docs_folder=args.docs,
        owner_notes_folder=args.owner_notes,
        facebook_manual_folder=args.facebook_manual,
        web_seeds=args.web_seeds,
        clear=args.clear,
    )


if __name__ == "__main__":
    main()
