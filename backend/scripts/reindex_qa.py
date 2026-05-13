"""
Re-extract all Q&A pairs with improved embeddings (Q+R instead of Q only).
Deletes all auto-extracted pairs, then re-runs extraction.
Manual pairs are preserved.

Run: cd backend && python scripts/reindex_qa.py
"""
import asyncio
import json
import logging
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Auto-load env
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("reindex_qa")


async def main():
    from app.core.pg import init_pool, close_pool, fetch_all, execute
    from app.services.qa_service import extract_qa_from_conversations, count_qa_pairs

    await init_pool()

    accounts = await fetch_all("SELECT id, name FROM whatsapp_accounts ORDER BY name")
    logger.info("Found %d accounts", len(accounts))

    # Step 1: Delete all auto-extracted pairs (manual ones are kept)
    result = await execute("DELETE FROM qa_pairs WHERE source = 'auto'")
    logger.info("Deleted all auto-extracted Q&A pairs (%s)", result)

    # Step 2: Re-extract for each account
    total = 0
    for acc in accounts:
        aid = str(acc["id"])
        name = acc.get("name", "?")
        logger.info("---- %s ----", name)
        try:
            created = await extract_qa_from_conversations(aid, since_days=365)
            cnt = await count_qa_pairs(aid)
            logger.info("  -> %d created, %d total", created, cnt)
            total += created
        except Exception as exc:
            logger.error("  FAILED: %s", exc, exc_info=True)

    logger.info("==== Done. %d total Q&A pairs re-indexed ====", total)
    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
