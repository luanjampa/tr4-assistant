"""FastAPI: TR4 chat (RAG). User messages are not written to the knowledge base."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles

from tr4 import __version__
from tr4.auth import require_api_key
from tr4.budget import ensure_schema as ensure_budget_schema
from tr4.captcha import verify_captcha
from tr4.config import get_settings
from tr4.gaps import ensure_schema as ensure_gaps_schema
from tr4.legal import REPLY_DISCLAIMER, TERMS_TEXT
from tr4.rag import answer_question
from tr4.rate_limit import enforce_rate_limit
from tr4.store import ensure_schema_async

app = FastAPI(title="TR4 Assistant API", version=__version__)

# src/tr4/app.py -> parents[2] is the repo root both locally and in the Docker
# image (WORKDIR /app, `COPY frontend ./frontend`).
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    accepted_terms: bool = Field(
        default=False,
        description="Must be true. Fetch GET /terms and show it to the user before sending their first message.",
    )
    captcha_token: str | None = Field(
        default=None,
        description="Cloudflare Turnstile token from the frontend widget. Only checked if TURNSTILE_SECRET_KEY is configured.",
    )


class ChatResponse(BaseModel):
    reply: str
    context_previews: list[str] = Field(default_factory=list)
    disclaimer: str = REPLY_DISCLAIMER


@app.on_event("startup")
async def on_startup() -> None:
    settings = get_settings()
    await ensure_schema_async(settings.database_url, dim=settings.embedding_dim)
    await ensure_budget_schema(settings)
    await ensure_gaps_schema(settings)


@app.get("/")
async def root() -> dict:
    return {
        "name": "TR4 Assistant API",
        "version": __version__,
        "docs": "/docs",
        "ui": "/ui",
        "endpoints": ["/health", "/terms", "/config", "/chat"],
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/terms")
async def terms() -> dict:
    return {"terms": TERMS_TEXT}


@app.get("/config")
async def frontend_config() -> dict:
    """Public, non-secret config the static frontend needs at load time.

    TR4_API_KEY here is a cost/abuse gate, not a real secret, once shipped to
    every browser via a public frontend — rate limiting, the budget cap and
    (once configured) Turnstile are the actual controls (see CLAUDE.md).
    """
    settings = get_settings()
    return {
        "api_key": settings.tr4_api_key or "",
        "turnstile_site_key": settings.turnstile_site_key or "",
    }


@app.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    settings = get_settings()
    remote_ip = request.client.host if request.client else None
    if not await verify_captcha(body.captcha_token, remote_ip, settings):
        raise HTTPException(status_code=403, detail={"error": "captcha_failed"})
    if not body.accepted_terms:
        raise HTTPException(
            status_code=403,
            detail={"error": "terms_not_accepted", "terms": TERMS_TEXT},
        )
    try:
        reply, previews = await answer_question(body.message)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return ChatResponse(reply=reply, context_previews=previews)


app.mount("/ui", StaticFiles(directory=FRONTEND_DIR, html=True), name="ui")


def create_app() -> FastAPI:
    return app
