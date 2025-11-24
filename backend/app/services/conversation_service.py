from typing import Optional

from app.core.db import supabase
from app.services.account_service import get_account_by_id


async def get_all_conversations(account_id: str) -> Optional[list]:
    account = get_account_by_id(account_id)
    if not account:
        return None

    res = (
        supabase.table("conversations")
        .select("*, contacts(display_name, whatsapp_number)")
        .eq("account_id", account_id)
        .order("updated_at", desc=True)
        .execute()
    )
    return res.data


async def mark_conversation_read(conversation_id: str) -> bool:
    supabase.table("conversations").update({"unread_count": 0}).eq("id", conversation_id).execute()
    return True


async def set_conversation_favorite(conversation_id: str, favorite: bool) -> bool:
    supabase.table("conversations").update({"is_favorite": favorite}).eq("id", conversation_id).execute()
    return True


async def get_conversation_by_id(conversation_id: str) -> Optional[dict]:
    res = (
        supabase.table("conversations")
        .select("*")
        .eq("id", conversation_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]
