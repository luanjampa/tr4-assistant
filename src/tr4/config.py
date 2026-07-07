from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Embeddings — Cloudflare Workers AI (bge-m3: multilíngue, 1024 dim, sem servidor pra manter)
    cloudflare_account_id: str | None = None
    cloudflare_api_token: str | None = None
    cloudflare_embed_model: str = "@cf/baai/bge-m3"
    embedding_dim: int = 1024
    embed_batch_size: int = 20
    # AI Gateway (opcional) — dá limite de gasto real ($/mês) e rate limit no
    # Cloudflare em si, além do que já existe no app. Sem isso, chama Workers AI direto.
    cloudflare_gateway_id: str | None = None
    cloudflare_gateway_token: str | None = None

    # Chat (Groq — API compatível OpenAI, sem GPU)
    groq_api_key: str | None = None
    groq_chat_model: str = "llama-3.1-8b-instant"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    # Preço por milhão de tokens (ajustar conforme tabela Groq vigente)
    groq_price_in_per_m: float = 0.05
    groq_price_out_per_m: float = 0.08
    max_tokens_per_reply: int = 700

    tr4_data_dir: Path = Path("./data")

    # Postgres + pgvector
    database_url: str = "postgresql://tr4:tr4@127.0.0.1:5433/tr4"

    facebook_access_token: str | None = None
    facebook_group_id: str | None = None

    rag_top_k: int = 6
    rag_chunk_size: int = 900
    rag_chunk_overlap: int = 120

    # Segurança / custo
    tr4_api_key: str | None = None
    rate_limit_per_minute: int = 20
    max_monthly_spend_usd: float = 5.0

    # Cloudflare Turnstile — opcional. Só faz efeito quando um frontend existir pra
    # renderizar o widget (a site key é pública, fica no frontend); sem essa variável,
    # /chat não exige captcha.
    turnstile_secret_key: str | None = None
    # Site key é pública por natureza (Cloudflare) — servida ao frontend via GET /config.
    turnstile_site_key: str | None = None

    # Acima disso, distância (cosine) do melhor match é tratada como "sem boa resposta"
    # e a pergunta é registrada em tr4_gaps pra futura ingestão (ver gaps.py).
    unanswered_distance_threshold: float = 0.45


def get_settings() -> Settings:
    return Settings()
