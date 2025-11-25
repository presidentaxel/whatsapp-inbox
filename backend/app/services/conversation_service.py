from typing import Optional

from app.core.db import supabase, supabase_execute
from app.services.account_service import get_account_by_id


async def get_all_conversations(
    account_id: str,
    limit: int = 50,
    cursor: Optional[str] = None,
) -> Optional[list]:
    account = await get_account_by_id(account_id)
    if not account:
        return None

    query = (
        supabase.table("conversations")
        .select("*, contacts(display_name, whatsapp_number)")
        .eq("account_id", account_id)
        .order("updated_at", desc=True)
    )
    if cursor:
        query = query.lt("updated_at", cursor)
    query = query.limit(limit)
    res = await supabase_execute(query)
    return res.data


async def mark_conversation_read(conversation_id: str) -> bool:
    await supabase_execute(
        supabase.table("conversations").update({"unread_count": 0}).eq("id", conversation_id)
    )
    return True


async def set_conversation_favorite(conversation_id: str, favorite: bool) -> bool:
    await supabase_execute(
        supabase.table("conversations").update({"is_favorite": favorite}).eq("id", conversation_id)
    )
    return True


async def get_conversation_by_id(conversation_id: str) -> Optional[dict]:
    res = await supabase_execute(
        supabase.table("conversations").select("*").eq("id", conversation_id).limit(1)
    )
    if not res.data:
        return None
    return res.data[0]


async def set_conversation_bot_mode(conversation_id: str, enabled: bool) -> Optional[dict]:
    await supabase_execute(
        supabase.table("conversations").update({"bot_enabled": enabled}).eq("id", conversation_id)
    )
    updated = await supabase_execute(
        supabase.table("conversations").select("*").eq("id", conversation_id).limit(1)
    )
    if not updated.data:
        return None
    return updated.data[0]