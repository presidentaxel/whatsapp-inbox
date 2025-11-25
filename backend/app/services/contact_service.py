from app.core.db import supabase, supabase_execute


async def list_contacts():
    res = await supabase_execute(
        supabase.table("contacts")
        .select("id, whatsapp_number, display_name, created_at")
        .order("created_at", desc=True)
    )
    return res.data

