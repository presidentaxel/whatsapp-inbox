"""
Réactions sur messages WhatsApp.

Extraction du gros `message_service.py` (cf. guide de bonnes pratiques §5.1
"Garder les routes minces / services testables"). Concentre :
- CRUD `message_reactions` côté DB
- relai vers l'API Cloud Meta
"""
from __future__ import annotations

import logging
from typing import Any, Dict

import httpx

from app.core.config import settings
from app.core.db import supabase, supabase_execute
from app.core.pg import execute, fetch_one, get_pool
from app.services.account_service import get_account_by_id
from app.services.conversation_service import get_conversation_by_id
from app.services.whatsapp_send import send_with_retry

logger = logging.getLogger(__name__)


async def add_reaction(message_id: str, emoji: str, from_number: str) -> Dict[str, Any]:
    """Ajoute une réaction à un message."""
    if get_pool():
        msg = await fetch_one(
            "SELECT id FROM messages WHERE id = $1::uuid LIMIT 1",
            message_id,
        )
        if not msg:
            return {"error": "message_not_found"}
        row = await fetch_one(
            """
            INSERT INTO message_reactions (message_id, emoji, from_number)
            VALUES ($1::uuid, $2, $3)
            ON CONFLICT (message_id, from_number, emoji) DO UPDATE SET emoji = EXCLUDED.emoji
            RETURNING *
            """,
            message_id,
            emoji,
            from_number,
        )
        return {"success": True, "reaction": dict(row) if row else None}

    message = await supabase_execute(
        supabase.table("messages")
        .select("id, wa_message_id, conversation_id")
        .eq("id", message_id)
        .limit(1)
    )
    if not message.data:
        return {"error": "message_not_found"}
    reaction = await supabase_execute(
        supabase.table("message_reactions").upsert(
            {"message_id": message_id, "emoji": emoji, "from_number": from_number},
            on_conflict="message_id,from_number,emoji",
        )
    )
    return {"success": True, "reaction": reaction.data[0] if reaction.data else None}


async def remove_reaction(message_id: str, emoji: str, from_number: str) -> Dict[str, Any]:
    """Supprime une réaction d'un message."""
    if get_pool():
        msg = await fetch_one(
            "SELECT id FROM messages WHERE id = $1::uuid LIMIT 1", message_id
        )
        if not msg:
            return {"error": "message_not_found"}
        await execute(
            "DELETE FROM message_reactions WHERE message_id = $1::uuid AND emoji = $2 AND from_number = $3",
            message_id,
            emoji,
            from_number,
        )
        return {"success": True}

    message = await supabase_execute(
        supabase.table("messages").select("id").eq("id", message_id).limit(1)
    )
    if not message.data:
        return {"error": "message_not_found"}
    await supabase_execute(
        supabase.table("message_reactions")
        .delete()
        .eq("message_id", message_id)
        .eq("emoji", emoji)
        .eq("from_number", from_number)
    )
    return {"success": True}


async def send_reaction_to_whatsapp(
    conversation_id: str,
    target_wa_message_id: str,
    emoji: str,
) -> Dict[str, Any]:
    """
    Envoie une réaction via l'API WhatsApp.

    Args:
        conversation_id: ID de la conversation
        target_wa_message_id: ID WhatsApp du message cible
        emoji: Emoji de la réaction (vide pour supprimer)

    Returns:
        Dict avec le résultat de l'envoi
    """
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        return {"error": "conversation_not_found"}

    account = await get_account_by_id(conversation["account_id"])
    if not account:
        return {"error": "account_not_found"}

    phone_id = account.get("phone_number_id") or settings.WHATSAPP_PHONE_ID
    token = account.get("access_token") or settings.WHATSAPP_TOKEN

    if not phone_id or not token:
        return {"error": "whatsapp_not_configured"}

    body = {
        "messaging_product": "whatsapp",
        "to": conversation["client_number"],
        "type": "reaction",
        "reaction": {
            "message_id": target_wa_message_id,
            "emoji": emoji,
        },
    }

    try:
        response = await send_with_retry(phone_id, token, body)
    except httpx.HTTPError as exc:
        logger.error("WhatsApp reaction API error: %s", exc)
        return {"error": "whatsapp_api_error", "details": str(exc)}

    if response.is_error:
        logger.error(
            "WhatsApp reaction error: %s %s", response.status_code, response.text
        )
        return {
            "error": "whatsapp_api_error",
            "status_code": response.status_code,
            "details": response.text,
        }

    response_json = response.json()
    wa_message_id = response_json.get("messages", [{}])[0].get("id")
    return {"success": True, "wa_message_id": wa_message_id}
