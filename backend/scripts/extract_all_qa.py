"""
Extract Q&A pairs from human operator conversations for ALL accounts.

Usage (from project root):
  cd backend && python scripts/extract_all_qa.py          # incremental
  cd backend && python scripts/extract_all_qa.py --purge  # delete old auto-pairs, re-extract fresh
"""
import asyncio
import json
import logging
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8")

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
logger = logging.getLogger("extract_all_qa")

PURGE = "--purge" in sys.argv


async def main():
    from app.core.pg import init_pool, close_pool, fetch_all, execute
    from app.services.qa_service import extract_qa_from_conversations, count_qa_pairs

    await init_pool()

    if PURGE:
        deleted = await execute(
            "DELETE FROM qa_pairs WHERE source = 'auto'"
        )
        logger.info("PURGE: deleted all auto-extracted Q&A pairs")

    accounts = await fetch_all(
        "SELECT id, name FROM whatsapp_accounts ORDER BY name"
    )
    if not accounts:
        logger.error("No accounts found in whatsapp_accounts")
        await close_pool()
        return

    logger.info("Found %d accounts to process", len(accounts))
    total_created = 0

    for acc in accounts:
        aid = str(acc["id"])
        name = acc.get("name", "?")
        logger.info("---- Processing: %s (%s) ----", name, aid)
        try:
            created = await extract_qa_from_conversations(aid, since_days=365)
            count = await count_qa_pairs(aid)
            logger.info(
                "  -> %d new pairs created, %d total in DB for this account",
                created, count,
            )
            total_created += created
        except Exception as exc:
            logger.error("  FAILED for %s: %s", name, exc, exc_info=True)

    logger.info("==== Done. %d new Q&A pairs created across all accounts ====", total_created)
    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
