"""
Re-embed all Q&A pairs with the new Q+A combined strategy.
Also cleans up low-quality pairs.
Run: cd backend && python scripts/reembed_all_qa.py
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
logger = logging.getLogger("reembed")


async def main():
    from app.core.pg import init_pool, close_pool, fetch_all
    from app.services.qa_service import reembed_all, count_qa_pairs

    await init_pool()

    accounts = await fetch_all("SELECT id, name FROM whatsapp_accounts ORDER BY name")
    logger.info("Found %d accounts", len(accounts))

    total_updated = 0
    for acc in accounts:
        aid = str(acc["id"])
        name = acc.get("name", "?")
        cnt = await count_qa_pairs(aid)
        if cnt == 0:
            continue
        logger.info("---- %s (%d pairs) ----", name, cnt)
        updated = await reembed_all(aid)
        total_updated += updated
        new_cnt = await count_qa_pairs(aid)
        logger.info("  -> %d re-embedded, %d remaining after cleanup", updated, new_cnt)

    logger.info("==== Done. %d pairs re-embedded total ====", total_updated)
    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
