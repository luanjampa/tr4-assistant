from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Embeddings (Ollama local — CPU é suficiente)
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_embed_model: str = "nomic-embed-text"
    embedding_dim: int = 768

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

    # Acima disso, distância (cosine) do melhor match é tratada como "sem boa resposta"
    # e a pergunta é registrada em tr4_gaps pra futura ingestão (ver gaps.py).
    unanswered_distance_threshold: float = 0.45


def get_settings() -> Settings:
    return Settings()
