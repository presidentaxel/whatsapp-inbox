from app.core.db import supabase, supabase_execute
from app.core.pg import fetch_all, get_pool


async def list_contacts():
    if get_pool():
        rows = await fetch_all(
            """
            SELECT id, whatsapp_number, display_name, profile_picture_url, whatsapp_name, whatsapp_info_fetched_at, created_at
            FROM contacts
            ORDER BY created_at DESC
            """
        )
        return rows
    res = await supabase_execute(
        supabase.table("contacts")
        .select("id, whatsapp_number, display_name, profile_picture_url, whatsapp_name, whatsapp_info_fetched_at, created_at")
        .order("created_at", desc=True)
    )
    return res.data or []

