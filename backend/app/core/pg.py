"""
Pool PostgreSQL asynchrone (asyncpg) pour requêtes directes.

Quand DATABASE_URL est défini, ce module fournit un pool de connexions
utilisé par les services pour éviter l'API Supabase (PostgREST) et réduire
la latence / le blocage entre requêtes.
"""
import logging
from typing import Any, List, Optional
from urllib.parse import urlparse

from app.core.config import settings

logger = logging.getLogger(__name__)

_pool: Any = None


def _safe_url_for_log(url: str) -> str:
    """Retourne l'URL avec mot de passe masqué (pour les logs)."""
    try:
        p = urlparse(url)
        netloc = f"{p.hostname or ''}" + (f":{p.port}" if p.port else "")
        return f"{p.scheme}://{p.username or '***'}:***@{netloc}{p.path or '/'}"
    except Exception:
        return "(invalid url)"


async def init_pool() -> None:
    """Crée le pool PostgreSQL au démarrage de l'app (si DATABASE_URL est défini)."""
    global _pool
    if not settings.DATABASE_URL:
        logger.info("DATABASE_URL not set, skipping PostgreSQL pool init")
        return
    url_safe = _safe_url_for_log(settings.DATABASE_URL)
    logger.info("Initializing PostgreSQL pool: %s", url_safe)
    try:
        import asyncpg
        _pool = await asyncpg.create_pool(
            settings.DATABASE_URL,
            min_size=5,
            max_size=20,
            command_timeout=30,
        )
        logger.info("PostgreSQL pool created (min=5, max=20)")
    except Exception as e:
        exc_type = type(e).__name__
        exc_msg = str(e)
        logger.warning(
            "Failed to create PostgreSQL pool: %s (%s): %s. Falling back to Supabase API.",
            exc_type,
            getattr(e, "errno", "—"),
            exc_msg,
        )
        if "getaddrinfo failed" in exc_msg or (getattr(e, "errno", None) == 11001):
            host = urlparse(settings.DATABASE_URL).hostname if settings.DATABASE_URL else "?"
            logger.warning(
                "DNS resolution failed for host %r.",
                host,
            )
            if host and host.startswith("db.") and host.endswith(".supabase.co"):
                logger.warning(
                    "You are using Supabase *direct* connection (db.xxx.supabase.co). "
                    "Use the *pooler* URL instead: Supabase Dashboard → Project Settings → Database → "
                    "Connection string → 'Connection pooling' / Session or Transaction mode "
                    "(host like aws-0-<region>.pooler.supabase.com, port 6543)."
                )
            else:
                logger.warning(
                    "Check: 1) hostname typo in DATABASE_URL, 2) network/VPN/firewall."
                )
        logger.warning("PostgreSQL pool init failed (traceback below)", exc_info=True)
        _pool = None


async def close_pool() -> None:
    """Ferme le pool au shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL pool closed")


def get_pool():
    """Retourne le pool ou None si PostgreSQL direct n'est pas configuré."""
    return _pool


async def fetch_one(
    query: str,
    *args,
    timeout: float = 30.0,
) -> Optional[dict]:
    """
    Exécute une requête SELECT et retourne une seule ligne comme dict, ou None.
    """
    pool = get_pool()
    if not pool:
        return None
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, *args, timeout=timeout)
            return dict(row) if row else None
    except Exception as e:
        logger.error("pg fetch_one error: %s", e, exc_info=True)
        raise


async def fetch_all(
    query: str,
    *args,
    timeout: float = 30.0,
) -> List[dict]:
    """
    Exécute une requête SELECT et retourne toutes les lignes comme list[dict].
    """
    pool = get_pool()
    if not pool:
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *args, timeout=timeout)
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("pg fetch_all error: %s", e, exc_info=True)
        raise


async def execute(
    query: str,
    *args,
    timeout: float = 30.0,
) -> str:
    """
    Exécute une requête INSERT/UPDATE/DELETE. Retourne le status du dernier résultat.
    """
    pool = get_pool()
    if not pool:
        raise RuntimeError("PostgreSQL pool not available")
    try:
        async with pool.acquire() as conn:
            await conn.execute(query, *args, timeout=timeout)
            return "OK"
    except Exception as e:
        logger.error("pg execute error: %s", e, exc_info=True)
        raise
