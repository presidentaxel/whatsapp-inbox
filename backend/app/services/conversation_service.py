from typing import Optional

from app.core.cache import cached, invalidate_cache_pattern
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
        .select("*, contacts(display_name, whatsapp_number, profile_picture_url)")
        .eq("account_id", account_id)
        .order("updated_at", desc=True)
    )
    if cursor:
        query = query.lt("updated_at", cursor)
    query = query.limit(limit)
    res = await supabase_execute(query)
    conversations = res.data
    
    if not conversations:
        return []
    
    # Récupérer le dernier message de chaque conversation
    conversation_ids = [c["id"] for c in conversations]
    
    # Récupérer tous les messages récents (en excluant les réactions) et filtrer en Python
    # On récupère plus de messages que nécessaire pour s'assurer d'avoir le dernier de chaque conversation
    messages_query = (
        supabase.table("messages")
        .select("conversation_id, content_text, message_type, timestamp")
        .in_("conversation_id", conversation_ids)
        .neq("message_type", "reaction")
        .order("timestamp", desc=True)
        .limit(1000)  # Limite généreuse pour couvrir toutes les conversations
    )
    messages_res = await supabase_execute(messages_query)
    all_messages = messages_res.data if messages_res.data else []
    
    # Grouper par conversation_id et prendre le premier (le plus récent)
    last_messages_map = {}
    seen_conversations = set()
    for msg in all_messages:
        conv_id = msg["conversation_id"]
        if conv_id not in seen_conversations:
            last_messages_map[conv_id] = msg
            seen_conversations.add(conv_id)
    
    # Fusionner les derniers messages avec les conversations
    for conv in conversations:
        last_msg = last_messages_map.get(conv["id"])
        if last_msg:
            # Formater le texte du dernier message selon le type
            if last_msg.get("message_type") == "text":
                content = last_msg.get("content_text", "") or ""
                # Tronquer à 60 caractères pour l'affichage mobile
                conv["last_message"] = content[:60] + "..." if len(content) > 60 else content
            elif last_msg.get("message_type") == "image":
                conv["last_message"] = "[image]"
            elif last_msg.get("message_type") == "video":
                conv["last_message"] = "[video]"
            elif last_msg.get("message_type") == "audio":
                conv["last_message"] = "[audio]"
            elif last_msg.get("message_type") == "document":
                conv["last_message"] = "[document]"
            elif last_msg.get("message_type") == "location":
                conv["last_message"] = "[location]"
            elif last_msg.get("message_type") == "contacts":
                conv["last_message"] = "[contact]"
            elif last_msg.get("message_type") == "interactive":
                conv["last_message"] = "[interactive]"
            else:
                content = last_msg.get("content_text", "") or ""
                # Tronquer à 60 caractères pour l'affichage mobile
                conv["last_message"] = content[:60] + "..." if len(content) > 60 else content
        else:
            conv["last_message"] = ""
    
    return conversations


async def mark_conversation_read(conversation_id: str) -> bool:
    await supabase_execute(
        supabase.table("conversations").update({"unread_count": 0}).eq("id", conversation_id)
    )
    # Invalider le cache pour forcer le rechargement
    await invalidate_cache_pattern(f"conversation:{conversation_id}")
    return True


async def set_conversation_favorite(conversation_id: str, favorite: bool) -> bool:
    await supabase_execute(
        supabase.table("conversations").update({"is_favorite": favorite}).eq("id", conversation_id)
    )
    # Invalider le cache pour forcer le rechargement
    await invalidate_cache_pattern(f"conversation:{conversation_id}")
    return True


@cached(ttl_seconds=60, key_prefix="conversation")
async def get_conversation_by_id(conversation_id: str) -> Optional[dict]:
    """
    Récupère une conversation avec cache (1 min TTL).
    Les conversations changent peu fréquemment.
    """
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
    # CRUCIAL: Invalider le cache immédiatement pour que les webhooks voient le changement
    await invalidate_cache_pattern(f"conversation:{conversation_id}")
    
    updated = await supabase_execute(
        supabase.table("conversations").select("*").eq("id", conversation_id).limit(1)
    )
    if not updated.data:
        return None
    return updated.data[0]