"""
Tracks questions the knowledge base likely couldn't answer well, so they can
be reviewed later and used to target future ingestion (`tr4-sync --docs`/
`--web-seeds`/`--owner-notes`).

A question is flagged as a "gap" when either signal fires:
- the best retrieval match was a weak one (distance above threshold) — a
  more reliable signal than parsing the model's prose, since it doesn't
  depend on the model phrasing its uncertainty a particular way.
- the reply contains one of the phrases the system prompt tells the model to
  use when CONTEXT doesn't cover the question.
"""

from __future__ import annotations

import re

from tr4.config import Settings
from tr4.store import get_pool

TABLE = "tr4_gaps"

_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id bigserial PRIMARY KEY,
    ts timestamptz NOT NULL DEFAULT now(),
    question text NOT NULL,
    best_distance real,
    reply_snippet text
);
"""

_DONT_KNOW_RE = re.compile(
    r"não tenho (essa|esta|a) informação|não encontrei|não tenho esse dado|"
    r"base de conhecimento não|não consta (no|na) contexto",
    re.IGNORECASE,
)


async def ensure_schema(settings: Settings) -> None:
    pool = await get_pool(settings.database_url)
    async with pool.connection() as conn:
        await conn.execute(_SCHEMA_SQL)


def is_gap(reply: str, best_distance: float | None, settings: Settings) -> bool:
    if best_distance is None or best_distance > settings.unanswered_distance_threshold:
        return True
    return bool(_DONT_KNOW_RE.search(reply))


async def record_gap(question: str, best_distance: float | None, reply: str, settings: Settings) -> None:
    pool = await get_pool(settings.database_url)
    async with pool.connection() as conn:
        await conn.execute(
            f"INSERT INTO {TABLE} (question, best_distance, reply_snippet) VALUES (%s, %s, %s)",
            (question, best_distance, reply[:500]),
        )


async def top_gaps(settings: Settings, limit: int = 30) -> list[dict]:
    """Most-repeated unanswered questions first — a rough dedupe by exact text."""
    pool = await get_pool(settings.database_url)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT question, count(*) AS n, max(ts) AS last_seen, avg(best_distance) AS avg_distance
            FROM {TABLE}
            GROUP BY question
            ORDER BY n DESC, last_seen DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = await cur.fetchall()
    return [
        {"question": r[0], "count": r[1], "last_seen": r[2], "avg_distance": r[3]}
        for r in rows
    ]
