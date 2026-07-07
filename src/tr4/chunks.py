"""Split long text into overlapping chunks for embedding."""


def chunk_text(
    text: str,
    *,
    chunk_size: int,
    overlap: int,
) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    step = max(1, chunk_size - overlap)
    while start < len(text):
        end = start + chunk_size
        piece = text[start:end]
        chunks.append(piece.strip())
        start += step
    return [c for c in chunks if c]
