from typing import Optional

from app.core.db import supabase, supabase_execute
from app.core.pg import fetch_all, fetch_one, get_pool


async def list_contacts(limit: int = 200, offset: int = 0):
    if get_pool():
        rows = await fetch_all(
            """
            SELECT id, whatsapp_number, display_name, profile_picture_url, whatsapp_name, whatsapp_info_fetched_at, created_at
            FROM contacts
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
        return [dict(r) for r in rows]
    res = await supabase_execute(
        supabase.table("contacts")
        .select("id, whatsapp_number, display_name, profile_picture_url, whatsapp_name, whatsapp_info_fetched_at, created_at")
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    return res.data or []


async def count_contacts() -> int:
    if get_pool():
        row = await fetch_one("SELECT count(*)::int AS cnt FROM contacts")
        return row["cnt"] if row else 0
    res = await supabase_execute(
        supabase.table("contacts").select("id", count="exact")
    )
    return res.count if hasattr(res, "count") and res.count is not None else len(res.data or [])

