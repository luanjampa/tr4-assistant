#!/usr/bin/env python3
"""Prints the most-repeated questions the knowledge base likely answered poorly.

Use this to decide what to research/ingest next (`tr4-sync --docs`/`--web-seeds`/
`--owner-notes`). No Groq/API needed — just reads tr4_gaps from Postgres.
"""

from __future__ import annotations

import asyncio

from tr4.config import get_settings
from tr4.gaps import top_gaps


async def main() -> None:
    settings = get_settings()
    gaps = await top_gaps(settings)
    if not gaps:
        print("Nenhuma pergunta mal respondida registrada ainda.")
        return

    print(f"{'#vezes':>7}  {'dist.média':>10}  {'última vez':<20}  pergunta")
    for g in gaps:
        dist = f"{g['avg_distance']:.3f}" if g["avg_distance"] is not None else "—"
        last = str(g["last_seen"])[:19]
        print(f"{g['count']:>7}  {dist:>10}  {last:<20}  {g['question']}")


if __name__ == "__main__":
    asyncio.run(main())
