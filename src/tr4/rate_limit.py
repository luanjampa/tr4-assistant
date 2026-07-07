"""In-memory sliding-window rate limiter (single-instance only)."""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request

from tr4.config import get_settings

_hits: dict[str, list[float]] = defaultdict(list)
_lock = Lock()


async def enforce_rate_limit(request: Request) -> None:
    settings = get_settings()
    limit = settings.rate_limit_per_minute
    if limit <= 0:
        return

    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window_start = now - 60.0

    with _lock:
        hits = [t for t in _hits[key] if t > window_start]
        if len(hits) >= limit:
            _hits[key] = hits
            raise HTTPException(status_code=429, detail="Muitas requisições. Tenta novamente em instantes.")
        hits.append(now)
        _hits[key] = hits
