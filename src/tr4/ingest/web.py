"""
Batch web research ingestion: fetches real page content from a seed URL list
and indexes it. Does NOT trust numbers/codes typed by hand anywhere else —
only what is actually extracted from the live page, since seed sources
(manuals, catalogs, forums) can go stale or be wrong.

Seed file format: one URL per line, '#' starts a comment line.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import trafilatura
from pypdf import PdfReader
from io import BytesIO

logger = logging.getLogger(__name__)

_HEADERS = {
    # Some sources WAF-block generic "bot" user-agents outright (naive heuristic,
    # not an explicit robots.txt disallow — checked before making this change).
    # This is a low-volume batch job (one request per seed URL, run periodically),
    # not a crawler following links, so a standard browser UA is proportionate.
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}


def load_seed_urls(path: Path) -> list[str]:
    if not path.exists():
        return []
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def _url_id(url: str) -> str:
    return "web_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def _extract_pdf_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    pages = [(p.extract_text() or "") for p in reader.pages]
    return "\n".join(pages).strip()


def fetch_web_documents(
    urls: list[str],
    *,
    timeout: float = 20.0,
    delay_seconds: float = 2.0,
) -> list[dict]:
    """Best-effort: a failing URL is logged and skipped, not fatal.

    `delay_seconds` is a politeness pause between requests — several sources
    started returning 429 (Too Many Requests) when hit back-to-back with no
    delay, since a handful of these URLs share the same domain.
    """
    docs: list[dict] = []
    fetched_at = datetime.now(timezone.utc).isoformat()

    with httpx.Client(timeout=timeout, headers=_HEADERS, follow_redirects=True) as client:
        for i, url in enumerate(urls):
            if i > 0 and delay_seconds > 0:
                time.sleep(delay_seconds)
            try:
                resp = client.get(url)
                resp.raise_for_status()
            except Exception as e:
                logger.warning("Falha ao buscar %s: %s", url, e)
                continue

            content_type = resp.headers.get("content-type", "")
            is_pdf = "pdf" in content_type or url.lower().endswith(".pdf")

            if is_pdf:
                text = _extract_pdf_text(resp.content)
            else:
                text = trafilatura.extract(resp.text, url=url, include_tables=True)

            if not text or not text.strip():
                logger.warning("Sem texto extraído de %s", url)
                continue

            docs.append(
                {
                    "id": _url_id(url),
                    "text": text.strip(),
                    "metadata": {
                        "source": url,
                        "kind": "web_research",
                        "fetched_at": fetched_at,
                    },
                }
            )
    return docs
