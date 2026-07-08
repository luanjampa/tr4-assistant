"""Batch ingestion of manual documents (PDF / txt / md) into the knowledge base."""

from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader

logger = logging.getLogger(__name__)


def _ocr_page(path: Path, page_num: int) -> str:
    """Fallback for scanned pages pypdf can't extract a text layer from.

    Renders just that one page to an image (pdf2image, needs the `poppler`
    binary) and OCRs it (pytesseract, needs the `tesseract` binary, `por`
    language pack) — both external system deps, not in requirements.txt,
    since ingestion is a local/manual job (see CLAUDE.md), not something the
    deployed Render API container ever runs. Degrades to "" (page skipped,
    same as before) if either isn't installed or OCR itself fails, so a dev
    machine without tesseract set up doesn't lose non-scanned pages too.
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        return ""
    try:
        images = convert_from_path(str(path), first_page=page_num, last_page=page_num, dpi=300)
        if not images:
            return ""
        return pytesseract.image_to_string(images[0], lang="por")
    except Exception as e:
        logger.warning("OCR falhou em %s p%d: %s", path.name, page_num, e)
        return ""


def _pdf_to_documents(path: Path, *, kind: str, id_prefix: str) -> list[dict]:
    docs: list[dict] = []
    reader = PdfReader(str(path))
    for page_num, page in enumerate(reader.pages, start=1):
        # pypdf occasionally emits NUL bytes from garbled font/encoding data in
        # a page's content stream — Postgres text columns reject them outright
        # (psycopg.DataError), so strip before this ever reaches store.py.
        text = (page.extract_text() or "").replace("\x00", "").strip()
        extraction = "text"
        if not text:
            text = _ocr_page(path, page_num).replace("\x00", "").strip()
            extraction = "ocr"
        if not text:
            continue
        docs.append(
            {
                "id": f"{id_prefix}_{path.stem}_p{page_num}",
                "text": text,
                "metadata": {
                    "source": path.name,
                    "kind": kind,
                    "file": path.name,
                    "page": str(page_num),
                    "extraction": extraction,
                },
            }
        )
    return docs


def _text_to_documents(path: Path, *, kind: str, id_prefix: str) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace").replace("\x00", "").strip()
    if not text:
        return []
    return [
        {
            "id": f"{id_prefix}_{path.stem}",
            "text": text,
            "metadata": {"source": path.name, "kind": kind, "file": path.name},
        }
    ]


def load_docs_folder(folder: Path, *, kind: str = "manual_doc", id_prefix: str = "doc") -> list[dict]:
    """Reads every .pdf/.txt/.md file in `folder`, recursively, into documents.

    `kind` is a trust-tier tag read by prompts/system.txt (e.g. "manual_doc" for an
    official owner's manual vs "owner_note" for a personal report from the vehicle's
    owner — real but not manufacturer-official, so it must not be labeled the same way.
    Recursive so a folder organized into subfolders (e.g. one per vehicle system —
    motor/, freio/, eletrica/...) is picked up in one `--docs` pass; subfolder names
    aren't tracked in metadata, just the filename, so filenames must stay unique across
    subfolders (true today — chapter-numbered workshop manual pages).
    """
    docs: list[dict] = []
    if not folder.exists():
        return docs
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            docs.extend(_pdf_to_documents(path, kind=kind, id_prefix=id_prefix))
        elif suffix in (".txt", ".md"):
            docs.extend(_text_to_documents(path, kind=kind, id_prefix=id_prefix))
    return docs
