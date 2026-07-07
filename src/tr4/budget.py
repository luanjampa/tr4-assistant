"""Monthly spend cap for Groq chat usage, tracked in Postgres."""

from __future__ import annotations

from tr4.config import Settings
from tr4.store import get_pool

TABLE = "tr4_usage"

_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id bigserial PRIMARY KEY,
    ts timestamptz NOT NULL DEFAULT now(),
    prompt_tokens integer NOT NULL,
    completion_tokens integer NOT NULL,
    cost_usd numeric NOT NULL
);
"""


def _cost_usd(prompt_tokens: int, completion_tokens: int, settings: Settings) -> float:
    return (
        prompt_tokens / 1_000_000 * settings.groq_price_in_per_m
        + completion_tokens / 1_000_000 * settings.groq_price_out_per_m
    )


async def ensure_schema(settings: Settings) -> None:
    pool = await get_pool(settings.database_url)
    async with pool.connection() as conn:
        await conn.execute(_SCHEMA_SQL)


async def month_spend_usd(settings: Settings) -> float:
    pool = await get_pool(settings.database_url)
    async with pool.connection() as conn:
        row = await (
            await conn.execute(
                f"""
                SELECT COALESCE(SUM(cost_usd), 0) FROM {TABLE}
                WHERE date_trunc('month', ts) = date_trunc('month', now())
                """
            )
        ).fetchone()
        return float(row[0])


async def check_budget_ok(settings: Settings) -> bool:
    spent = await month_spend_usd(settings)
    return spent < settings.max_monthly_spend_usd


async def record_usage(prompt_tokens: int, completion_tokens: int, settings: Settings) -> None:
    cost = _cost_usd(prompt_tokens, completion_tokens, settings)
    pool = await get_pool(settings.database_url)
    async with pool.connection() as conn:
        await conn.execute(
            f"INSERT INTO {TABLE} (prompt_tokens, completion_tokens, cost_usd) VALUES (%s, %s, %s)",
            (prompt_tokens, completion_tokens, cost),
        )


BUDGET_EXCEEDED_REPLY = (
    "O limite de gasto mensal do assistente foi atingido. Tenta novamente no próximo mês "
    "ou contacta o administrador para ajustar o limite."
)
