"""Blocage interne (app) par contact + compte WhatsApp — sans Meta block_users."""
from __future__ import annotations

import logging
from typing import List, Optional

from app.core.db import supabase, supabase_execute
from app.core.pg import get_pool
from app.services.whatsapp_api_service import normalize_whatsapp_user_id

logger = logging.getLogger(__name__)

_TABLE_MISSING_LOGGED = False


class InternalBlocksTableNotMigrated(Exception):
    """Table `internal_contact_blocks` absente : appliquer `050_internal_contact_blocks.sql`."""


def _is_missing_blocks_table_error(exc: BaseException) -> bool:
    s = str(exc).lower()
    if "internal_contact_blocks" not in s:
        return False
    try:
        import asyncpg.exceptions

        if isinstance(exc, asyncpg.exceptions.UndefinedTableError):
            return True
    except ImportError:
        pass
    return "does not exist" in s or ("relation" in s and "not exist" in s)


def _warn_migration_once() -> None:
    global _TABLE_MISSING_LOGGED
    if not _TABLE_MISSING_LOGGED:
        _TABLE_MISSING_LOGGED = True
        logger.warning(
            "Table internal_contact_blocks absente : exécuter la migration "
            "supabase/migrations/050_internal_contact_blocks.sql sur la base Postgres."
        )


async def _pg_fetch_rows_for_blocks(query: str, *args) -> List[dict]:
    """fetch via le pool sans passer par pg.fetch_all (évite ERROR en log si table absente)."""
    pool = get_pool()
    if not pool:
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *args, timeout=30.0)
            return [dict(r) for r in rows]
    except Exception as e:
        if _is_missing_blocks_table_error(e):
            _warn_migration_once()
            return []
        raise


async def _pg_execute_block_table(query: str, *args) -> None:
    """INSERT/DELETE sur internal_contact_blocks sans logger ERROR pg si table absente."""
    pool = get_pool()
    if not pool:
        raise RuntimeError("PostgreSQL pool not available")
    try:
        async with pool.acquire() as conn:
            await conn.execute(query, *args, timeout=30.0)
    except Exception as e:
        if _is_missing_blocks_table_error(e):
            _warn_migration_once()
            raise InternalBlocksTableNotMigrated from e
        raise


async def is_internally_blocked(contact_id: Optional[str], account_id: Optional[str]) -> bool:
    if not contact_id or not account_id:
        return False
    if get_pool():
        row = await _pg_fetch_rows_for_blocks(
            """
            SELECT 1 FROM internal_contact_blocks
            WHERE contact_id = $1::uuid AND account_id = $2::uuid
            LIMIT 1
            """,
            contact_id,
            account_id,
        )
        return bool(row)
    try:
        res = await supabase_execute(
            supabase.table("internal_contact_blocks")
            .select("contact_id")
            .eq("contact_id", contact_id)
            .eq("account_id", account_id)
            .limit(1)
        )
    except Exception as e:
        if _is_missing_blocks_table_error(e):
            _warn_migration_once()
            return False
        raise
    return bool(res.data)


async def list_blocked_wa_ids_for_account(account_id: str) -> List[str]:
    """Liste des whatsapp_number normalisés (chiffres) pour GET /contacts/meta-blocked."""
    out: List[str] = []
    if get_pool():
        rows = await _pg_fetch_rows_for_blocks(
            """
            SELECT c.whatsapp_number
            FROM internal_contact_blocks b
            JOIN contacts c ON c.id = b.contact_id
            WHERE b.account_id = $1::uuid
            """,
            account_id,
        )
        for r in rows:
            raw = dict(r).get("whatsapp_number") if r is not None else None
            n = normalize_whatsapp_user_id(str(raw))
            if n:
                out.append(n)
        return out
    try:
        res = await supabase_execute(
            supabase.table("internal_contact_blocks")
            .select("contacts(whatsapp_number)")
            .eq("account_id", account_id)
        )
    except Exception as e:
        if _is_missing_blocks_table_error(e):
            _warn_migration_once()
            return []
        raise
    for row in res.data or []:
        nested = row.get("contacts") or {}
        wa = nested.get("whatsapp_number") if isinstance(nested, dict) else None
        if isinstance(wa, str):
            n = normalize_whatsapp_user_id(wa)
            if n:
                out.append(n)
    return out


async def upsert_internal_block(contact_id: str, account_id: str) -> None:
    async def _force_human_safe() -> None:
        """Sécurité : bloquer ⇒ mode humain (bot off) pour ce couple contact × compte."""
        try:
            from app.services.conversation_service import force_human_mode_for_contact_account

            await force_human_mode_for_contact_account(contact_id, account_id)
        except Exception:
            logger.warning(
                "Impossible de forcer le mode humain après blocage interne (contact=%s, account=%s)",
                contact_id,
                account_id,
                exc_info=True,
            )

    if get_pool():
        await _pg_execute_block_table(
            """
            INSERT INTO internal_contact_blocks (contact_id, account_id)
            VALUES ($1::uuid, $2::uuid)
            ON CONFLICT (contact_id, account_id) DO NOTHING
            """,
            contact_id,
            account_id,
        )
        await _force_human_safe()
        return
    try:
        await supabase_execute(
            supabase.table("internal_contact_blocks").upsert(
                {"contact_id": contact_id, "account_id": account_id},
                on_conflict="contact_id,account_id",
            )
        )
    except Exception as e:
        if _is_missing_blocks_table_error(e):
            _warn_migration_once()
            raise InternalBlocksTableNotMigrated from e
        raise
    await _force_human_safe()


async def remove_internal_block(contact_id: str, account_id: str) -> None:
    if get_pool():
        await _pg_execute_block_table(
            """
            DELETE FROM internal_contact_blocks
            WHERE contact_id = $1::uuid AND account_id = $2::uuid
            """,
            contact_id,
            account_id,
        )
        return
    try:
        await supabase_execute(
            supabase.table("internal_contact_blocks")
            .delete()
            .eq("contact_id", contact_id)
            .eq("account_id", account_id)
        )
    except Exception as e:
        if _is_missing_blocks_table_error(e):
            _warn_migration_once()
            raise InternalBlocksTableNotMigrated from e
        raise
