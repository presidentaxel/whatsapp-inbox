from app.core.db import supabase


async def list_contacts():
    res = (
        supabase.table("contacts")
        .select("id, whatsapp_number, display_name, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return res.data

