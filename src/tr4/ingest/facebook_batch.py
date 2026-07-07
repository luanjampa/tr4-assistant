"""
Batch ingestion for Facebook-sourced data.

Real Graph API sync should run in this module behind credentials (not in the LLM).
Until Meta credentials are configured, use a JSON file export shape:

[
  {"id": "1", "message": "...", "created_time": "2024-01-01T00:00:00+0000", "from": {"name": "User"}}
]

Or load from FACEBOOK_* env when implemented.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_facebook_json_file(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("Facebook export JSON must be a list of objects")
    return [x for x in data if isinstance(x, dict)]


def facebook_items_to_documents(items: list[dict[str, Any]], *, source_label: str = "facebook") -> list[dict]:
    docs: list[dict] = []
    for i, item in enumerate(items):
        msg = item.get("message") or item.get("story") or ""
        if not msg or not str(msg).strip():
            continue
        author = ""
        if isinstance(item.get("from"), dict):
            author = str(item["from"].get("name") or "")
        created = str(item.get("created_time") or "")
        text = f"[{created}] {author}: {msg}".strip()
        doc_id = f"{source_label}_{item.get('id', i)}"
        docs.append(
            {
                "id": doc_id,
                "text": text,
                "metadata": {"source": source_label, "kind": "facebook_post", "created_time": created},
            }
        )
    return docs


async def fetch_group_feed_stub() -> list[dict]:
    """
    Placeholder for future Graph API batch fetch.
    Returns empty until FACEBOOK_ACCESS_TOKEN + FACEBOOK_GROUP_ID are wired with approved app.
    """
    return []
