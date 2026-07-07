"""Simple API key guard for public endpoints."""

from __future__ import annotations

import hmac
import logging

from fastapi import Header, HTTPException

from tr4.config import get_settings

logger = logging.getLogger(__name__)


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.tr4_api_key:
        logger.warning("TR4_API_KEY não configurada — /chat está aberto sem autenticação.")
        return
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.tr4_api_key):
        raise HTTPException(status_code=401, detail="API key inválida ou ausente (header X-API-Key).")
