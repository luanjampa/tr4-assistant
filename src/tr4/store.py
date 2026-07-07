"""Postgres + pgvector store for TR4 knowledge (replaces Chroma)."""

from __future__ import annotations

import json

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector, register_vector_async
from psycopg_pool import AsyncConnectionPool

TABLE = "tr4_kb"

def _schema_sql(dim: int) -> str:
    return f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS {TABLE} (
    id text PRIMARY KEY,
    text text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    embedding vector({dim}) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS {TABLE}_embedding_idx
    ON {TABLE} USING hnsw (embedding vector_cosine_ops);
"""


_pool: AsyncConnectionPool | None = None


def get_sync_conn(database_url: str) -> psycopg.Connection:
    conn = psycopg.connect(database_url, autocommit=True)
    # Some managed Postgres poolers (confirmed on Neon's pooled/PgBouncer
    # endpoint) hand out connections with an empty search_path instead of the
    # usual "$user",public default — unqualified table names then fail with
    # "relation does not exist" even though the tables exist in public. Force
    # it explicitly rather than relying on the server default.
    conn.execute("SET search_path TO public")
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    return conn


def ensure_schema_sync(conn: psycopg.Connection, *, dim: int) -> None:
    conn.execute(_schema_sql(dim))


def clear_table_sync(conn: psycopg.Connection) -> None:
    conn.execute(f"TRUNCATE TABLE {TABLE}")


def upsert_rows_sync(conn: psycopg.Connection, rows: list[dict]) -> None:
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (id, text, metadata, embedding)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                SET text = excluded.text,
                    metadata = excluded.metadata,
                    embedding = excluded.embedding
                """,
                (r["id"], r["text"], json.dumps(r["metadata"]), Vector(r["embedding"])),
            )


def count_rows_sync(conn: psycopg.Connection) -> int:
    return conn.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]


async def _configure_connection(conn: psycopg.AsyncConnection) -> None:
    # See the comment in get_sync_conn: some pooled Postgres endpoints (Neon's
    # PgBouncer-backed pooler, confirmed) don't guarantee "public" is on the
    # search_path for every connection handed out of the pool, even though the
    # role's default normally includes it — force it per-connection instead.
    # autocommit first: pool connections default to transactions-on, and a
    # bare SET without a commit leaves the connection INTRANS, which the pool
    # rejects as unhealthy right after configure() runs.
    await conn.set_autocommit(True)
    await conn.execute("SET search_path TO public")
    await register_vector_async(conn)


async def get_pool(database_url: str) -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        # Ensure the extension exists before opening the pool: the pool's
        # `configure` callback registers the vector type on every new
        # connection, which fails if `CREATE EXTENSION vector` hasn't run yet.
        async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as boot_conn:
            await boot_conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        pool = AsyncConnectionPool(database_url, open=False, configure=_configure_connection)
        # wait=True: fail fast with a clear PoolTimeout if the DB isn't reachable,
        # instead of returning before any connection is ready (first query would
        # then hang waiting on a connection that may never come).
        await pool.open(wait=True, timeout=10)
        _pool = pool
    return _pool


async def ensure_schema_async(database_url: str, *, dim: int) -> None:
    pool = await get_pool(database_url)
    async with pool.connection() as conn:
        await conn.execute(_schema_sql(dim))


async def count_rows_async(database_url: str) -> int:
    pool = await get_pool(database_url)
    async with pool.connection() as conn:
        row = await (await conn.execute(f"SELECT count(*) FROM {TABLE}")).fetchone()
        return row[0]


async def query_similar_async(
    database_url: str,
    embedding: list[float],
    k: int,
) -> list[dict]:
    vec = Vector(embedding)
    pool = await get_pool(database_url)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT id, text, metadata, embedding <=> %s AS distance
            FROM {TABLE}
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            (vec, vec, k),
        )
        rows = await cur.fetchall()
    return [
        {"id": row[0], "text": row[1], "metadata": row[2], "distance": row[3]}
        for row in rows
    ]
