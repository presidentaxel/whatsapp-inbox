import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.db import supabase, supabase_execute
from app.core.http_client import get_http_client, get_http_client_for_media
from app.core.retry import retry_on_network_error
from app.services import bot_service
from app.services.account_service import (
    get_account_by_id,
    get_account_by_phone_number_id,
)
from app.services.conversation_service import get_conversation_by_id, set_conversation_bot_mode
from app.services.profile_picture_service import queue_profile_picture_update

logger = logging.getLogger("uvicorn.error").getChild("bot.message")
logger.setLevel(logging.INFO)

FALLBACK_MESSAGE = "Je me renseigne auprès d’un collègue et je reviens vers vous au plus vite."

logger = logging.getLogger(__name__)


async def handle_incoming_message(data: dict):
    """
    Parse le webhook WhatsApp Cloud API et stocke les messages + statuts.
    """
    print("Webhook received:", data)

    for entry in data.get("entry", []):
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            metadata = value.get("metadata", {})
            account = await get_account_by_phone_number_id(metadata.get("phone_number_id"))
            if not account:
                print("Unknown account for payload; skipping", metadata)
                continue

            contacts_map = {c.get("wa_id"): c for c in value.get("contacts", []) if c.get("wa_id")}
            
            # Debug: Afficher les informations de contact disponibles dans le webhook
            if contacts_map:
                logger.debug("📋 Contacts in webhook:")
                for wa_id, contact_info in contacts_map.items():
                    profile = contact_info.get("profile", {})
                    logger.debug(f"  {wa_id}: name={profile.get('name')}, profile_data={json.dumps(profile)}")

            for message in value.get("messages", []):
                await _process_incoming_message(account["id"], message, contacts_map)

            for status in value.get("statuses", []):
                await _process_status(status, account)

    return True


async def _process_incoming_message(
    account_id: str, message: Dict[str, Any], contacts_map: Dict[str, Any]
):
    wa_id = message.get("from")
    if not wa_id:
        return

    contact_info = contacts_map.get(wa_id, {})
    profile_name = (
        contact_info.get("profile", {}).get("name")
        if isinstance(contact_info.get("profile"), dict)
        else None
    )
    
    # Essayer de récupérer l'image de profil depuis les données du webhook
    # Note: WhatsApp ne fournit généralement pas l'image directement dans le webhook
    profile_picture_url = None
    if isinstance(contact_info.get("profile"), dict):
        profile_picture_url = contact_info.get("profile", {}).get("profile_picture_url")
        if profile_picture_url:
            logger.info(f"📸 Profile picture found in webhook for {wa_id}")

    timestamp_iso = _timestamp_to_iso(message.get("timestamp"))
    contact = await _upsert_contact(wa_id, profile_name, profile_picture_url)
    conversation = await _upsert_conversation(account_id, contact["id"], wa_id, timestamp_iso)
    
    # Mettre à jour l'image de profil en arrière-plan si pas déjà disponible
    # Note: WhatsApp ne fournit généralement pas l'image dans les webhooks,
    # donc on essaie de la récupérer via l'API en arrière-plan
    if not profile_picture_url:
        logger.info(f"🔄 Queuing profile picture update for contact {contact['id']} ({wa_id})")
        try:
            # Utiliser create_task pour ne pas bloquer
            task = asyncio.create_task(
                queue_profile_picture_update(
                    contact_id=contact["id"],
                    whatsapp_number=wa_id,
                    account_id=account_id,
                    priority=True  # Priorité pour les nouveaux messages
                )
            )
            # Ne pas attendre la tâche, laisser tourner en arrière-plan
            # Ajouter un callback pour logger les erreurs sans bloquer
            def log_result(t):
                if t.exception() is None:
                    logger.debug(f"✅ Profile picture update queued for {wa_id}")
                else:
                    logger.warning(f"❌ Profile picture update failed for {wa_id}: {t.exception()}")
            task.add_done_callback(log_result)
        except Exception as e:
            # Ne pas faire échouer le traitement du message si la mise à jour de l'image échoue
            logger.warning(f"❌ Failed to queue profile picture update for {wa_id}: {e}", exc_info=True)
    msg_type_raw = message.get("type")
    msg_type = msg_type_raw.lower() if isinstance(msg_type_raw, str) else msg_type_raw

    # Les réactions sont traitées différemment - elles sont stockées dans message_reactions
    if msg_type == "reaction":
        reaction_data = message.get("reaction", {})
        target_message_id = reaction_data.get("message_id")
        emoji = reaction_data.get("emoji", "")
        
        if not target_message_id or not emoji:
            logger.warning("Invalid reaction data: %s", reaction_data)
            return
        
        # Trouver le message cible par son wa_message_id
        target_message = await supabase_execute(
            supabase.table("messages")
            .select("id")
            .eq("wa_message_id", target_message_id)
            .limit(1)
        )
        
        if not target_message.data:
            logger.warning("Target message not found for reaction: %s", target_message_id)
            return
        
        target_msg_id = target_message.data[0]["id"]
        
        # Si emoji est vide, c'est une suppression de réaction
        if not emoji or emoji == "":
            # Supprimer la réaction existante
            await supabase_execute(
                supabase.table("message_reactions")
                .delete()
                .eq("message_id", target_msg_id)
                .eq("from_number", wa_id)
            )
        else:
            # Ajouter ou mettre à jour la réaction
            await supabase_execute(
                supabase.table("message_reactions").upsert(
                    {
                        "message_id": target_msg_id,
                        "wa_message_id": message.get("id"),
                        "emoji": emoji,
                        "from_number": wa_id,
                    },
                    on_conflict="message_id,from_number,emoji",
                )
            )
        
        # Les réactions ne mettent pas à jour le timestamp de conversation ni le unread_count
        # et ne déclenchent pas le bot
        return

    content_text = _extract_content_text(message)
    media_meta = _extract_media_metadata(message)

    # Insérer le message d'abord pour obtenir son ID
    message_result = await supabase_execute(
        supabase.table("messages").upsert(
            {
                "conversation_id": conversation["id"],
                "direction": "inbound",
                "content_text": content_text,
                "timestamp": timestamp_iso,
                "wa_message_id": message.get("id"),
                "message_type": msg_type,
                "status": "received",
                "media_id": media_meta.get("media_id"),
                "media_mime_type": media_meta.get("media_mime_type"),
                "media_filename": media_meta.get("media_filename"),
            },
            on_conflict="wa_message_id",
        ).select("id")
    )
    
    # Récupérer l'ID du message inséré
    inserted_message = message_result.data[0] if message_result.data else None
    message_db_id = inserted_message.get("id") if inserted_message else None

    # Si c'est un média, télécharger et stocker dans Supabase Storage en arrière-plan
    if message_db_id and media_meta.get("media_id") and msg_type in ("image", "video", "audio", "document", "sticker"):
        logger.info(f"📥 Media detected: message_id={message_db_id}, media_id={media_meta.get('media_id')}, type={msg_type}")
        # Récupérer l'account pour le token
        account = await get_account_by_id(account_id)
        if account:
            logger.info(f"✅ Account found, starting async media download for message_id={message_db_id}")
            asyncio.create_task(_download_and_store_media_async(
                message_db_id=message_db_id,
                media_id=media_meta.get("media_id"),
                account=account,
                mime_type=media_meta.get("media_mime_type"),
                filename=media_meta.get("media_filename")
            ))
        else:
            logger.warning(f"❌ Account not found for account_id={account_id}, cannot download media")

    await _update_conversation_timestamp(conversation["id"], timestamp_iso)
    await _increment_unread_count(conversation)

    await _maybe_trigger_bot_reply(conversation["id"], content_text, contact, message.get("type"))


async def _process_status(status_payload: Dict[str, Any], account: Dict[str, Any]):
    message_id = status_payload.get("id")
    status_value = status_payload.get("status")
    recipient_id = status_payload.get("recipient_id")
    timestamp_iso = _timestamp_to_iso(status_payload.get("timestamp"))

    if not message_id or not status_value:
        return

    existing = await supabase_execute(
        supabase.table("messages")
        .select("id, conversation_id")
        .eq("wa_message_id", message_id)
        .limit(1)
    )

    if existing.data:
        record = existing.data[0]
        await supabase_execute(
            supabase.table("messages")
            .update({"status": status_value, "timestamp": timestamp_iso})
            .eq("id", record["id"])
        )
        await _update_conversation_timestamp(record["conversation_id"], timestamp_iso)
        return

    if not recipient_id or not account:
        return

    conversation = await supabase_execute(
        supabase.table("conversations")
        .select("id")
        .eq("account_id", account.get("id"))
        .eq("client_number", recipient_id)
        .limit(1)
    )

    if conversation.data:
        conv = conversation.data[0]
    else:
        contact = await _upsert_contact(recipient_id, None, None)
        conv = await _upsert_conversation(account["id"], contact["id"], recipient_id, timestamp_iso)

    await supabase_execute(
        supabase.table("messages").upsert(
            {
                "conversation_id": conv["id"],
                "direction": "outbound",
                "content_text": "[status update]",
                "timestamp": timestamp_iso,
                "wa_message_id": message_id,
                "message_type": status_payload.get("type") or "status",
                "status": status_value,
            },
            on_conflict="wa_message_id",
        )
    )
    await _update_conversation_timestamp(conv["id"], timestamp_iso)


async def _upsert_contact(
    wa_id: str, 
    profile_name: Optional[str],
    profile_picture_url: Optional[str] = None
):
    """
    Crée ou met à jour un contact avec son nom et son image de profil
    """
    payload = {"whatsapp_number": wa_id}
    if profile_name:
        payload["display_name"] = profile_name
    if profile_picture_url:
        payload["profile_picture_url"] = profile_picture_url

    res = await supabase_execute(
        supabase.table("contacts").upsert(payload, on_conflict="whatsapp_number")
    )
    return res.data[0]


async def _upsert_conversation(
    account_id: str, contact_id: str, client_number: str, timestamp_iso: str
):
    res = await supabase_execute(
        supabase.table("conversations").upsert(
            {
                "contact_id": contact_id,
                "client_number": client_number,
                "account_id": account_id,
                "status": "open",
                "updated_at": timestamp_iso,
            },
            on_conflict="account_id,client_number",
        )
    )
    return res.data[0]


def _extract_content_text(message: Dict[str, Any]) -> str:
    msg_type = message.get("type")
    if isinstance(msg_type, str):
        msg_type = msg_type.lower()

    if msg_type == "text":
        return message.get("text", {}).get("body", "")

    if msg_type == "interactive":
        interactive = message.get("interactive", {})
        if interactive.get("type") == "button_reply":
            return interactive.get("button_reply", {}).get("title", "")
        if interactive.get("type") == "list_reply":
            return interactive.get("list_reply", {}).get("title", "")

    if msg_type == "image":
        caption = message.get("image", {}).get("caption")
        return caption or "[image]"

    if msg_type == "audio":
        return "[audio]"

    if msg_type == "document":
        caption = message.get("document", {}).get("caption")
        return caption or "[document]"

    if msg_type == "reaction":
        # Les réactions sont gérées séparément dans _process_incoming_message
        # Ne pas retourner de contenu texte pour les réactions
        return ""

    # fallback: conserver la totalité du payload
    return json.dumps(message)


def _timestamp_to_iso(raw_ts: Optional[str]) -> str:
    if raw_ts:
        try:
            return datetime.fromtimestamp(int(raw_ts), tz=timezone.utc).isoformat()
        except (ValueError, TypeError):
            pass

    return datetime.now(timezone.utc).isoformat()


async def _update_conversation_timestamp(conversation_id: str, timestamp_iso: Optional[str] = None):
    await supabase_execute(
        supabase.table("conversations")
        .update({"updated_at": timestamp_iso or datetime.now(timezone.utc).isoformat()})
        .eq("id", conversation_id)
    )
    # Invalider le cache pour garantir la cohérence
    from app.core.cache import invalidate_cache_pattern
    await invalidate_cache_pattern(f"conversation:{conversation_id}")


async def _increment_unread_count(conversation: Dict[str, Any]):
    current = conversation.get("unread_count") or 0
    new_value = current + 1
    await supabase_execute(
        supabase.table("conversations").update({"unread_count": new_value}).eq(
            "id", conversation["id"]
        )
    )
    conversation["unread_count"] = new_value
    # Invalider le cache pour garantir la cohérence
    from app.core.cache import invalidate_cache_pattern
    await invalidate_cache_pattern(f"conversation:{conversation['id']}")


async def _maybe_trigger_bot_reply(
    conversation_id: str,
    content_text: Optional[str],
    contact: Dict[str, Any],
    message_type: Optional[str] = "text",
):
    message_text = (content_text or "").strip()
    if not message_text:
        logger.info("Bot skip: empty message for %s", conversation_id)
        return

    conversation = await get_conversation_by_id(conversation_id)
    if not conversation or not conversation.get("bot_enabled"):
        logger.info(
            "Bot skip: bot disabled/missing conversation (id=%s, enabled=%s)",
            conversation_id,
            conversation.get("bot_enabled") if conversation else None,
        )
        return

    account_id = conversation["account_id"]

    if message_type and message_type.lower() != "text":
        fallback = "Je ne peux pas lire ce type de contenu, peux-tu me l'écrire ?"
        logger.info("Non-text message detected for %s; sending fallback", conversation_id)
        await send_message({"conversation_id": conversation_id, "content": fallback})
        return

    contact_name = contact.get("display_name") or contact.get("whatsapp_number")

    try:
        logger.info(
            "Gemini invocation for conversation %s (account=%s, contact=%s)",
            conversation_id,
            conversation["account_id"],
            contact_name,
        )
        reply = await bot_service.generate_bot_reply(
            conversation_id,
            conversation["account_id"],
            message_text,
            contact_name,
        )
    except Exception as exc:
        logger.warning("Bot generation failed for %s: %s", conversation_id, exc)
        return

    if not reply:
        logger.info("Gemini returned empty text for %s, escalating to human", conversation_id)
        await send_message({"conversation_id": conversation_id, "content": FALLBACK_MESSAGE})
        await _escalate_to_human(conversation, message_text)
        return

    normalized_reply = reply.strip().lower()
    requires_escalation = normalized_reply == FALLBACK_MESSAGE.lower()

    send_result = await send_message({"conversation_id": conversation_id, "content": reply})
    if isinstance(send_result, dict) and send_result.get("error"):
        logger.warning("Bot send failed for %s: %s", conversation_id, send_result)
        if message_type and message_type != "text":
            logger.info("Disabling bot for %s after unsupported content", conversation_id)
            await set_conversation_bot_mode(conversation_id, False)
        return

    logger.info("Bot reply sent for conversation %s (length=%d)", conversation_id, len(reply))
    await supabase_execute(
        supabase.table("conversations")
        .update({"bot_last_reply_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", conversation_id)
    )
    # Invalider le cache pour garantir la cohérence
    from app.core.cache import invalidate_cache_pattern
    await invalidate_cache_pattern(f"conversation:{conversation_id}")

    if requires_escalation:
        await _escalate_to_human(conversation, message_text)


async def get_messages(
    conversation_id: str,
    limit: int = 100,
    before: Optional[str] = None,
):
    query = (
        supabase.table("messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("timestamp", desc=True)
        .limit(limit)
    )
    if before:
        query = query.lt("timestamp", before)
    res = await supabase_execute(query)
    rows = res.data or []
    rows.reverse()
    
    # Récupérer les réactions pour chaque message
    if rows:
        message_ids = [msg["id"] for msg in rows]
        reactions_res = await supabase_execute(
            supabase.table("message_reactions")
            .select("*")
            .in_("message_id", message_ids)
        )
        reactions_by_message = {}
        for reaction in reactions_res.data or []:
            msg_id = reaction["message_id"]
            if msg_id not in reactions_by_message:
                reactions_by_message[msg_id] = []
            reactions_by_message[msg_id].append(reaction)
        
        # Ajouter les réactions à chaque message
        for msg in rows:
            msg["reactions"] = reactions_by_message.get(msg["id"], [])
    
    return rows


async def add_reaction(message_id: str, emoji: str, from_number: str) -> Dict[str, Any]:
    """
    Ajoute une réaction à un message.
    
    Args:
        message_id: ID du message dans la base de données
        emoji: Emoji de la réaction
        from_number: Numéro WhatsApp de la personne qui réagit
    
    Returns:
        Dict avec le résultat de l'opération
    """
    # Vérifier que le message existe
    message = await supabase_execute(
        supabase.table("messages")
        .select("id, wa_message_id, conversation_id")
        .eq("id", message_id)
        .limit(1)
    )
    
    if not message.data:
        return {"error": "message_not_found"}
    
    msg = message.data[0]
    
    # Ajouter la réaction
    reaction = await supabase_execute(
        supabase.table("message_reactions").upsert(
            {
                "message_id": message_id,
                "emoji": emoji,
                "from_number": from_number,
            },
            on_conflict="message_id,from_number,emoji",
        )
    )
    
    return {"success": True, "reaction": reaction.data[0] if reaction.data else None}


async def remove_reaction(message_id: str, emoji: str, from_number: str) -> Dict[str, Any]:
    """
    Supprime une réaction d'un message.
    
    Args:
        message_id: ID du message dans la base de données
        emoji: Emoji de la réaction à supprimer
        from_number: Numéro WhatsApp de la personne qui retire la réaction
    
    Returns:
        Dict avec le résultat de l'opération
    """
    # Vérifier que le message existe
    message = await supabase_execute(
        supabase.table("messages")
        .select("id")
        .eq("id", message_id)
        .limit(1)
    )
    
    if not message.data:
        return {"error": "message_not_found"}
    
    # Supprimer la réaction
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
    
    to_number = conversation["client_number"]
    
    body = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "reaction",
        "reaction": {
            "message_id": target_wa_message_id,
            "emoji": emoji,
        },
    }
    
    try:
        response = await _send_to_whatsapp_with_retry(phone_id, token, body)
    except httpx.HTTPError as exc:
        logger.error("WhatsApp reaction API error: %s", exc)
        return {
            "error": "whatsapp_api_error",
            "details": str(exc),
        }
    
    if response.is_error:
        logger.error("WhatsApp reaction error: %s %s", response.status_code, response.text)
        return {
            "error": "whatsapp_api_error",
            "status_code": response.status_code,
            "details": response.text,
        }
    
    response_json = response.json()
    wa_message_id = response_json.get("messages", [{}])[0].get("id")
    
    return {
        "success": True,
        "wa_message_id": wa_message_id,
    }


@retry_on_network_error(max_attempts=3, min_wait=1.0, max_wait=5.0)
async def _send_to_whatsapp_with_retry(phone_id: str, token: str, body: dict) -> httpx.Response:
    """Envoie un message WhatsApp avec retry automatique sur erreurs réseau."""
    client = await get_http_client()
    response = await client.post(
        f"https://graph.facebook.com/v19.0/{phone_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )
    return response


async def send_message(payload: dict):
    import asyncio
    
    conv_id = payload.get("conversation_id")
    text = payload.get("content")

    if not conv_id or not text:
        return {"error": "invalid_payload", "message": "conversation_id and content are required"}

    # Récupérer la conversation (avec cache)
    conversation = await get_conversation_by_id(conv_id)
    if not conversation:
        return {"error": "conversation_not_found"}

    to_number = conversation["client_number"]
    account_id = conversation.get("account_id")

    # Récupérer l'account (avec cache)
    account = await get_account_by_id(account_id)
    if not account:
        return {"error": "account_not_found"}

    phone_id = account.get("phone_number_id") or settings.WHATSAPP_PHONE_ID
    token = account.get("access_token") or settings.WHATSAPP_TOKEN

    if not phone_id or not token:
        return {"error": "whatsapp_not_configured"}

    body = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text},
    }

    # Utiliser le client HTTP partagé avec retry automatique
    timestamp_iso = datetime.now(timezone.utc).isoformat()
    
    try:
        response = await _send_to_whatsapp_with_retry(phone_id, token, body)
    except httpx.HTTPError as exc:
        logger.error("WhatsApp API error after retries: %s", exc)
        return {
            "error": "whatsapp_api_error",
            "status_code": getattr(exc, "response", {}).get("status_code", 0),
            "details": str(exc),
        }

    if response.is_error:
        logger.error("WhatsApp send error: %s %s", response.status_code, response.text)
        return {
            "error": "whatsapp_api_error",
            "status_code": response.status_code,
            "details": response.text,
        }

    message_id = None
    try:
        response_json = response.json()
        message_id = response_json.get("messages", [{}])[0].get("id")
    except ValueError:
        response_json = None

    message_payload = {
        "conversation_id": conv_id,
        "direction": "outbound",
        "content_text": text,
        "timestamp": timestamp_iso,
        "wa_message_id": message_id,
        "message_type": "text",
        "status": "sent",
    }

    # Paralléliser l'insertion du message et l'update de la conversation
    await asyncio.gather(
        supabase_execute(
            supabase.table("messages").upsert(message_payload, on_conflict="wa_message_id")
        ),
        _update_conversation_timestamp(conv_id, timestamp_iso)
    )

    return {"status": "sent", "message_id": message_id}


async def send_interactive_message_with_storage(
    conversation_id: str,
    interactive_type: str,
    body_text: str,
    interactive_payload: dict,
    header_text: Optional[str] = None,
    footer_text: Optional[str] = None
):
    """
    Envoie un message interactif (buttons/list) ET l'enregistre correctement dans la base
    """
    if not conversation_id or not body_text:
        return {"error": "invalid_payload"}

    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        return {"error": "conversation_not_found"}

    to_number = conversation["client_number"]
    account_id = conversation.get("account_id")

    account = await get_account_by_id(account_id)
    if not account:
        return {"error": "account_not_found"}

    phone_id = account.get("phone_number_id") or settings.WHATSAPP_PHONE_ID
    token = account.get("access_token") or settings.WHATSAPP_TOKEN

    if not phone_id or not token:
        return {"error": "whatsapp_not_configured"}

    # Construire le payload pour WhatsApp
    interactive_obj = {
        "type": interactive_type,
        "body": {"text": body_text}
    }
    
    if header_text:
        interactive_obj["header"] = {"type": "text", "text": header_text}
    if footer_text:
        interactive_obj["footer"] = {"text": footer_text}
    
    # Ajouter action (buttons ou sections)
    interactive_obj["action"] = interactive_payload

    body = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "interactive",
        "interactive": interactive_obj
    }

    timestamp_iso = datetime.now(timezone.utc).isoformat()
    
    try:
        # Utiliser le client avec retry
        client = await get_http_client()
        response = await client.post(
            f"https://graph.facebook.com/v19.0/{phone_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json=body
        )
        response.raise_for_status()

        # Récupérer le message ID
        response_json = response.json()
        message_id = response_json.get("messages", [{}])[0].get("id")

        # Construire un texte de prévisualisation
        if interactive_type == "button":
            button_titles = [btn.get("reply", {}).get("title", "") for btn in interactive_payload.get("buttons", [])]
            preview_text = f"{body_text}\n[Boutons: {', '.join(button_titles)}]"
        else:  # list
            preview_text = f"{body_text}\n[Liste interactive]"

        # Enregistrer le message dans la base
        message_payload = {
            "conversation_id": conversation_id,
            "direction": "outbound",
            "content_text": preview_text,
            "timestamp": timestamp_iso,
            "wa_message_id": message_id,
            "message_type": "interactive",
            "status": "sent",
            "interactive_data": json.dumps({
                "type": interactive_type,
                "header": header_text,
                "body": body_text,
                "footer": footer_text,
                "action": interactive_payload
            })
        }

        await asyncio.gather(
            supabase_execute(
                supabase.table("messages").upsert(message_payload, on_conflict="wa_message_id")
            ),
            _update_conversation_timestamp(conversation_id, timestamp_iso)
        )

        return {"status": "sent", "message_id": message_id}
    
    except httpx.HTTPError as exc:
        logger.error("WhatsApp interactive message error: %s", exc)
        return {
            "error": "whatsapp_api_error",
            "details": str(exc),
        }


async def send_media_message_with_storage(
    conversation_id: str,
    media_type: str,
    media_id: str,
    caption: Optional[str] = None
):
    """
    Envoie un message média ET l'enregistre correctement dans la base
    """
    if not conversation_id or not media_id:
        return {"error": "invalid_payload"}

    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        return {"error": "conversation_not_found"}

    to_number = conversation["client_number"]
    account_id = conversation.get("account_id")

    account = await get_account_by_id(account_id)
    if not account:
        return {"error": "account_not_found"}

    phone_id = account.get("phone_number_id") or settings.WHATSAPP_PHONE_ID
    token = account.get("access_token") or settings.WHATSAPP_TOKEN

    if not phone_id or not token:
        return {"error": "whatsapp_not_configured"}

    # Construire le payload pour WhatsApp
    media_object = {"id": media_id}
    if caption:
        media_object["caption"] = caption

    body = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": media_type,
        media_type: media_object
    }

    timestamp_iso = datetime.now(timezone.utc).isoformat()
    
    try:
        # Utiliser le client avec retry
        client = await get_http_client()
        response = await client.post(
            f"https://graph.facebook.com/v19.0/{phone_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json=body
        )
    except httpx.HTTPError as exc:
        logger.error("WhatsApp API error: %s", exc)
        return {"error": "whatsapp_api_error", "details": str(exc)}

    if response.is_error:
        logger.error("WhatsApp send error: %s %s", response.status_code, response.text)
        return {"error": "whatsapp_api_error", "status_code": response.status_code}

    message_id = None
    try:
        response_json = response.json()
        message_id = response_json.get("messages", [{}])[0].get("id")
    except ValueError:
        response_json = None

    # Créer le texte à afficher
    display_text = caption if caption else f"[{media_type}]"

    # Enregistrer le message dans la base
    message_payload = {
        "conversation_id": conversation_id,
        "direction": "outbound",
        "content_text": display_text,
        "timestamp": timestamp_iso,
        "wa_message_id": message_id,
        "message_type": media_type,
        "status": "sent",
        "media_id": media_id,
        "media_mime_type": None,  # Sera mis à jour si disponible
    }

    await supabase_execute(
        supabase.table("messages").upsert(message_payload, on_conflict="wa_message_id")
    )
    await _update_conversation_timestamp(conversation_id, timestamp_iso)

    return {"status": "sent", "message_id": message_id}


def _extract_media_metadata(message: Dict[str, Any]) -> Dict[str, Optional[str]]:
    msg_type = message.get("type")
    if isinstance(msg_type, str):
        msg_type = msg_type.lower()
    media_section: Optional[Dict[str, Any]] = None

    if msg_type in {"audio", "voice"}:
        media_section = message.get("audio") or message.get("voice")
    elif msg_type == "image":
        media_section = message.get("image")
    elif msg_type == "video":
        media_section = message.get("video")
    elif msg_type == "document":
        media_section = message.get("document")
    elif msg_type == "sticker":
        media_section = message.get("sticker")
    elif msg_type == "interactive":
        interactive = message.get("interactive", {})
        if interactive.get("type") == "list_reply":
            media_section = None
    elif msg_type == "contacts":
        media_section = None

    if media_section and media_section.get("id"):
        return {
            "media_id": media_section.get("id"),
            "media_mime_type": media_section.get("mime_type"),
            "media_filename": media_section.get("filename") or media_section.get("sha256"),
        }

    return {}


async def get_message_by_id(message_id: str) -> Optional[Dict[str, Any]]:
    res = await supabase_execute(
        supabase.table("messages").select("*").eq("id", message_id).limit(1)
    )
    if not res.data:
        return None
    return res.data[0]


async def _escalate_to_human(conversation: Dict[str, Any], last_customer_message: str):
    await set_conversation_bot_mode(conversation["id"], False)
    await _notify_backup(conversation, last_customer_message)


async def _notify_backup(conversation: Dict[str, Any], last_customer_message: str):
    backup_number = settings.HUMAN_BACKUP_NUMBER
    if not backup_number:
        logger.info("No HUMAN_BACKUP_NUMBER configured; skipping backup notification")
        return

    account_id = conversation["account_id"]
    summary = (
        f"[Escalade] Conversation {conversation['id']} (client: {conversation.get('client_number')})\n"
        f"Dernier message: {last_customer_message}"
    )
    await _send_direct_whatsapp(account_id, backup_number, summary)


async def _send_direct_whatsapp(account_id: str, to_number: str, text: str):
    if not text.strip():
        return
    account = await get_account_by_id(account_id)
    if not account:
        logger.warning("Cannot notify backup: account %s not found", account_id)
        return

    phone_id = account.get("phone_number_id") or settings.WHATSAPP_PHONE_ID
    token = account.get("access_token") or settings.WHATSAPP_TOKEN
    if not phone_id or not token:
        logger.warning("Cannot notify backup: missing phone id/token for account %s", account_id)
        return

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text},
    }

    try:
        resp = await _send_to_whatsapp_with_retry(phone_id, token, payload)
        if resp.is_error:
            logger.warning(
                "Failed to notify backup %s (status=%s): %s",
                to_number,
                resp.status_code,
                resp.text,
            )
    except httpx.HTTPError as exc:
        logger.warning("Failed to notify backup %s: %s", to_number, exc)


async def fetch_message_media_content(
    message: Dict[str, Any], account: Dict[str, Any]
) -> Tuple[bytes, str, Optional[str]]:
    media_id = message.get("media_id")
    if not media_id:
        raise ValueError("media_missing")

    token = account.get("access_token") or settings.WHATSAPP_TOKEN
    if not token:
        raise ValueError("missing_token")

    # Utiliser le client pour médias (timeout plus long)
    client = await get_http_client_for_media()
    
    try:
        # Récupérer les métadonnées du média
        meta_resp = await client.get(
            f"https://graph.facebook.com/v19.0/{media_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        meta_resp.raise_for_status()
        meta_json = meta_resp.json()
        download_url = meta_json.get("url")
        mime_type = (
            meta_json.get("mime_type")
            or message.get("media_mime_type")
            or "application/octet-stream"
        )

        if not download_url:
            raise ValueError("media_url_missing")

        # Télécharger le contenu du média avec le token dans le header
        media_resp = await client.get(
            download_url, 
            headers={"Authorization": f"Bearer {token}"}
        )
        media_resp.raise_for_status()
        content = media_resp.content

        filename = message.get("media_filename") or meta_json.get("file_name")
        return content, mime_type, filename
    except httpx.HTTPStatusError as e:
        # Gérer les erreurs HTTP de l'API WhatsApp
        if e.response.status_code == 400:
            # Média expiré ou invalide
            raise ValueError("media_expired_or_invalid")
        elif e.response.status_code == 401:
            # Token invalide
            raise ValueError("invalid_token")
        elif e.response.status_code == 404:
            # Média non trouvé
            raise ValueError("media_not_found")
        else:
            # Autre erreur HTTP
            raise ValueError(f"media_fetch_error_{e.response.status_code}")
    except httpx.HTTPError as e:
        # Erreur réseau ou autre
        logger.error(f"HTTP error fetching media {media_id}: {e}")
        raise ValueError("media_network_error")


async def _download_and_store_media_async(
    message_db_id: str,
    media_id: str,
    account: Dict[str, Any],
    mime_type: Optional[str] = None,
    filename: Optional[str] = None
):
    """
    Télécharge un média depuis WhatsApp et le stocke dans Supabase Storage en arrière-plan.
    Cette fonction est appelée de manière asynchrone pour ne pas bloquer le traitement du webhook.
    """
    logger.info(f"🚀 Starting media download and storage: message_id={message_db_id}, media_id={media_id}")
    try:
        from app.core.http_client import get_http_client_for_media
        
        token = account.get("access_token") or settings.WHATSAPP_TOKEN
        if not token:
            logger.warning(f"❌ Missing token for media download: message_id={message_db_id}")
            return
        
        logger.info(f"📡 Fetching media metadata from WhatsApp: media_id={media_id}")
        # Récupérer les métadonnées du média depuis WhatsApp
        client = await get_http_client_for_media()
        meta_resp = await client.get(
            f"https://graph.facebook.com/v19.0/{media_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        meta_resp.raise_for_status()
        meta_json = meta_resp.json()
        download_url = meta_json.get("url")
        
        if not download_url:
            logger.warning(f"❌ No download URL for media: message_id={message_db_id}, meta_json={meta_json}")
            return
        
        logger.info(f"📥 Download URL obtained, downloading media: message_id={message_db_id}")
        
        # Détecter le mime_type
        detected_mime_type = (
            meta_json.get("mime_type")
            or mime_type
            or "application/octet-stream"
        )
        
        logger.info(f"💾 Starting storage in Supabase: message_id={message_db_id}, mime_type={detected_mime_type}")
        # Télécharger et stocker dans Supabase Storage
        storage_url = await download_and_store_message_media(
            message_id=message_db_id,
            media_url=download_url,
            content_type=detected_mime_type,
            filename=filename or meta_json.get("file_name")
        )
        
        if storage_url:
            # Mettre à jour le message avec l'URL de stockage
            await supabase_execute(
                supabase.table("messages")
                .update({"storage_url": storage_url})
                .eq("id", message_db_id)
            )
            logger.info(f"✅ Media stored in Supabase Storage: message_id={message_db_id}, storage_url={storage_url}")
        else:
            logger.warning(f"❌ Failed to store media in Supabase Storage: message_id={message_db_id}")
            
    except Exception as e:
        logger.error(f"❌ Error downloading and storing media: message_id={message_db_id}, error={e}", exc_info=True)