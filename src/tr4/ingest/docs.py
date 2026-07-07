"""Batch ingestion of manual documents (PDF / txt / md) into the knowledge base."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


def _pdf_to_documents(path: Path, *, kind: str, id_prefix: str) -> list[dict]:
    docs: list[dict] = []
    reader = PdfReader(str(path))
    for page_num, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
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
                },
            }
        )
    return docs


def _text_to_documents(path: Path, *, kind: str, id_prefix: str) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
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
    """Reads every .pdf/.txt/.md file in `folder` (non-recursive) into documents.

    `kind` is a trust-tier tag read by prompts/system.txt (e.g. "manual_doc" for an
    official owner's manual vs "owner_note" for a personal report from the vehicle's
    owner — real but not manufacturer-official, so it must not be labeled the same way.
    """
    docs: list[dict] = []
    if not folder.exists():
        return docs
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            docs.extend(_pdf_to_documents(path, kind=kind, id_prefix=id_prefix))
        elif suffix in (".txt", ".md"):
            docs.extend(_text_to_documents(path, kind=kind, id_prefix=id_prefix))
    return docs
