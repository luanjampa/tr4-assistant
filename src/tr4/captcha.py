"""
Cloudflare Turnstile server-side verification — stops scripted bots from
spamming /chat and running up the Groq bill without needing a human to
solve anything most of the time (Turnstile usually passes invisibly).

This only matters once some frontend actually renders the Turnstile widget
and sends the resulting token as `captcha_token` — there's no UI in this
repo (API-only by design). Until `TURNSTILE_SECRET_KEY` is set, verification
is skipped entirely, same opt-in pattern as auth.py/rate_limit.py.
"""

from __future__ import annotations

import logging

import httpx

from tr4.config import Settings

logger = logging.getLogger(__name__)

_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_captcha(token: str | None, remote_ip: str | None, settings: Settings) -> bool:
    if not settings.turnstile_secret_key:
        logger.warning("TURNSTILE_SECRET_KEY não configurada — /chat aceita sem captcha.")
        return True

    if not token:
        return False

    data = {"secret": settings.turnstile_secret_key, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(_VERIFY_URL, data=data)
            resp.raise_for_status()
            result = resp.json()
    except Exception as e:
        logger.warning("Falha ao verificar captcha (tratando como inválido): %s", e)
        return False

    return bool(result.get("success"))
