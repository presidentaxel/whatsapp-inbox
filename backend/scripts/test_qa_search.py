"""
Test interactif du RAG Q&A.
Lancer depuis la racine du projet :

  cd backend
  python scripts/test_qa_search.py
"""
import asyncio
import os
import sys
import subprocess
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8")

# Auto-load env from docker compose config if not already set
if not os.environ.get("DATABASE_URL"):
    try:
        root = os.path.join(os.path.dirname(__file__), "..", "..")
        raw = subprocess.check_output(
            ["docker", "compose", "config", "--format", "json"],
            cwd=root, stderr=subprocess.DEVNULL,
        )
        cfg = json.loads(raw)
        env = cfg.get("services", {}).get("backend", {}).get("environment", {})
        for k in ["DATABASE_URL", "SUPABASE_URL", "SUPABASE_KEY", "GEMINI_API_KEY", "GEMINI_MODEL"]:
            if env.get(k):
                os.environ.setdefault(k, env[k])
    except Exception:
        pass

import logging
logging.basicConfig(level=logging.WARNING)

ACCOUNTS = {}

async def load_accounts():
    from app.core.pg import fetch_all
    from app.services.qa_service import count_qa_pairs
    rows = await fetch_all("SELECT id, name FROM whatsapp_accounts ORDER BY name")
    for i, r in enumerate(rows):
        aid = str(r["id"])
        name = r.get("name", "?")
        cnt = await count_qa_pairs(aid)
        if cnt > 0:
            key = str(i + 1)
            ACCOUNTS[key] = (aid, name, cnt)


async def main():
    from app.core.pg import init_pool, close_pool
    from app.services.qa_service import search_similar_qa, format_qa_context

    await init_pool()
    await load_accounts()

    if not ACCOUNTS:
        print("Aucun compte avec des Q&A en base.")
        await close_pool()
        return

    print("\n╔══════════════════════════════════════════╗")
    print("║     Test RAG Q&A - Mode interactif       ║")
    print("╚══════════════════════════════════════════╝\n")
    print("Comptes disponibles :\n")
    for key, (aid, name, cnt) in ACCOUNTS.items():
        print(f"  [{key}] {name}  ({cnt} Q&A)")

    print()
    choice = input("Choisis un numéro : ").strip()
    if choice not in ACCOUNTS:
        print("Choix invalide.")
        await close_pool()
        return

    account_id, account_name, _ = ACCOUNTS[choice]
    print(f"\n→ {account_name}")
    print("Tape une question client puis Entrée. (quit pour sortir)\n")

    while True:
        try:
            query = input("💬 Question > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not query or query.lower() in ("quit", "exit", "q"):
            break

        results = await search_similar_qa(account_id, query, limit=5)

        if not results:
            print("  ❌ Aucun résultat.\n")
            continue

        print()
        for i, r in enumerate(results):
            sim = r.get("similarity", 0)
            q = (r.get("question") or "").strip()
            a = (r.get("answer") or "").strip()
            if len(q) > 120:
                q = q[:117] + "..."
            if len(a) > 200:
                a = a[:197] + "..."
            bar = "█" * int(sim * 20) + "░" * (20 - int(sim * 20))
            print(f"  [{i+1}] {bar} {sim:.1%}")
            print(f"      Q: {q}")
            print(f"      R: {a}")
            print()

        block = format_qa_context(results)
        print("  ┌─── Ce bloc sera injecté dans le prompt Gemini ───┐")
        for line in block.strip().split("\n"):
            print(f"  │ {line}")
        print("  └──────────────────────────────────────────────────┘\n")

    await close_pool()
    print("\nBye !")


if __name__ == "__main__":
    asyncio.run(main())
