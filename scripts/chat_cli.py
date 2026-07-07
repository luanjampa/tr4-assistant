#!/usr/bin/env python3
"""Interactive local CLI to chat with a running TR4 API. Dev tool, not part of the package."""

from __future__ import annotations

import os

import httpx

BASE = os.environ.get("TR4_API_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("TR4_API_KEY", "")


def main() -> None:
    headers = {"X-API-Key": API_KEY} if API_KEY else {}

    try:
        resp = httpx.get(f"{BASE}/terms", timeout=10.0)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"Não consegui conectar em {BASE} — a API está rodando (`make api`)? Detalhe: {e}")
        return

    print(resp.json()["terms"])
    print()
    if input("Aceita os termos? [s/N] ").strip().lower() != "s":
        print("Sem aceite, encerrando.")
        return

    print("\nPergunte sobre TR4 ('sair' ou Ctrl+C pra encerrar).\n")
    while True:
        try:
            msg = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not msg or msg.lower() in ("sair", "exit", "quit"):
            break

        try:
            resp = httpx.post(
                f"{BASE}/chat",
                headers=headers,
                json={"message": msg, "accepted_terms": True},
                timeout=60.0,
            )
        except httpx.HTTPError as e:
            print(f"[erro de conexão] {e}\n")
            continue

        if resp.status_code != 200:
            print(f"[erro {resp.status_code}] {resp.text}\n")
            continue

        data = resp.json()
        print(f"\n{data['reply']}\n")
        print(f"({data['disclaimer']})\n")


if __name__ == "__main__":
    main()
