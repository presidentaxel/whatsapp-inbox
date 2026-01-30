import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.db import supabase, supabase_execute, SUPABASE_IN_CLAUSE_CHUNK_SIZE
from app.core.pg import fetch_all, fetch_one, execute, get_pool
from app.core.http_client import get_http_client, get_http_client_for_media
from app.core.retry import retry_on_network_error
from app.services import bot_service
from app.services.account_service import (
    get_account_by_id,
    get_account_by_phone_number_id,
)
from app.services.conversation_service import get_conversation_by_id, set_conversation_bot_mode
from app.services.profile_picture_service import queue_profile_picture_update
from app.services.storage_service import download_and_store_message_media
from app.services.whatsapp_api_service import (
    get_phone_number_details,
    list_message_templates,
    create_message_template,
    send_template_message,
    check_phone_number_has_whatsapp,
)

FALLBACK_MESSAGE = "Je me renseigne auprès d'un collègue et je reviens vers vous au plus vite."

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# S'assurer que les logs sont visibles
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = True


async def handle_incoming_message(data: dict):
    """
    Parse le webhook WhatsApp Cloud API et stocke les messages + statuts.
    
    Supporte deux formats:
    1. Format réel: {"object": "...", "entry": [...]}
    2. Format test Meta: {"field": "...", "value": {...}}
    """
    try:
        logger.info(f"📥 Webhook received: object={data.get('object')}, entries={len(data.get('entry', []))}")
        
        # Gérer le format du test Meta (v24.0) qui est différent
        if "field" in data and "value" in data and "entry" not in data:
            logger.info("🔄 Format test Meta détecté, conversion au format réel...")
            # Convertir le format test en format réel
            field = data.get("field")
            value = data.get("value")
            
            # Créer une structure entry compatible
            phone_number_id = value.get("metadata", {}).get("phone_number_id")
            if not phone_number_id:
                logger.error("❌ Format test Meta: phone_number_id manquant dans metadata")
                return True
            
            # Utiliser phone_number_id comme entry.id (peut être WABA_ID dans certains cas)
            data = {
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "id": phone_number_id,
                        "changes": [
                            {
                                "field": field,
                                "value": value
                            }
                        ]
                    }
                ]
            }
            logger.info(f"✅ Format converti: entry.id={phone_number_id}, field={field}")
        
        entries = data.get("entry", [])
        if not entries:
            logger.warning("⚠️ No entries in webhook payload")
            logger.debug(f"📋 Webhook data keys: {list(data.keys())}")
            return True

        for entry_idx, entry in enumerate(entries):
            logger.info(f"📋 Processing entry {entry_idx + 1}/{len(entries)}")
            changes = entry.get("changes", [])
            
            if not changes:
                logger.warning(f"⚠️ No changes in entry {entry_idx + 1}")
                continue
            
            for change_idx, change in enumerate(changes):
                try:
                    value = change.get("value", {})
                    if not value:
                        logger.warning(f"⚠️ No value in change {change_idx + 1}")
                        continue
                    
                    metadata = value.get("metadata", {})
                    phone_number_id = metadata.get("phone_number_id")
                    entry_id = entry.get("id")
                    change_field = change.get("field")
                    account = None
                    
                    # Certains types de webhooks n'ont pas besoin d'un compte (ex: message_template_status_update)
                    # On ne traite que les webhooks qui concernent les messages
                    if change_field not in ("messages", "message_status"):
                        logger.debug(f"ℹ️ Skipping webhook field '{change_field}' (not a message-related event)")
                        continue
                    
                    # Stratégie de recherche du compte:
                    # 1. Utiliser phone_number_id du metadata (méthode principale)
                    # 2. Si absent, essayer entry.id comme phone_number_id
                    # 3. Si toujours pas trouvé, logger l'erreur
                    
                    if phone_number_id:
                        logger.info(f"🔍 Looking for account with phone_number_id from metadata: {phone_number_id}")
                        account = await get_account_by_phone_number_id(phone_number_id)
                        if account:
                            logger.info(f"✅ Found account using metadata phone_number_id: {account.get('name')} (id: {account.get('id')})")
                    
                    # Si pas trouvé et qu'on a un entry.id, essayer avec ça
                    if not account and entry_id and entry_id != "0":
                        logger.info(f"🔍 Strategy 2: Trying entry.id as phone_number_id: {entry_id}")
                        account = await get_account_by_phone_number_id(entry_id)
                        if account:
                            logger.info(f"✅ Found account using entry.id: {account.get('name')} (id: {account.get('id')})")
                            phone_number_id = entry_id  # Utiliser entry.id comme phone_number_id
                    
                    # Si toujours pas trouvé, logger toutes les infos disponibles
                    if not account:
                        logger.error(
                            f"❌ CRITICAL: Cannot find account for webhook!\n"
                            f"   metadata phone_number_id: {phone_number_id or 'MISSING'}\n"
                            f"   entry.id: {entry_id or 'MISSING'}\n"
                            f"   metadata: {json.dumps(metadata, indent=2)}\n"
                            f"   change_field: {change.get('field')}\n"
                            f"   value_keys: {list(value.keys())}\n"
                            f"   This webhook will be SKIPPED - messages will NOT be stored!"
                        )
                        # Lister tous les comptes disponibles pour debug
                        from app.services.account_service import get_all_accounts
                        all_accounts = await get_all_accounts()
                        if all_accounts:
                            logger.error(f"📋 Available accounts in database:")
                            for acc in all_accounts:
                                is_active = acc.get('is_active', False)
                                status = "✅ ACTIVE" if is_active else "❌ INACTIVE"
                                logger.error(f"   {status} - {acc.get('name')}: phone_number_id={acc.get('phone_number_id')}")
                        else:
                            logger.error("📋 NO ACCOUNTS FOUND in database!")
                            logger.error("   → Check that ensure_default_account() has been called")
                            logger.error("   → Check that WHATSAPP_PHONE_ID and WHATSAPP_TOKEN are set in .env")
                        # CRITICAL: Skip this change - messages will be lost if we continue
                        continue
                    
                    logger.info(f"✅ Account found: {account.get('id')} ({account.get('name', 'N/A')})")

                    contacts_map = {c.get("wa_id"): c for c in value.get("contacts", []) if c.get("wa_id")}
                    
                    # Debug: Afficher les informations de contact disponibles dans le webhook
                    if contacts_map:
                        logger.debug(f"📋 Contacts in webhook: {len(contacts_map)} contacts")
                        for wa_id, contact_info in contacts_map.items():
                            profile = contact_info.get("profile", {})
                            logger.debug(f"  {wa_id}: name={profile.get('name')}, profile_data={json.dumps(profile)}")

                    messages = value.get("messages", [])
                    logger.info(f"📨 Processing {len(messages)} messages")
                    
                    for msg_idx, message in enumerate(messages):
                        try:
                            logger.info(f"  Processing message {msg_idx + 1}/{len(messages)}: type={message.get('type')}, from={message.get('from')}")
                            await _process_incoming_message(account["id"], message, contacts_map)
                            logger.info(f"  ✅ Message {msg_idx + 1} processed successfully")
                        except Exception as msg_error:
                            logger.error(f"  ❌ Error processing message {msg_idx + 1}: {msg_error}", exc_info=True)
                            # Continue avec les autres messages même si un échoue

                    statuses = value.get("statuses", [])
                    logger.info(f"📊 Processing {len(statuses)} statuses")
                    
                    for status_idx, status in enumerate(statuses):
                        try:
                            await _process_status(status, account)
                            logger.debug(f"  ✅ Status {status_idx + 1} processed")
                        except Exception as status_error:
                            logger.error(f"  ❌ Error processing status {status_idx + 1}: {status_error}", exc_info=True)
                            # Continue avec les autres statuts même si un échoue
                            
                except Exception as change_error:
                    logger.error(f"❌ Error processing change {change_idx + 1}: {change_error}", exc_info=True)
                    # Enregistrer l'erreur pour diagnostic
                    try:
                        from app.api.routes_diagnostics import log_error_to_memory
                        log_error_to_memory(
                            "message_processing_change",
                            str(change_error),
                            {
                                "entry_id": entry.get("id"),
                                "change_field": change.get("field"),
                                "change_idx": change_idx
                            }
                        )
                    except:
                        pass
                    # Continue avec les autres changes même si un échoue
                    
    except Exception as e:
        logger.error(f"❌ Critical error in handle_incoming_message: {e}", exc_info=True)
        # Enregistrer l'erreur pour diagnostic
        try:
            from app.api.routes_diagnostics import log_error_to_memory
            log_error_to_memory(
                "handle_incoming_message_critical",
                str(e),
                {
                    "data_object": data.get("object") if isinstance(data, dict) else None,
                    "entries_count": len(data.get("entry", [])) if isinstance(data, dict) else 0
                }
            )
        except:
            pass
        # Ne pas lever l'exception pour que WhatsApp ne réessaie pas indéfiniment
        return True

    return True


async def _process_incoming_message(
    account_id: str, message: Dict[str, Any], contacts_map: Dict[str, Any]
):
    try:
        print(f"🔍 [BOT DEBUG] _process_incoming_message called: account_id={account_id}, message_id={message.get('id')}, from={message.get('from')}")
        logger.info(f"🔍 [BOT DEBUG] _process_incoming_message called: account_id={account_id}, message_id={message.get('id')}, from={message.get('from')}")
        wa_id = message.get("from")
        if not wa_id:
            logger.warning("⚠️ [BOT DEBUG] Message has no 'from' field, skipping")
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
        logger.info(f"🔍 [BOT DEBUG] Contact upserted: id={contact.get('id')}, whatsapp_number={contact.get('whatsapp_number')}")
        
        conversation = await _upsert_conversation(account_id, contact["id"], wa_id, timestamp_iso)
        logger.info(f"🔍 [BOT DEBUG] Conversation upserted: id={conversation.get('id')}, bot_enabled={conversation.get('bot_enabled')}")

        # Invalider immédiatement le cache fenêtre gratuite pour que le prochain envoi
        # (ex. réponse rapide après "Eh") voie un état à jour et n'utilise pas un cache périmé
        try:
            from app.core.cache import get_cache
            cache = await get_cache()
            await cache.delete(f"free_window:{conversation['id']}")
        except Exception as cache_err:
            logger.debug("Free window cache invalidation (early): %s", cache_err)

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
            if get_pool():
                target_row = await fetch_one(
                    "SELECT id FROM messages WHERE wa_message_id = $1 AND conversation_id = $2::uuid LIMIT 1",
                    target_message_id,
                    conversation["id"],
                )
                target_msg_id = target_row["id"] if target_row else None
            else:
                target_message = await supabase_execute(
                    supabase.table("messages")
                    .select("id")
                    .eq("wa_message_id", target_message_id)
                    .limit(1)
                )
                target_msg_id = target_message.data[0]["id"] if target_message.data else None
            if not target_msg_id:
                logger.warning("Target message not found for reaction: %s", target_message_id)
                return
            
            if not emoji or emoji == "":
                if get_pool():
                    await execute(
                        "DELETE FROM message_reactions WHERE message_id = $1::uuid AND from_number = $2",
                        target_msg_id,
                        wa_id,
                    )
                else:
                    await supabase_execute(
                        supabase.table("message_reactions")
                        .delete()
                        .eq("message_id", target_msg_id)
                        .eq("from_number", wa_id)
                    )
            else:
                if get_pool():
                    await execute(
                        """
                        INSERT INTO message_reactions (message_id, wa_message_id, emoji, from_number)
                        VALUES ($1::uuid, $2, $3, $4)
                        ON CONFLICT (message_id, from_number, emoji) DO UPDATE SET emoji = EXCLUDED.emoji, wa_message_id = EXCLUDED.wa_message_id
                        """,
                        target_msg_id,
                        message.get("id"),
                        emoji,
                        wa_id,
                    )
                else:
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
        
        # Log de diagnostic pour voir ce qui est extrait
        logger.info(f"🔍 [MESSAGE PROCESSING] Processing message from {wa_id}:")
        logger.info(f"   - wa_message_id: {message.get('id')}")
        logger.info(f"   - msg_type: {msg_type}")
        logger.info(f"   - content_text: {repr(content_text)}")
        logger.info(f"   - media_meta: {media_meta}")
        logger.info(f"   - account_id: {account_id}")
        
        # Pour les messages interactifs, logger toute la structure
        if msg_type == "interactive":
            logger.info(f"🔍 [MESSAGE PROCESSING] Full message structure for interactive:")
            logger.info(f"   {json.dumps(message, indent=2, ensure_ascii=False)}")

        # Pour les réponses de boutons, traiter comme un message texte normal
        # car le contenu est maintenant extrait dans content_text
        stored_message_type = "text" if msg_type == "button" else msg_type

        # Extraire le contexte (message référencé) si présent
        reply_to_message_id = None
        context = message.get("context")
        if context:
            referenced_wa_message_id = context.get("id")
            if referenced_wa_message_id:
                logger.info(f"🔍 [MESSAGE PROCESSING] Message has context, referenced wa_message_id: {referenced_wa_message_id}")
                if get_pool():
                    ref_row = await fetch_one(
                        "SELECT id FROM messages WHERE wa_message_id = $1 AND conversation_id = $2::uuid LIMIT 1",
                        referenced_wa_message_id,
                        conversation["id"],
                    )
                    if ref_row:
                        reply_to_message_id = ref_row["id"]
                        logger.info(f"✅ [MESSAGE PROCESSING] Found referenced message: reply_to_message_id={reply_to_message_id}")
                    else:
                        logger.warning(f"⚠️ [MESSAGE PROCESSING] Referenced message not found: wa_message_id={referenced_wa_message_id}")
                else:
                    referenced_message = await supabase_execute(
                        supabase.table("messages")
                        .select("id")
                        .eq("wa_message_id", referenced_wa_message_id)
                        .eq("conversation_id", conversation["id"])
                        .limit(1)
                    )
                    if referenced_message.data and len(referenced_message.data) > 0:
                        reply_to_message_id = referenced_message.data[0]["id"]
                        logger.info(f"✅ [MESSAGE PROCESSING] Found referenced message: reply_to_message_id={reply_to_message_id}")
                    else:
                        logger.warning(f"⚠️ [MESSAGE PROCESSING] Referenced message not found: wa_message_id={referenced_wa_message_id}")

        # Insérer le message d'abord
        message_payload = {
            "conversation_id": conversation["id"],
            "direction": "inbound",
            "content_text": content_text,
            "timestamp": timestamp_iso,
            "wa_message_id": message.get("id"),
            "message_type": stored_message_type,
            "status": "received",
            "media_id": media_meta.get("media_id"),
            "media_mime_type": media_meta.get("media_mime_type"),
            "media_filename": media_meta.get("media_filename"),
        }
        
        # Ajouter reply_to_message_id si présent
        if reply_to_message_id:
            message_payload["reply_to_message_id"] = reply_to_message_id
        
        logger.info(f"💾 [MESSAGE INSERT] Attempting to upsert message: wa_message_id={message.get('id')}, conversation_id={conversation['id']}, direction=inbound")
        logger.info(f"💾 [MESSAGE INSERT] Payload: {json.dumps({k: v for k, v in message_payload.items() if k != 'content_text'}, indent=2)}")
        
        message_db_id = None
        try:
            if get_pool():
                row = await fetch_one(
                    """
                    INSERT INTO messages (conversation_id, direction, content_text, timestamp, wa_message_id, message_type, status, media_id, media_mime_type, media_filename, reply_to_message_id)
                    VALUES ($1::uuid, $2, $3, $4::timestamptz, $5, $6, $7, $8, $9, $10, $11::uuid)
                    ON CONFLICT (wa_message_id) DO UPDATE SET
                        conversation_id = EXCLUDED.conversation_id,
                        direction = EXCLUDED.direction,
                        content_text = EXCLUDED.content_text,
                        timestamp = EXCLUDED.timestamp,
                        message_type = EXCLUDED.message_type,
                        status = EXCLUDED.status,
                        media_id = EXCLUDED.media_id,
                        media_mime_type = EXCLUDED.media_mime_type,
                        media_filename = EXCLUDED.media_filename,
                        reply_to_message_id = EXCLUDED.reply_to_message_id
                    RETURNING id, conversation_id, direction
                    """,
                    message_payload["conversation_id"],
                    message_payload["direction"],
                    message_payload["content_text"],
                    message_payload["timestamp"],
                    message_payload["wa_message_id"],
                    message_payload["message_type"],
                    message_payload["status"],
                    message_payload.get("media_id"),
                    message_payload.get("media_mime_type"),
                    message_payload.get("media_filename"),
                    message_payload.get("reply_to_message_id"),
                )
                if row:
                    message_db_id = row["id"]
                    stored_conv_id = row["conversation_id"]
                    stored_direction = row["direction"]
                    logger.info(f"✅ [MESSAGE INSERT] Message upserted (pg): id={message_db_id}, conversation_id={stored_conv_id}, direction={stored_direction}")
                    if stored_conv_id != conversation["id"]:
                        logger.error(f"❌ [MESSAGE INSERT] CRITICAL: Message stored in wrong conversation! Expected: {conversation['id']}, Got: {stored_conv_id}")
                    if stored_direction != "inbound":
                        logger.error(f"❌ [MESSAGE INSERT] CRITICAL: Message stored with wrong direction! Expected: inbound, Got: {stored_direction}")
            else:
                upsert_result = await supabase_execute(
                    supabase.table("messages").upsert(
                        message_payload,
                        on_conflict="wa_message_id",
                    )
                )
                if upsert_result.data and len(upsert_result.data) > 0:
                    message_db_id = upsert_result.data[0].get("id")
                    logger.info(f"✅ [MESSAGE INSERT] Message upserted successfully: {message_db_id}")
                if message.get("id") and not message_db_id:
                    existing_msg = await supabase_execute(
                        supabase.table("messages")
                        .select("id, conversation_id, direction")
                        .eq("wa_message_id", message.get("id"))
                        .limit(1)
                    )
                    if existing_msg.data:
                        message_db_id = existing_msg.data[0].get("id")
                        stored_conv_id = existing_msg.data[0].get("conversation_id")
                        stored_direction = existing_msg.data[0].get("direction")
                        logger.info(f"✅ [MESSAGE INSERT] Message ID retrieved: {message_db_id}")
                        if stored_conv_id != conversation["id"]:
                            logger.error(f"❌ [MESSAGE INSERT] CRITICAL: Message stored in wrong conversation!")
                        if stored_direction != "inbound":
                            logger.error(f"❌ [MESSAGE INSERT] CRITICAL: Message stored with wrong direction!")
                    else:
                        logger.error(f"❌ [MESSAGE INSERT] CRITICAL: Message upserted but not found by wa_message_id: {message.get('id')}")
        except Exception as upsert_error:
            logger.error(f"❌ [MESSAGE INSERT] CRITICAL: Failed to upsert message: {upsert_error}", exc_info=True)
            raise
        if not message_db_id and message.get("id"):
            logger.warning("⚠️ [MESSAGE INSERT] Message has no wa_message_id or upsert did not return id, cannot retrieve database ID")

        # Si c'est un média, télécharger et stocker dans Supabase Storage en arrière-plan
        # IMPORTANT: Le téléchargement se fait automatiquement dès la réception, sans attendre que l'utilisateur ouvre le chat
        has_media_id = bool(media_meta.get("media_id"))
        is_supported_type = msg_type in ("image", "video", "audio", "document", "sticker")
        
        if has_media_id and is_supported_type:
            logger.info(f"📥 [AUTO-DOWNLOAD] Media detected on message receipt: wa_message_id={message.get('id')}, media_id={media_meta.get('media_id')}, type={msg_type}")
            
            # Récupérer l'account pour le token (forcer le refresh pour avoir les dernières données Google Drive)
            account = await get_account_by_id(account_id)
            if not account:
                logger.error(f"❌ [AUTO-DOWNLOAD] Account not found for account_id={account_id}, cannot download media")
            else:
                # Vérifier que le compte a bien les colonnes Google Drive
                logger.info(f"🔍 [AUTO-DOWNLOAD] Account retrieved: id={account.get('id')}, has_google_drive_enabled={'google_drive_enabled' in account}, has_google_drive_connected={'google_drive_connected' in account}")
                if 'google_drive_enabled' not in account:
                    logger.warning(f"⚠️ [AUTO-DOWNLOAD] Account cache might be stale, forcing refresh for Google Drive columns")
                    if get_pool():
                        fresh_row = await fetch_one("SELECT * FROM whatsapp_accounts WHERE id = $1::uuid LIMIT 1", account_id)
                        if fresh_row:
                            account = dict(fresh_row)
                            logger.info(f"✅ [AUTO-DOWNLOAD] Account refreshed with Google Drive columns")
                    else:
                        fresh_account = await supabase_execute(
                            supabase.table("whatsapp_accounts").select("*").eq("id", account_id).limit(1)
                        )
                        if fresh_account.data:
                            account = fresh_account.data[0]
                            logger.info(f"✅ [AUTO-DOWNLOAD] Account refreshed with Google Drive columns")
            
            if message_db_id:
                # Cas idéal : message_db_id disponible immédiatement
                logger.info(f"✅ [AUTO-DOWNLOAD] Starting immediate download for message_id={message_db_id}")
                task = asyncio.create_task(_download_and_store_media_async(
                    message_db_id=message_db_id,
                    media_id=media_meta.get("media_id"),
                    account=account,
                    mime_type=media_meta.get("media_mime_type"),
                    filename=media_meta.get("media_filename")
                ))
                
                def log_task_result(t):
                    try:
                        if t.exception() is not None:
                            logger.error(f"❌ [AUTO-DOWNLOAD] Media download failed for message_id={message_db_id}: {t.exception()}", exc_info=t.exception())
                        else:
                            logger.info(f"✅ [AUTO-DOWNLOAD] Media download completed for message_id={message_db_id}")
                    except Exception as e:
                        logger.error(f"❌ [AUTO-DOWNLOAD] Error in task callback: {e}")
                
                task.add_done_callback(log_task_result)
            else:
                # Cas où message_db_id n'est pas encore disponible : retry avec délai
                wa_message_id = message.get("id")
                logger.info(f"⏳ [AUTO-DOWNLOAD] message_db_id not available yet, will retry for wa_message_id={wa_message_id}")
                
                async def retry_download_with_delay():
                    """Retry le téléchargement après un court délai pour laisser le temps au message d'être inséré"""
                    max_retries = 3
                    retry_delay = 1.0  # 1 seconde
                    
                    for attempt in range(max_retries):
                        await asyncio.sleep(retry_delay)
                        
                        # Chercher le message par wa_message_id
                        if get_pool():
                            msg_row = await fetch_one("SELECT id FROM messages WHERE wa_message_id = $1 LIMIT 1", wa_message_id)
                            retry_message_db_id = msg_row["id"] if msg_row else None
                        else:
                            msg_result = await supabase_execute(
                                supabase.table("messages")
                                .select("id")
                                .eq("wa_message_id", wa_message_id)
                                .limit(1)
                            )
                            retry_message_db_id = msg_result.data[0].get("id") if msg_result.data else None
                        if retry_message_db_id:
                            logger.info(f"✅ [AUTO-DOWNLOAD] Found message_db_id on attempt {attempt + 1}: {retry_message_db_id}")
                            
                            # Lancer le téléchargement
                            task = asyncio.create_task(_download_and_store_media_async(
                                message_db_id=retry_message_db_id,
                                media_id=media_meta.get("media_id"),
                                account=account,
                                mime_type=media_meta.get("media_mime_type"),
                                filename=media_meta.get("media_filename")
                            ))
                            
                            def log_retry_result(t):
                                try:
                                    if t.exception() is not None:
                                        logger.error(f"❌ [AUTO-DOWNLOAD] Retry download failed for message_id={retry_message_db_id}: {t.exception()}", exc_info=t.exception())
                                    else:
                                        logger.info(f"✅ [AUTO-DOWNLOAD] Retry download completed for message_id={retry_message_db_id}")
                                except Exception as e:
                                    logger.error(f"❌ [AUTO-DOWNLOAD] Error in retry task callback: {e}")
                            
                            task.add_done_callback(log_retry_result)
                            return
                        else:
                            logger.debug(f"⏳ [AUTO-DOWNLOAD] Attempt {attempt + 1}/{max_retries}: message_db_id still not found for wa_message_id={wa_message_id}")
                    
                    # Si après tous les essais, on n'a toujours pas le message_db_id
                    logger.warning(f"⚠️ [AUTO-DOWNLOAD] Could not find message_db_id after {max_retries} attempts for wa_message_id={wa_message_id}. Media will be downloaded by background task.")
                
                # Lancer le retry en arrière-plan
                asyncio.create_task(retry_download_with_delay())
        elif has_media_id and not is_supported_type:
            logger.debug(f"ℹ️ [AUTO-DOWNLOAD] Media detected but type '{msg_type}' not supported for auto-download (supported: image, video, audio, document, sticker)")
        elif not has_media_id:
            logger.debug(f"ℹ️ [AUTO-DOWNLOAD] Message has no media_id (not a media message)")

        await _update_conversation_timestamp(conversation["id"], timestamp_iso)
        await _increment_unread_count(conversation)
        
        # 🆕 Marquer qu'un destinataire a répondu à une campagne si applicable
        if message_db_id:
            try:
                from app.services.broadcast_service import track_reply
                await track_reply(
                    conversation_id=conversation["id"],
                    message_id=message_db_id,
                )
            except Exception as e:
                logger.debug(f"Broadcast reply tracking (not a broadcast reply or error): {e}")

        # Recharger la conversation pour s'assurer qu'on a la valeur à jour de bot_enabled
        # (l'upsert pourrait avoir préservé une ancienne valeur)
        refreshed_conversation = await get_conversation_by_id(conversation["id"])
        if refreshed_conversation:
            conversation = refreshed_conversation
        
        logger.info(f"🔍 [BOT DEBUG] Processing incoming message: conversation_id={conversation['id']}, bot_enabled={conversation.get('bot_enabled')}, content_text length={len(content_text or '')}")
        await _maybe_trigger_bot_reply(conversation["id"], content_text, contact, message.get("type"))
        
        logger.info(f"✅ Message processed successfully: conversation_id={conversation['id']}, type={msg_type}, from={wa_id}")
        
        # Vérifier et envoyer les notifications d'épinglage en attente
        # car un nouveau message entrant réinitialise la fenêtre gratuite
        try:
            from app.services.pinned_notification_service import send_pending_pin_notifications
            # Lancer en arrière-plan pour ne pas bloquer
            asyncio.create_task(send_pending_pin_notifications())
        except Exception as e:
            logger.debug(f"Note: Could not check pending pin notifications: {e}")
        
    except Exception as e:
        logger.error(f"❌ Error in _process_incoming_message (from={message.get('from', 'unknown')}, account_id={account_id}): {e}", exc_info=True)
        # Ne pas lever l'exception pour ne pas bloquer le traitement des autres messages
        # Mais on log l'erreur pour le débogage


async def _process_status(status_payload: Dict[str, Any], account: Dict[str, Any]):
    message_id = status_payload.get("id")
    status_value = status_payload.get("status")
    recipient_id = status_payload.get("recipient_id")
    timestamp_iso = _timestamp_to_iso(status_payload.get("timestamp"))
    
    # Extraire les informations d'erreur si le statut est "failed"
    error_message = None
    if status_value == "failed":
        # WhatsApp peut envoyer des détails d'erreur dans différents champs
        errors = status_payload.get("errors", [])
        if errors and isinstance(errors, list) and len(errors) > 0:
            # Prendre le premier message d'erreur
            error_obj = errors[0]
            error_code = error_obj.get("code")
            error_title = error_obj.get("title", "")
            error_details = error_obj.get("details", "")
            
            # Traduire les codes d'erreur courants en français
            error_translations = {
                131026: "Message non livrable",
                131030: "Numéro non autorisé (liste blanche requise)",
                131042: "Problème d'éligibilité du compte (paiement/facturation)",
                131047: "Message hors fenêtre gratuite (nécessite un template)",
                131048: "Numéro de téléphone invalide",
                131051: "Le destinataire n'a pas WhatsApp",
                131052: "Le destinataire a bloqué ce numéro",
                100: "Erreur d'authentification",
                190: "Token d'accès expiré",
            }
            
            # Détecter spécifiquement si le destinataire n'a pas WhatsApp
            is_no_whatsapp_error = error_code in [131026, 131051] or (
                error_code == 131026 and "undeliverable" in error_title.lower()
            )
            
            # Utiliser la traduction si disponible, sinon utiliser le titre original
            translated_title = error_translations.get(error_code, error_title)
            
            # Construire le message d'erreur
            if error_code:
                error_message = f"Code {error_code}: {translated_title}"
            else:
                error_message = translated_title if translated_title else error_title
            
            # Ajouter les détails si disponibles
            if error_details:
                error_message += f" - {error_details}"
            
            # Ajouter des conseils pour les erreurs courantes
            if is_no_whatsapp_error:
                error_message += " ⚠️ Ce numéro ne semble pas avoir de compte WhatsApp actif. Vérifiez que le destinataire a WhatsApp installé et que le numéro est correct."
            elif error_code == 131030:
                error_message += " ⚠️ Votre compte WhatsApp Business est en mode test. Pour envoyer des messages à ce numéro, vous devez l'ajouter à votre liste de numéros autorisés dans Meta Business Suite (Phone Numbers > Manage > Add phone number). Une fois votre compte approuvé par Meta, cette restriction sera levée."
            elif error_code == 131026:
                error_message += " (Vérifiez que le numéro est valide et que le destinataire a WhatsApp installé)"
            elif error_code == 131042:
                error_message += " ⚠️ Votre compte WhatsApp Business n'est pas éligible pour envoyer des templates. Vérifiez: 1) La méthode de paiement dans Meta Business Suite, 2) Que le compte est vérifié (pas en mode test), 3) Les limites d'utilisation de votre compte."
            elif error_code == 131047:
                error_message += " (Utilisez un template de message approuvé pour envoyer hors fenêtre gratuite)"
        elif status_payload.get("error"):
            # Format alternatif
            error_message = str(status_payload.get("error"))

    if not message_id or not status_value:
        return

    if get_pool():
        existing_row = await fetch_one(
            "SELECT id, conversation_id FROM messages WHERE wa_message_id = $1 LIMIT 1",
            message_id,
        )
    else:
        existing = await supabase_execute(
            supabase.table("messages")
            .select("id, conversation_id")
            .eq("wa_message_id", message_id)
            .limit(1)
        )
        existing_row = existing.data[0] if existing.data else None

    if existing_row:
        record = dict(existing_row) if get_pool() else existing_row
        message_db_id = record["id"]
        conv_id = record["conversation_id"]
        if get_pool():
            if error_message:
                await execute(
                    "UPDATE messages SET status = $2, timestamp = $3::timestamptz, error_message = $4 WHERE id = $1::uuid",
                    message_db_id,
                    status_value,
                    _parse_timestamp_iso(timestamp_iso),
                    error_message,
                )
            else:
                await execute(
                    "UPDATE messages SET status = $2, timestamp = $3::timestamptz WHERE id = $1::uuid",
                    message_db_id,
                    status_value,
                    _parse_timestamp_iso(timestamp_iso),
                )
        else:
            update_data = {"status": status_value, "timestamp": timestamp_iso}
            if error_message:
                update_data["error_message"] = error_message
            await supabase_execute(
                supabase.table("messages").update(update_data).eq("id", message_db_id)
            )
        await _update_conversation_timestamp(conv_id, timestamp_iso)
        
        # 🆕 Mettre à jour les stats de campagne si applicable
        try:
            from app.services.broadcast_service import update_recipient_stat_from_webhook
            await update_recipient_stat_from_webhook(
                wa_message_id=message_id,
                status=status_value,
                timestamp=timestamp_iso,
                error_message=error_message,
            )
        except Exception as e:
            logger.debug(f"Broadcast stat update (not a broadcast message or error): {e}")
        
        # Si le message est lu (status = "read") et qu'il a un template auto-créé, le supprimer
        if status_value == "read":
            try:
                from app.services.pending_template_service import delete_auto_template_for_message
                # Lancer la suppression en arrière-plan (non bloquant)
                asyncio.create_task(delete_auto_template_for_message(message_db_id))
            except Exception as e:
                logger.warning(f"⚠️ Erreur lors de la tentative de suppression du template auto-créé: {e}")
        
        return

    if not recipient_id or not account:
        return

    account_id = account.get("id")
    if get_pool():
        conv_row = await fetch_one(
            "SELECT id FROM conversations WHERE account_id = $1::uuid AND client_number = $2 LIMIT 1",
            account_id,
            recipient_id,
        )
        if conv_row:
            conv = dict(conv_row)
        else:
            contact = await _upsert_contact(recipient_id, None, None)
            conv = await _upsert_conversation(account_id, contact["id"], recipient_id, timestamp_iso)
        existing_msg_row = await fetch_one(
            "SELECT id, content_text FROM messages WHERE wa_message_id = $1 LIMIT 1",
            message_id,
        )
        if existing_msg_row:
            if error_message:
                await execute(
                    "UPDATE messages SET status = $2, timestamp = $3::timestamptz, error_message = $4 WHERE id = $1::uuid",
                    existing_msg_row["id"],
                    status_value,
                    _parse_timestamp_iso(timestamp_iso),
                    error_message,
                )
            else:
                await execute(
                    "UPDATE messages SET status = $2, timestamp = $3::timestamptz WHERE id = $1::uuid",
                    existing_msg_row["id"],
                    status_value,
                    _parse_timestamp_iso(timestamp_iso),
                )
        else:
            await execute(
                """
                INSERT INTO messages (conversation_id, direction, content_text, timestamp, wa_message_id, message_type, status)
                VALUES ($1::uuid, 'outbound', '[status update]', $2::timestamptz, $3, $4, $5)
                ON CONFLICT (wa_message_id) DO UPDATE SET status = EXCLUDED.status, timestamp = EXCLUDED.timestamp
                """,
                conv["id"],
                _parse_timestamp_iso(timestamp_iso),
                message_id,
                status_payload.get("type") or "status",
                status_value,
            )
    else:
        conversation = await supabase_execute(
            supabase.table("conversations")
            .select("id")
            .eq("account_id", account_id)
            .eq("client_number", recipient_id)
            .limit(1)
        )
        if conversation.data:
            conv = conversation.data[0]
        else:
            contact = await _upsert_contact(recipient_id, None, None)
            conv = await _upsert_conversation(account_id, contact["id"], recipient_id, timestamp_iso)
        existing_msg = await supabase_execute(
            supabase.table("messages").select("id, content_text").eq("wa_message_id", message_id).limit(1)
        )
        if existing_msg.data:
            existing_record = existing_msg.data[0]
            update_data = {"status": status_value, "timestamp": timestamp_iso}
            if error_message:
                update_data["error_message"] = error_message
            await supabase_execute(
                supabase.table("messages").update(update_data).eq("id", existing_record["id"])
            )
        else:
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
    profile_picture_url: Optional[str] = None,
):
    """Crée ou met à jour un contact avec son nom et son image de profil."""
    if get_pool():
        row = await fetch_one(
            """
            INSERT INTO contacts (whatsapp_number, display_name, profile_picture_url)
            VALUES ($1, $2, $3)
            ON CONFLICT (whatsapp_number) DO UPDATE SET
                display_name = COALESCE(EXCLUDED.display_name, contacts.display_name),
                profile_picture_url = COALESCE(EXCLUDED.profile_picture_url, contacts.profile_picture_url)
            RETURNING *
            """,
            wa_id,
            profile_name,
            profile_picture_url,
        )
        return dict(row) if row else None
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
    if get_pool():
        existing = await fetch_one(
            "SELECT bot_enabled FROM conversations WHERE account_id = $1::uuid AND client_number = $2 LIMIT 1",
            account_id,
            client_number,
        )
        bot_enabled = existing.get("bot_enabled") if existing else None
        row = await fetch_one(
            """
            INSERT INTO conversations (contact_id, client_number, account_id, status, updated_at, bot_enabled)
            VALUES ($1::uuid, $2, $3::uuid, 'open', $4::timestamptz, $5)
            ON CONFLICT (account_id, client_number) DO UPDATE SET
                contact_id = EXCLUDED.contact_id,
                status = 'open',
                updated_at = EXCLUDED.updated_at,
                bot_enabled = COALESCE(conversations.bot_enabled, EXCLUDED.bot_enabled)
            RETURNING *
            """,
            contact_id,
            client_number,
            account_id,
            _parse_timestamp_iso(timestamp_iso),
            bot_enabled if bot_enabled is not None else False,
        )
        return dict(row) if row else None
    existing = await supabase_execute(
        supabase.table("conversations")
        .select("bot_enabled")
        .eq("account_id", account_id)
        .eq("client_number", client_number)
        .limit(1)
    )
    bot_enabled = existing.data[0].get("bot_enabled") if existing.data else None
    upsert_data = {
        "contact_id": contact_id,
        "client_number": client_number,
        "account_id": account_id,
        "status": "open",
        "updated_at": timestamp_iso,
    }
    if bot_enabled is not None:
        upsert_data["bot_enabled"] = bot_enabled
    res = await supabase_execute(
        supabase.table("conversations").upsert(upsert_data, on_conflict="account_id,client_number")
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
        logger.info(f"🔍 [EXTRACT TEXT] Interactive message detected: type={interactive.get('type')}")
        logger.info(f"🔍 [EXTRACT TEXT] Full interactive data: {json.dumps(interactive, indent=2, ensure_ascii=False)}")
        if interactive.get("type") == "button_reply":
            button_reply = interactive.get("button_reply", {})
            title = button_reply.get("title", "")
            logger.info(f"🔍 [EXTRACT TEXT] Button reply: title={title}, full_data={json.dumps(button_reply, indent=2, ensure_ascii=False)}")
            return title
        if interactive.get("type") == "list_reply":
            list_reply = interactive.get("list_reply", {})
            title = list_reply.get("title", "")
            row_id = list_reply.get("id", "")
            description = list_reply.get("description", "")
            logger.info(f"🔍 [EXTRACT TEXT] List reply detected:")
            logger.info(f"   - title: {title}")
            logger.info(f"   - id: {row_id}")
            logger.info(f"   - description: {description}")
            logger.info(f"   - full list_reply data: {json.dumps(list_reply, indent=2, ensure_ascii=False)}")
            # Construire un texte plus complet avec toutes les infos
            text_parts = [title]
            if description:
                text_parts.append(description)
            if row_id:
                text_parts.append(f"[ID: {row_id}]")
            return " | ".join(text_parts) if len(text_parts) > 1 else title

    if msg_type == "button":
        # Gérer les réponses de boutons de template WhatsApp
        button_data = message.get("button", {})
        # Préférer "text" qui est le texte affiché, sinon utiliser "payload"
        return button_data.get("text") or button_data.get("payload", "")

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


def _parse_timestamp_iso(ts: Optional[str]) -> datetime:
    """Parse ISO timestamp string to timezone-aware datetime for asyncpg (timestamptz)."""
    if not ts:
        return datetime.now(timezone.utc)
    if isinstance(ts, datetime):
        return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
    s = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


async def _update_conversation_timestamp(conversation_id: str, timestamp_iso: Optional[str] = None):
    ts = timestamp_iso or datetime.now(timezone.utc).isoformat()
    if get_pool():
        await execute(
            "UPDATE conversations SET updated_at = $2::timestamptz WHERE id = $1::uuid",
            conversation_id,
            _parse_timestamp_iso(ts),
        )
    else:
        await supabase_execute(
            supabase.table("conversations").update({"updated_at": ts}).eq("id", conversation_id)
        )
    from app.core.cache import invalidate_cache_pattern
    await invalidate_cache_pattern(f"conversation:{conversation_id}")
    # OPTIMISATION: Invalider aussi le cache de la fenêtre gratuite
    # car un nouveau message entrant change potentiellement le statut
    from app.core.cache import get_cache
    cache = await get_cache()
    await cache.delete(f"free_window:{conversation_id}")


async def _save_failed_message(conversation_id: str, content_text: str, timestamp_iso: str, error_message: str):
    """Stocke un message échoué dans la base de données"""
    try:
        if get_pool():
            await execute(
                """
                INSERT INTO messages (conversation_id, direction, content_text, timestamp, message_type, status, error_message)
                VALUES ($1::uuid, 'outbound', $2, $3::timestamptz, 'text', 'failed', $4)
                """,
                conversation_id,
                content_text,
                _parse_timestamp_iso(timestamp_iso),
                error_message,
            )
        else:
            message_payload = {
                "conversation_id": conversation_id,
                "direction": "outbound",
                "content_text": content_text,
                "timestamp": timestamp_iso,
                "message_type": "text",
                "status": "failed",
                "error_message": error_message,
            }
            await supabase_execute(
                supabase.table("messages").insert(message_payload)
            )
        await _update_conversation_timestamp(conversation_id, timestamp_iso)
    except Exception as e:
        logger.error("Error saving failed message to database: %s", e, exc_info=True)


async def _increment_unread_count(conversation: Dict[str, Any]):
    current = conversation.get("unread_count") or 0
    new_value = current + 1
    if get_pool():
        await execute(
            "UPDATE conversations SET unread_count = $2 WHERE id = $1::uuid",
            conversation["id"],
            new_value,
        )
    else:
        await supabase_execute(
            supabase.table("conversations").update({"unread_count": new_value}).eq(
                "id", conversation["id"]
            )
        )
    conversation["unread_count"] = new_value
    from app.core.cache import invalidate_cache_pattern
    await invalidate_cache_pattern(f"conversation:{conversation['id']}")


async def _maybe_trigger_bot_reply(
    conversation_id: str,
    content_text: Optional[str],
    contact: Dict[str, Any],
    message_type: Optional[str] = "text",
):
    print(f"🔍 [BOT DEBUG] _maybe_trigger_bot_reply called for conversation {conversation_id}, content_text length: {len(content_text or '')}, message_type: {message_type}")
    logger.info(f"🔍 [BOT DEBUG] _maybe_trigger_bot_reply called for conversation {conversation_id}, content_text length: {len(content_text or '')}, message_type: {message_type}")
    
    message_text = (content_text or "").strip()
    if not message_text:
        logger.info(f"ℹ️ [BOT DEBUG] Bot skip: empty message for conversation {conversation_id}")
        return

    logger.info(f"🔍 [BOT DEBUG] Fetching conversation {conversation_id} to check bot status")
    conversation = await get_conversation_by_id(conversation_id)
    
    if not conversation:
        logger.warning(f"⚠️ [BOT DEBUG] Conversation {conversation_id} not found, cannot trigger bot")
        return
        
    logger.info(f"🔍 [BOT DEBUG] Conversation found: id={conversation_id}, bot_enabled={conversation.get('bot_enabled')}, account_id={conversation.get('account_id')}")
    
    if not conversation.get("bot_enabled"):
        logger.info(f"ℹ️ [BOT DEBUG] Bot skip: bot disabled for conversation {conversation_id}")
        return

    account_id = conversation["account_id"]
    logger.info(f"🔍 [BOT DEBUG] Account ID: {account_id}")

    if message_type and message_type.lower() != "text":
        fallback = "Je ne peux pas lire ce type de contenu, peux-tu me l'écrire ?"
        logger.info(f"ℹ️ [BOT DEBUG] Non-text message detected for {conversation_id} (type: {message_type}); sending fallback")
        await send_message({"conversation_id": conversation_id, "content": fallback}, skip_bot_trigger=True)
        return

    contact_name = contact.get("display_name") or contact.get("whatsapp_number")
    logger.info(f"🔍 [BOT DEBUG] Contact name: {contact_name}, contact data: {list(contact.keys())}")

    try:
        logger.info(
            f"🤖 [BOT DEBUG] Starting Gemini invocation for conversation {conversation_id} (account={account_id}, contact={contact_name}, message_length={len(message_text)})"
        )
        reply = await bot_service.generate_bot_reply(
            conversation_id,
            conversation["account_id"],
            message_text,
            contact_name,
        )
        logger.info(f"✅ [BOT DEBUG] Gemini returned reply: length={len(reply) if reply else 0}, preview: '{reply[:100] if reply else None}...'")
    except Exception as exc:
        logger.error(f"❌ [BOT DEBUG] Bot generation failed for {conversation_id}: {exc}", exc_info=True)
        return

    if not reply:
        logger.info(f"ℹ️ [BOT DEBUG] Gemini returned empty text for {conversation_id}, escalating to human")
        await send_message({"conversation_id": conversation_id, "content": FALLBACK_MESSAGE}, skip_bot_trigger=True)
        await _escalate_to_human(conversation, message_text)
        return

    normalized_reply = reply.strip().lower()
    requires_escalation = normalized_reply == FALLBACK_MESSAGE.lower()

    logger.info(f"🔍 [BOT DEBUG] Sending bot reply for conversation {conversation_id}, reply length: {len(reply)}")
    send_result = await send_message({"conversation_id": conversation_id, "content": reply}, skip_bot_trigger=True)
    
    if isinstance(send_result, dict) and send_result.get("error"):
        logger.error(f"❌ [BOT DEBUG] Bot send failed for {conversation_id}: {send_result}")
        if message_type and message_type != "text":
            logger.info(f"ℹ️ [BOT DEBUG] Disabling bot for {conversation_id} after unsupported content")
            await set_conversation_bot_mode(conversation_id, False)
        return

    logger.info(f"✅ [BOT DEBUG] Bot reply sent successfully for conversation {conversation_id} (length={len(reply)})")
    await supabase_execute(
        supabase.table("conversations")
        .update({"bot_last_reply_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", conversation_id)
    )
    logger.info(f"✅ [BOT DEBUG] Updated bot_last_reply_at for conversation {conversation_id}")
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
    pool = get_pool()
    if pool:
        # PostgreSQL direct: 1 requête messages + 1 quoted + 1 reactions (ou 2 si pas de quoted)
        sql = """
            SELECT * FROM messages
            WHERE conversation_id = $1::uuid
        """
        params: list = [conversation_id]
        if before:
            sql += " AND timestamp < $2::timestamptz"
            params.append(_parse_timestamp_iso(before))
        sql += " ORDER BY timestamp DESC LIMIT " + ("$3" if before else "$2")
        params.append(limit)
        rows_raw = await fetch_all(sql, *params)
        rows = [dict(r) for r in rows_raw]
        rows.reverse()

        reply_to_ids = list({msg.get("reply_to_message_id") for msg in rows if msg.get("reply_to_message_id")})
        message_ids = [msg["id"] for msg in rows]

        async def fetch_quoted():
            if not reply_to_ids:
                return {}
            quoted_rows = await fetch_all(
                "SELECT * FROM messages WHERE id = ANY($1::uuid[])",
                reply_to_ids,
            )
            return {str(r["id"]): dict(r) for r in quoted_rows}

        async def fetch_reactions():
            if not rows:
                return {}
            reactions_rows = await fetch_all(
                "SELECT * FROM message_reactions WHERE message_id = ANY($1::uuid[])",
                message_ids,
            )
            by_msg = {}
            for r in reactions_rows:
                mid = r["message_id"]
                if mid not in by_msg:
                    by_msg[mid] = []
                by_msg[mid].append(dict(r))
            return by_msg

        quoted_messages, reactions_by_message = await asyncio.gather(fetch_quoted(), fetch_reactions())

        for msg in rows:
            rid = msg.get("reply_to_message_id")
            msg["reply_to_message"] = quoted_messages.get(str(rid)) if rid else None
            msg["reactions"] = reactions_by_message.get(msg["id"], [])
        return rows

    # Fallback Supabase API
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

    reply_to_message_ids = [msg.get("reply_to_message_id") for msg in rows if msg.get("reply_to_message_id")]
    quoted_messages = {}
    if reply_to_message_ids:
        for i in range(0, len(reply_to_message_ids), SUPABASE_IN_CLAUSE_CHUNK_SIZE):
            chunk = reply_to_message_ids[i : i + SUPABASE_IN_CLAUSE_CHUNK_SIZE]
            quoted_res = await supabase_execute(
                supabase.table("messages").select("*").in_("id", chunk)
            )
            if quoted_res.data:
                for quoted_msg in quoted_res.data:
                    quoted_messages[quoted_msg["id"]] = quoted_msg

    for msg in rows:
        if msg.get("reply_to_message_id") and msg["reply_to_message_id"] in quoted_messages:
            msg["reply_to_message"] = quoted_messages[msg["reply_to_message_id"]]
        else:
            msg["reply_to_message"] = None

    if rows:
        message_ids = [msg["id"] for msg in rows]
        reactions_by_message = {}
        for i in range(0, len(message_ids), SUPABASE_IN_CLAUSE_CHUNK_SIZE):
            chunk = message_ids[i : i + SUPABASE_IN_CLAUSE_CHUNK_SIZE]
            reactions_res = await supabase_execute(
                supabase.table("message_reactions").select("*").in_("message_id", chunk)
            )
            for reaction in reactions_res.data or []:
                msg_id = reaction["message_id"]
                if msg_id not in reactions_by_message:
                    reactions_by_message[msg_id] = []
                reactions_by_message[msg_id].append(reaction)
        for msg in rows:
            msg["reactions"] = reactions_by_message.get(msg["id"], [])
    return rows


async def update_message_content(
    message_id: str, new_content: str, user_id: str
) -> Dict[str, Any]:
    """
    Met à jour le contenu d'un message texte (édition locale uniquement).
    Conserve la première version dans edited_original_content et marque edited_at/edited_by.
    """
    if get_pool():
        msg = await fetch_one(
            "SELECT id, content_text, message_type, direction, edited_original_content FROM messages WHERE id = $1::uuid LIMIT 1",
            message_id,
        )
        if not msg:
            return {"error": "message_not_found"}
        msg = dict(msg)
        if msg.get("message_type", "text") not in ("text", None, ""):
            return {"error": "message_not_editable"}
        if msg.get("direction") != "outbound":
            return {"error": "cannot_edit_incoming_message"}
        now_iso = datetime.now(timezone.utc).isoformat()
        original = msg.get("edited_original_content") or msg.get("content_text")
        await execute(
            """
            UPDATE messages SET content_text = $2, edited_at = $3::timestamptz, edited_by = $4::uuid, edited_original_content = $5
            WHERE id = $1::uuid
            """,
            message_id,
            new_content,
            _parse_timestamp_iso(now_iso),
            user_id,
            original,
        )
        refreshed = await fetch_one("SELECT * FROM messages WHERE id = $1::uuid LIMIT 1", message_id)
        if not refreshed:
            return {"error": "update_fetch_failed"}
        return {"success": True, "message": dict(refreshed)}
    msg_res = await supabase_execute(
        supabase.table("messages")
        .select("id, content_text, conversation_id, message_type, direction, edited_original_content")
        .eq("id", message_id)
        .range(0, 0)
    )
    if not msg_res.data:
        return {"error": "message_not_found"}
    msg = msg_res.data[0]
    if msg.get("message_type", "text") not in ("text", None, ""):
        return {"error": "message_not_editable"}
    if msg.get("direction") != "outbound":
        return {"error": "cannot_edit_incoming_message"}
    now_iso = datetime.now(timezone.utc).isoformat()
    original = msg.get("edited_original_content") or msg.get("content_text")
    update_res = await supabase_execute(
        supabase.table("messages")
        .update(
            {
                "content_text": new_content,
                "edited_at": now_iso,
                "edited_by": user_id,
                "edited_original_content": original,
            }
        )
        .eq("id", message_id)
    )
    if not update_res.data:
        return {"error": "update_failed"}
    refreshed = await supabase_execute(
        supabase.table("messages").select("*").eq("id", message_id).range(0, 0)
    )
    if not refreshed.data:
        return {"error": "update_fetch_failed"}
    return {"success": True, "message": refreshed.data[0]}


async def delete_message_scope(
    message_id: str, scope: str, user_id: str
) -> Dict[str, Any]:
    """
    Supprime un message pour l'utilisateur courant (scope=me) ou pour tous (scope=all, local).
    """
    if get_pool():
        msg = await fetch_one(
            "SELECT id, conversation_id, direction, deleted_for_all_at, deleted_for_user_ids FROM messages WHERE id = $1::uuid LIMIT 1",
            message_id,
        )
        if not msg:
            return {"error": "message_not_found"}
        msg = dict(msg)
        now_iso = datetime.now(timezone.utc).isoformat()
        if scope == "all":
            await execute(
                "UPDATE messages SET deleted_for_all_at = $2::timestamptz WHERE id = $1::uuid",
                message_id,
                _parse_timestamp_iso(now_iso),
            )
        else:
            existing = msg.get("deleted_for_user_ids") or []
            if user_id not in existing:
                existing.append(user_id)
            await execute(
                "UPDATE messages SET deleted_for_user_ids = $2::jsonb WHERE id = $1::uuid",
                message_id,
                json.dumps(existing),
            )
        refreshed = await fetch_one("SELECT * FROM messages WHERE id = $1::uuid LIMIT 1", message_id)
        if not refreshed:
            return {"error": "update_fetch_failed"}
        return {"success": True, "message": dict(refreshed)}
    msg_res = await supabase_execute(
        supabase.table("messages")
        .select("id, conversation_id, direction, deleted_for_all_at, deleted_for_user_ids")
        .eq("id", message_id)
        .range(0, 0)
    )
    if not msg_res.data:
        return {"error": "message_not_found"}
    msg = msg_res.data[0]
    now_iso = datetime.now(timezone.utc).isoformat()
    if scope == "all":
        update_payload = {"deleted_for_all_at": now_iso}
    else:
        existing = msg.get("deleted_for_user_ids") or []
        if user_id not in existing:
            existing.append(user_id)
        update_payload = {"deleted_for_user_ids": existing}
    update_res = await supabase_execute(
        supabase.table("messages").update(update_payload).eq("id", message_id)
    )
    if not update_res.data:
        return {"error": "update_failed"}
    refreshed = await supabase_execute(
        supabase.table("messages").select("*").eq("id", message_id).range(0, 0)
    )
    if not refreshed.data:
        return {"error": "update_fetch_failed"}
    return {"success": True, "message": refreshed.data[0]}


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
        msg = await fetch_one("SELECT id FROM messages WHERE id = $1::uuid LIMIT 1", message_id)
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


async def send_message(payload: dict, skip_bot_trigger: bool = False, force_send: bool = False, is_system: bool = False):
    """
    Envoie un message WhatsApp.
    
    Si force_send=True, envoie même hors fenêtre gratuite (sera facturé comme message conversationnel par WhatsApp).
    Si force_send=False, essaie d'abord gratuitement, puis utilise template si hors fenêtre.
    
    Args:
        payload: Dict avec 'conversation_id' et 'content'
        skip_bot_trigger: Si True, ne déclenche pas le bot après envoi (utilisé quand le bot envoie lui-même)
        force_send: Si True, force l'envoi même hors fenêtre (sans template, message conversationnel normal)
        is_system: Si True, marque le message comme système (ne sera pas affiché dans l'interface)
    """
    import asyncio
    
    print(f"📤 [SEND MESSAGE] send_message() called: conversation_id={payload.get('conversation_id')}, content_length={len(payload.get('content', '') or '')}, skip_bot_trigger={skip_bot_trigger}, force_send={force_send}")
    logger.info(f"📤 [SEND MESSAGE] send_message() called: conversation_id={payload.get('conversation_id')}, content_length={len(payload.get('content', '') or '')}, skip_bot_trigger={skip_bot_trigger}, force_send={force_send}")
    
    conv_id = payload.get("conversation_id")
    text = payload.get("content")

    if not conv_id or not text:
        print(f"❌ [SEND MESSAGE] Invalid payload: conv_id={conv_id}, text_length={len(text or '')}")
        return {"error": "invalid_payload", "message": "conversation_id and content are required"}

    # Vérifier si on est dans la fenêtre gratuite
    is_free, last_inbound_time = await is_within_free_window(conv_id)
    
    # Si hors fenêtre gratuite, essayer d'abord sans template
    # Si WhatsApp refuse (erreur 131047), on utilisera un template en fallback
    if not is_free and not force_send:
        # Si force_send=False, utiliser le système avec fallback template
        return await send_message_with_template_fallback(payload, skip_bot_trigger=skip_bot_trigger)

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

    # Ajouter le contexte de réponse si reply_to_message_id est fourni
    reply_to_message_id = payload.get("reply_to_message_id")
    if reply_to_message_id:
        # Récupérer le message original pour obtenir son wa_message_id
        try:
            original_message_result = await supabase_execute(
                supabase.table("messages")
                .select("wa_message_id")
                .eq("id", reply_to_message_id)
                .single()
            )
            if original_message_result.data and original_message_result.data.get("wa_message_id"):
                wa_message_id = original_message_result.data["wa_message_id"]
                body["context"] = {"message_id": wa_message_id}
                logger.info(f"📎 [SEND MESSAGE] Adding reply context: reply_to_message_id={reply_to_message_id}, wa_message_id={wa_message_id}")
        except Exception as e:
            logger.warning(f"⚠️ [SEND MESSAGE] Could not fetch original message for reply: {e}")
            # Continuer sans contexte si on ne peut pas récupérer le message original

    # Utiliser le client HTTP partagé avec retry automatique
    timestamp_iso = datetime.now(timezone.utc).isoformat()
    
    # Vérifier si on est dans la fenêtre gratuite pour le prix
    is_free, _ = await is_within_free_window(conv_id)
    # Utiliser message conversationnel (pas de template) si hors fenêtre
    price_info = await calculate_message_price(conv_id, use_template=False, use_conversational=not is_free)
    
    try:
        response = await _send_to_whatsapp_with_retry(phone_id, token, body)
    except httpx.HTTPError as exc:
        logger.error("WhatsApp API error after retries: %s", exc)
        error_details = str(exc)
        status_code = 0
        error_code = None
        if hasattr(exc, "response") and exc.response:
            status_code = exc.response.status_code
            try:
                error_json = exc.response.json()
                if isinstance(error_json, dict):
                    error_obj = error_json.get("error", {})
                    if isinstance(error_obj, dict):
                        error_code = error_obj.get("code")
                        error_message = error_obj.get("message", "")
                        if error_code:
                            error_details = f"Code {error_code}"
                            if error_message:
                                error_details += f": {error_message}"
            except (ValueError, KeyError, AttributeError):
                pass
        
        # Si erreur 131047 (Re-engagement message), essayer avec un template
        if error_code == 131047 or (isinstance(error_details, str) and "131047" in error_details):
            logger.info(f"🔄 Erreur 131047 détectée dans exception - tentative avec template pour conversation {conv_id}")
            # Essayer avec un template en fallback
            template_result = await send_message_with_template_fallback(payload, skip_bot_trigger=skip_bot_trigger)
            if not template_result.get("error"):
                return template_result
            # Si le template échoue aussi, continuer avec l'erreur originale
        
        # Stocker le message échoué dans la base de données
        await _save_failed_message(conv_id, text, timestamp_iso, error_details)
        
        return {
            "error": "whatsapp_api_error",
            "status_code": status_code,
            "details": error_details,
        }

    if response.is_error:
        logger.error("WhatsApp send error: %s %s", response.status_code, response.text)
        error_details = response.text
        error_code = None
        try:
            error_json = response.json()
            if isinstance(error_json, dict):
                error_obj = error_json.get("error", {})
                if isinstance(error_obj, dict):
                    error_code = error_obj.get("code")
                    error_message = error_obj.get("message", "")
                    error_type = error_obj.get("type", "")
                    error_subcode = error_obj.get("error_subcode")
                    if error_code:
                        error_details = f"Code {error_code}"
                        if error_type:
                            error_details += f" ({error_type})"
                        if error_message:
                            error_details += f": {error_message}"
                        if error_subcode:
                            error_details += f" [Subcode: {error_subcode}]"
        except (ValueError, KeyError):
            pass
        
        # Si erreur 131047 (Re-engagement message), essayer avec un template
        if error_code == 131047 or (isinstance(error_details, str) and "131047" in error_details):
            logger.info(f"🔄 Erreur 131047 détectée - tentative avec template pour conversation {conv_id}")
            # Essayer avec un template en fallback
            template_result = await send_message_with_template_fallback(payload, skip_bot_trigger=skip_bot_trigger)
            if not template_result.get("error"):
                return template_result
            # Si le template échoue aussi, continuer avec l'erreur originale
        
        # Stocker le message échoué dans la base de données
        await _save_failed_message(conv_id, text, timestamp_iso, error_details)
        
        return {
            "error": "whatsapp_api_error",
            "status_code": response.status_code,
            "details": error_details,
        }

    message_id = None
    try:
        response_json = response.json()
        message_id = response_json.get("messages", [{}])[0].get("id")
    except ValueError:
        response_json = None

    # Retourner immédiatement après l'envoi à WhatsApp
    # L'insertion en base se fera en arrière-plan pour ne pas bloquer la réponse
    message_payload = {
        "conversation_id": conv_id,
        "direction": "outbound",
        "content_text": text,
        "timestamp": timestamp_iso,
        "wa_message_id": message_id,
        "message_type": "text",
        "status": "sent",
        "is_system": is_system,
    }
    
    # Ajouter reply_to_message_id si présent
    if reply_to_message_id:
        message_payload["reply_to_message_id"] = reply_to_message_id

    async def _save_message_async():
        try:
            if get_pool():
                await execute(
                    """
                    INSERT INTO messages (conversation_id, direction, content_text, timestamp, wa_message_id, message_type, status, is_system, reply_to_message_id)
                    VALUES ($1::uuid, 'outbound', $2, $3::timestamptz, $4, 'text', 'sent', $5, $6::uuid)
                    ON CONFLICT (wa_message_id) DO UPDATE SET status = 'sent', timestamp = EXCLUDED.timestamp, content_text = EXCLUDED.content_text
                    """,
                    conv_id,
                    text,
                    _parse_timestamp_iso(timestamp_iso),
                    message_id,
                    message_payload.get("is_system", False),
                    message_payload.get("reply_to_message_id"),
                )
                await _update_conversation_timestamp(conv_id, timestamp_iso)
            else:
                await asyncio.gather(
                    supabase_execute(
                        supabase.table("messages").upsert(message_payload, on_conflict="wa_message_id")
                    ),
                    _update_conversation_timestamp(conv_id, timestamp_iso)
                )
        except Exception as e:
            logger.error("Error saving message to database in background: %s", e, exc_info=True)
    
    asyncio.create_task(_save_message_async())

    # En mode production, le bot répond uniquement aux messages entrants via webhook
    # On ne déclenche pas le bot pour les messages sortants depuis l'interface

    result = {"status": "sent", "message_id": message_id}
    result["is_free"] = is_free
    result["price_usd"] = price_info.get("price_usd", 0.0)
    result["price_eur"] = price_info.get("price_eur", 0.0)
    result["category"] = price_info.get("category", "free" if is_free else "paid")
    return result


async def is_within_free_window(conversation_id: str) -> Tuple[bool, Optional[datetime]]:
    """
    Vérifie si on est dans la fenêtre de 24h pour envoyer un message gratuit.
    
    OPTIMISATION: Cache de 5 minutes pour éviter les requêtes DB répétées.
    Le cache est invalidé lorsqu'un nouveau message entrant arrive.
    
    WhatsApp Cloud API permet d'envoyer des messages gratuits pendant 24h
    après la dernière interaction CLIENT (message entrant uniquement).
    
    Les messages sortants (notre part) ne comptent pas pour réinitialiser la fenêtre.
    Les messages échoués (status='failed') ne sont pas considérés comme des interactions valides.
    
    Returns:
        Tuple[bool, Optional[datetime]]: 
        - (True, last_interaction_time) si dans la fenêtre gratuite
        - (False, last_interaction_time) si hors fenêtre (nécessite un template payant)
        - (False, None) si aucun message trouvé
    """
    # OPTIMISATION: Vérifier le cache d'abord (TTL: 5 minutes)
    from app.core.cache import get_cache
    cache = await get_cache()
    cache_key = f"free_window:{conversation_id}"
    
    cached_result = await cache.get(cache_key)
    if cached_result is not None:
        is_free, last_interaction_time = cached_result
        logger.debug(f"🕐 Free window CACHE HIT for conversation {conversation_id}: is_free={is_free}")
        return (is_free, last_interaction_time)
    
    # Récupérer le dernier message ENTRANT (client) de la conversation
    # Seuls les messages entrants comptent pour la fenêtre gratuite
    # Exclure les messages échoués car ils ne comptent pas comme interaction valide
    # Note: .neq() inclut automatiquement les valeurs NULL, donc les messages sans statut sont inclus
    last_message = await supabase_execute(
        supabase.table("messages")
        .select("timestamp, direction, status")
        .eq("conversation_id", conversation_id)
        .eq("direction", "inbound")  # Seulement les messages entrants (clients)
        .neq("status", "failed")  # Exclure uniquement les messages échoués (inclut NULL et autres statuts)
        .order("timestamp", desc=True)
        .limit(1)
    )
    
    if not last_message.data or len(last_message.data) == 0:
        logger.warning(f"⚠️ No valid messages found for conversation {conversation_id} (excluding failed messages)")
        return (False, None)
    
    last_message_data = last_message.data[0]
    last_interaction_time_str = last_message_data["timestamp"]
    last_interaction_direction = last_message_data.get("direction", "unknown")
    
    # Parser le timestamp
    try:
        if isinstance(last_interaction_time_str, str):
            # Gérer différents formats de timestamp
            if "T" in last_interaction_time_str:
                last_interaction_time = datetime.fromisoformat(last_interaction_time_str.replace("Z", "+00:00"))
            else:
                last_interaction_time = datetime.fromisoformat(last_interaction_time_str)
        else:
            last_interaction_time = last_interaction_time_str
        
        # S'assurer que c'est timezone-aware
        if last_interaction_time.tzinfo is None:
            last_interaction_time = last_interaction_time.replace(tzinfo=timezone.utc)
        
        # Calculer la différence avec maintenant
        now = datetime.now(timezone.utc)
        time_diff = now - last_interaction_time
        hours_elapsed = time_diff.total_seconds() / 3600
        
        # Fenêtre gratuite = 24 heures après la dernière interaction
        is_free = hours_elapsed < 24.0
        
        logger.info(
            f"🕐 Free window check for conversation {conversation_id}: "
            f"last_interaction={last_interaction_time} ({last_interaction_direction}), "
            f"hours_elapsed={hours_elapsed:.2f}, is_free={is_free}"
        )
        
        # OPTIMISATION: Mettre en cache le résultat (TTL: 5 minutes)
        # Le cache sera invalidé lors de l'arrivée d'un nouveau message entrant
        await cache.set(cache_key, (is_free, last_interaction_time), ttl_seconds=300)
        
        return (is_free, last_interaction_time)
        
    except Exception as e:
        logger.error(f"❌ Error parsing timestamp {last_interaction_time_str}: {e}", exc_info=True)
        return (False, None)


async def calculate_message_price(conversation_id: str, use_template: bool = False, use_conversational: bool = False) -> Dict[str, Any]:
    """
    Calcule le prix d'un message WhatsApp.
    
    Args:
        conversation_id: ID de la conversation
        use_template: Si True, utilise un template UTILITY (le moins cher)
        use_conversational: Si True, utilise un message conversationnel normal (plus cher que template)
    
    Returns:
        Dict avec:
        - is_free: bool
        - price_usd: float (0.0 si gratuit)
        - price_eur: float (0.0 si gratuit)
        - currency: str
        - category: str ("free", "utility", "conversational")
        - last_inbound_time: Optional[datetime]
    """
    is_free, last_interaction_time = await is_within_free_window(conversation_id)
    
    # Si on est dans la fenêtre gratuite, retourner gratuit peu importe les autres paramètres
    if is_free:
        return {
            "is_free": True,
            "price_usd": 0.0,
            "price_eur": 0.0,
            "currency": "USD",
            "category": "free",
            "last_inbound_time": last_interaction_time.isoformat() if last_interaction_time else None
        }
    
    # Hors fenêtre gratuite - calculer le prix selon le type de message
    if use_template:
        # Prix des templates WhatsApp UTILITY
        # Prix en Europe : 0,0248 € par message UTILITY
        utility_price_usd = 0.0248
        utility_price_eur = 0.0248
        return {
            "is_free": False,
            "price_usd": utility_price_usd,
            "price_eur": utility_price_eur,
            "currency": "USD",
            "category": "utility",
            "last_inbound_time": last_interaction_time.isoformat() if last_interaction_time else None,
            "template_required": True
        }
    
    # Message conversationnel normal (hors fenêtre, sans template)
    # L'assistance classique 24h est gratuite (géré par is_free ci-dessus)
    # Pour les messages hors fenêtre, utiliser le prix UTILITY
    conversational_price_usd = 0.0248
    conversational_price_eur = 0.0248
    
    return {
        "is_free": False,
        "price_usd": conversational_price_usd,
        "price_eur": conversational_price_eur,
        "currency": "USD",
        "category": "conversational",
        "last_inbound_time": last_interaction_time.isoformat() if last_interaction_time else None,
        "template_required": False
    }


async def _get_or_create_default_template(account: Dict[str, Any]) -> Optional[str]:
    """
    Récupère ou crée un template UTILITY par défaut pour envoyer des messages.
    Retourne le nom du template ou None si erreur.
    """
    try:
        phone_id = account.get("phone_number_id")
        token = account.get("access_token")
        
        if not phone_id or not token:
            return None
        
        # Récupérer le WABA ID depuis le phone number
        try:
            phone_details = await get_phone_number_details(phone_id, token)
            waba_id = phone_details.get("waba_id") or phone_details.get("whatsapp_business_account_id")
        except Exception as e:
            logger.warning(f"Could not get WABA ID: {e}")
            # Essayer avec phone_id directement (parfois phone_id = waba_id)
            waba_id = phone_id
        
        if not waba_id:
            logger.error("Could not determine WABA ID")
            return None
        
        # Chercher un template UTILITY existant avec statut APPROVED
        templates_res = await list_message_templates(waba_id, token, limit=100)
        templates = templates_res.get("data", [])
        
        # Chercher un template UTILITY approuvé
        for template in templates:
            if (template.get("status") == "APPROVED" and 
                template.get("category") == "UTILITY"):
                logger.info(f"✅ Found existing UTILITY template: {template.get('name')}")
                return template.get("name")
        
        # Si aucun template UTILITY trouvé, on ne peut pas en créer un automatiquement
        # (nécessite validation Meta). On retourne None et l'utilisateur devra créer un template.
        logger.warning("⚠️ No UTILITY template found. User must create one in Meta Business Manager.")
        return None
        
    except Exception as e:
        logger.error(f"Error getting/creating template: {e}", exc_info=True)
        return None


async def send_message_with_template_fallback(payload: dict, skip_bot_trigger: bool = False):
    """
    Envoie un message WhatsApp. Essaie d'abord gratuitement, puis utilise un template UTILITY si hors fenêtre.
    
    Args:
        payload: Dict avec 'conversation_id' et 'content'
        skip_bot_trigger: Si True, ne déclenche pas le bot après envoi
    
    Returns:
        Dict avec 'status', 'message_id', 'is_free', 'price_usd', etc.
    """
    conv_id = payload.get("conversation_id")
    text = payload.get("content")

    if not conv_id or not text:
        return {"error": "invalid_payload", "message": "conversation_id and content are required"}

    # Vérifier si on est dans la fenêtre gratuite
    is_free, last_inbound_time = await is_within_free_window(conv_id)
    
    # Si gratuit, envoyer normalement
    if is_free:
        logger.info(f"✅ Sending free message within 24h window for conversation {conv_id}")
        result = await send_message(payload, skip_bot_trigger=skip_bot_trigger)
        if result.get("error"):
            return result
        result["is_free"] = True
        result["price_usd"] = 0.0
        result["price_eur"] = 0.0
        return result
    
    # Hors fenêtre : utiliser un template UTILITY
    logger.info(f"💰 Sending paid message with UTILITY template for conversation {conv_id}")
    
    conversation = await get_conversation_by_id(conv_id)
    if not conversation:
        return {"error": "conversation_not_found"}
    
    account = await get_account_by_id(conversation.get("account_id"))
    if not account:
        return {"error": "account_not_found"}
    
    # Récupérer ou créer un template UTILITY
    template_name = await _get_or_create_default_template(account)
    
    if not template_name:
        return {
            "error": "template_required",
            "message": (
                "Aucun template UTILITY trouvé. Vous devez créer un template de message "
                "dans Meta Business Manager avec la catégorie UTILITY pour envoyer des messages hors fenêtre gratuite."
            ),
            "requires_template": True
        }
    
    # Envoyer via template
    phone_id = account.get("phone_number_id") or settings.WHATSAPP_PHONE_ID
    token = account.get("access_token") or settings.WHATSAPP_TOKEN
    to_number = conversation["client_number"]
    
    try:
        # Créer les composants du template avec le texte du message
        components = [
            {
                "type": "BODY",
                "text": text
            }
        ]
        
        response = await send_template_message(
            phone_number_id=phone_id,
            access_token=token,
            to=to_number,
            template_name=template_name,
            language_code="fr",
            components=components
        )
        
        message_id = response.get("messages", [{}])[0].get("id")
        timestamp_iso = datetime.now(timezone.utc).isoformat()
        
        # Sauvegarder le message
        message_payload = {
            "conversation_id": conv_id,
            "direction": "outbound",
            "content_text": text,
            "timestamp": timestamp_iso,
            "wa_message_id": message_id,
            "message_type": "template",
            "status": "sent",
        }
        
        async def _save_message_async():
            try:
                if get_pool():
                    await execute(
                        """
                        INSERT INTO messages (conversation_id, direction, content_text, timestamp, wa_message_id, message_type, status)
                        VALUES ($1::uuid, 'outbound', $2, $3::timestamptz, $4, 'template', 'sent')
                        ON CONFLICT (wa_message_id) DO UPDATE SET status = 'sent', timestamp = EXCLUDED.timestamp
                        """,
                        conv_id,
                        text,
                        _parse_timestamp_iso(timestamp_iso),
                        message_id,
                    )
                    await _update_conversation_timestamp(conv_id, timestamp_iso)
                else:
                    await asyncio.gather(
                        supabase_execute(
                            supabase.table("messages").upsert(message_payload, on_conflict="wa_message_id")
                        ),
                        _update_conversation_timestamp(conv_id, timestamp_iso)
                    )
            except Exception as e:
                logger.error("Error saving template message to database: %s", e, exc_info=True)
        
        asyncio.create_task(_save_message_async())
        
        price_info = await calculate_message_price(conv_id, use_template=True)
        
        return {
            "status": "sent",
            "message_id": message_id,
            "is_free": False,
            "price_usd": price_info["price_usd"],
            "price_eur": price_info["price_eur"],
            "category": "utility",
            "template_name": template_name
        }
        
    except Exception as e:
        logger.error(f"Error sending template message: {e}", exc_info=True)
        return {
            "error": "template_send_error",
            "message": f"Erreur lors de l'envoi via template: {str(e)}"
        }


async def send_free_message(payload: dict, skip_bot_trigger: bool = False):
    """
    Envoie un message WhatsApp uniquement si on est dans la fenêtre gratuite de 24h.
    
    Si on est hors fenêtre, retourne une erreur indiquant qu'un template est nécessaire.
    
    Args:
        payload: Dict avec 'conversation_id' et 'content'
        skip_bot_trigger: Si True, ne déclenche pas le bot après envoi
    
    Returns:
        Dict avec 'status' et 'message_id' si succès, ou 'error' si hors fenêtre
    """
    conv_id = payload.get("conversation_id")
    text = payload.get("content")

    if not conv_id or not text:
        return {"error": "invalid_payload", "message": "conversation_id and content are required"}

    # Vérifier si on est dans la fenêtre gratuite
    is_free, last_inbound_time = await is_within_free_window(conv_id)
    
    if not is_free:
        if last_inbound_time is None:
            error_msg = "Aucun message entrant trouvé. Vous devez utiliser un template de message pour initier la conversation."
        else:
            hours_elapsed = (datetime.now(timezone.utc) - last_inbound_time).total_seconds() / 3600
            error_msg = (
                f"Fenêtre gratuite expirée. Le dernier message entrant date de {hours_elapsed:.1f} heures. "
                f"Vous devez utiliser un template de message approuvé pour envoyer ce message."
            )
        
        logger.warning(f"⚠️ Attempt to send free message outside window: {error_msg}")
        return {
            "error": "free_window_expired",
            "message": error_msg,
            "last_inbound_time": last_inbound_time.isoformat() if last_inbound_time else None,
            "requires_template": True
        }
    
    # Si on est dans la fenêtre gratuite, utiliser la fonction send_message normale
    logger.info(f"✅ Sending free message within 24h window for conversation {conv_id}")
    return await send_message(payload, skip_bot_trigger=skip_bot_trigger)


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

    logger.info("=" * 80)
    logger.info(f"📤 [SEND-INTERACTIVE-STORAGE] ========== ENVOI MESSAGE INTERACTIF ==========")
    logger.info(f"📤 [SEND-INTERACTIVE-STORAGE] conversation_id={conversation_id}")
    logger.info(f"📤 [SEND-INTERACTIVE-STORAGE] interactive_type={interactive_type}")
    logger.info(f"📤 [SEND-INTERACTIVE-STORAGE] Paramètres reçus:")
    logger.info(f"   - body_text: {repr(body_text)}")
    logger.info(f"   - header_text: {repr(header_text)}")
    logger.info(f"   - footer_text: {repr(footer_text)}")
    logger.info(f"   - interactive_payload: {json.dumps(interactive_payload, indent=2, ensure_ascii=False)}")
    
    # Construire le payload pour WhatsApp
    interactive_obj = {
        "type": interactive_type,
        "body": {"text": body_text}
    }
    
    if header_text:
        interactive_obj["header"] = {"type": "text", "text": header_text}
        logger.info(f"📤 [SEND-INTERACTIVE-STORAGE] Header ajouté: {repr(header_text)}")
    else:
        logger.warning(f"⚠️ [SEND-INTERACTIVE-STORAGE] AUCUN HEADER (header_text={repr(header_text)})")
    
    if footer_text:
        interactive_obj["footer"] = {"text": footer_text}
        logger.info(f"📤 [SEND-INTERACTIVE-STORAGE] Footer ajouté: {repr(footer_text)}")
    else:
        logger.warning(f"⚠️ [SEND-INTERACTIVE-STORAGE] AUCUN FOOTER (footer_text={repr(footer_text)})")
    
    # Ajouter action (buttons ou sections)
    interactive_obj["action"] = interactive_payload
    logger.info(f"📤 [SEND-INTERACTIVE-STORAGE] Action ajoutée: {json.dumps(interactive_payload, indent=2, ensure_ascii=False)}")

    body = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "interactive",
        "interactive": interactive_obj
    }
    
    logger.info(f"📤 [SEND-INTERACTIVE-STORAGE] Payload complet envoyé à WhatsApp:")
    logger.info(f"📤 [SEND-INTERACTIVE-STORAGE] {json.dumps(body, indent=2, ensure_ascii=False)}")
    logger.info(f"📤 [SEND-INTERACTIVE-STORAGE] ==============================================")

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
        interactive_data_json = json.dumps({
            "type": interactive_type,
            "header": header_text,
            "body": body_text,
            "footer": footer_text,
            "action": interactive_payload
        })
        if get_pool():
            await execute(
                """
                INSERT INTO messages (conversation_id, direction, content_text, timestamp, wa_message_id, message_type, status, interactive_data)
                VALUES ($1::uuid, 'outbound', $2, $3::timestamptz, $4, 'interactive', 'sent', $5::jsonb)
                ON CONFLICT (wa_message_id) DO UPDATE SET status = 'sent', timestamp = EXCLUDED.timestamp, interactive_data = EXCLUDED.interactive_data
                """,
                conversation_id,
                preview_text,
                _parse_timestamp_iso(timestamp_iso),
                message_id,
                interactive_data_json,
            )
            await _update_conversation_timestamp(conversation_id, timestamp_iso)
        else:
            message_payload = {
                "conversation_id": conversation_id,
                "direction": "outbound",
                "content_text": preview_text,
                "timestamp": timestamp_iso,
                "wa_message_id": message_id,
                "message_type": "interactive",
                "status": "sent",
                "interactive_data": interactive_data_json,
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
    Envoie un message média ET l'enregistre correctement dans la base.
    Si hors fenêtre des 24h, crée un template avec l'image en HEADER et "(image)" en BODY.
    """
    if not conversation_id or not media_id:
        return {"error": "invalid_payload"}

    # Vérifier si on est dans la fenêtre gratuite
    is_free, last_inbound_time = await is_within_free_window(conversation_id)
    
    # Si dans la fenêtre gratuite, envoyer normalement
    if is_free:
        return await _send_media_message_normal(conversation_id, media_type, media_id, caption)
    
    # Hors fenêtre : créer un template avec l'image en HEADER
    logger.info(f"💰 Sending paid media message with template for conversation {conversation_id}")
    
    # Pour les images, utiliser un template avec HEADER IMAGE
    if media_type == "image":
        return await _send_image_with_template_queue(conversation_id, media_id, caption)
    
    # Pour les autres types de médias, essayer d'envoyer normalement (sera facturé)
    logger.warning(f"⚠️ Media type {media_type} hors fenêtre - envoi normal (sera facturé)")
    return await _send_media_message_normal(conversation_id, media_type, media_id, caption)


async def _send_media_message_normal(
    conversation_id: str,
    media_type: str,
    media_id: str,
    caption: Optional[str] = None
):
    """Envoie un message média normalement (dans la fenêtre gratuite)"""
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

    # Enregistrer le message dans la base d'abord pour obtenir son ID
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

    if get_pool():
        row = await fetch_one(
            """
            INSERT INTO messages (conversation_id, direction, content_text, timestamp, wa_message_id, message_type, status, media_id, media_mime_type)
            VALUES ($1::uuid, 'outbound', $2, $3::timestamptz, $4, $5, 'sent', $6, $7)
            ON CONFLICT (wa_message_id) DO UPDATE SET status = 'sent', timestamp = EXCLUDED.timestamp, media_id = EXCLUDED.media_id
            RETURNING id
            """,
            conversation_id,
            message_payload.get("content_text") or "",
            _parse_timestamp_iso(message_payload["timestamp"]),
            message_payload["wa_message_id"],
            message_payload["message_type"],
            message_payload.get("media_id"),
            message_payload.get("media_mime_type"),
        )
        message_db_id = row["id"] if row else None
    else:
        await supabase_execute(
            supabase.table("messages").upsert(message_payload, on_conflict="wa_message_id")
        )
        message_db_id = None
        if message_id:
            existing_msg = await supabase_execute(
                supabase.table("messages").select("id").eq("wa_message_id", message_id).limit(1)
            )
            if existing_msg.data:
                message_db_id = existing_msg.data[0].get("id")
                logger.debug(f"✅ Outbound message ID retrieved: {message_db_id}")
            else:
                logger.warning(f"⚠️ Outbound message inserted but ID not found by wa_message_id: {message_id}")
        else:
            logger.warning("⚠️ Outbound message has no wa_message_id, cannot retrieve database ID")
    
    # Télécharger et stocker le média dans Supabase Storage en arrière-plan
    if message_db_id and media_id and media_type in ("image", "video", "audio", "document", "sticker"):
        logger.info(f"📥 Outbound media detected: message_id={message_db_id}, media_id={media_id}, type={media_type}")
        
        # Créer la tâche avec gestion d'erreur
        task = asyncio.create_task(_download_and_store_media_async(
            message_db_id=message_db_id,
            media_id=media_id,
            account=account,
            mime_type=None,  # Sera détecté depuis WhatsApp
            filename=None
        ))
        
        # Ajouter un callback pour logger les erreurs
        def log_task_result(t):
            try:
                if t.exception() is not None:
                    logger.error(f"❌ Outbound media download task failed for message_id={message_db_id}: {t.exception()}", exc_info=t.exception())
                else:
                    logger.debug(f"✅ Outbound media download task completed for message_id={message_db_id}")
            except Exception as e:
                logger.error(f"❌ Error in outbound task callback: {e}")
        
        task.add_done_callback(log_task_result)
    
    await _update_conversation_timestamp(conversation_id, timestamp_iso)

    return {"status": "sent", "message_id": message_id}


async def _send_image_with_template_queue(
    conversation_id: str,
    media_id: str,
    caption: Optional[str] = None
):
    """
    Crée un template avec l'image en HEADER et "(image)" en BODY, puis attend l'approbation.
    """
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        return {"error": "conversation_not_found"}

    account = await get_account_by_id(conversation.get("account_id"))
    if not account:
        return {"error": "account_not_found"}

    # Créer le message en base avec status "pending"
    display_text = caption if caption else "(image)"
    timestamp_iso = datetime.now(timezone.utc).isoformat()
    if get_pool():
        row = await fetch_one(
            """
            INSERT INTO messages (conversation_id, direction, content_text, status, timestamp, message_type, media_id)
            VALUES ($1::uuid, 'outbound', $2, 'pending', $3::timestamptz, 'image', $4)
            RETURNING id
            """,
            conversation_id,
            display_text,
            _parse_timestamp_iso(timestamp_iso),
            media_id,
        )
        if not row:
            logger.error("❌ Échec de la création du message en base")
            return {"error": "failed_to_create_message"}
        message_id = row["id"]
    else:
        message_payload = {
            "conversation_id": conversation_id,
            "direction": "outbound",
            "content_text": display_text,
            "status": "pending",
            "timestamp": timestamp_iso,
            "message_type": "image",
            "media_id": media_id,
        }
        message_result = await supabase_execute(
            supabase.table("messages").insert(message_payload)
        )
        if not message_result.data or len(message_result.data) == 0:
            logger.error("❌ Échec de la création du message en base")
            return {"error": "failed_to_create_message"}
        message_id = message_result.data[0]["id"]
    logger.info(f"✅ Message créé en base: message_id={message_id}")
    
    from app.services.pending_template_service import create_and_queue_image_template
    template_result = await create_and_queue_image_template(
        conversation_id=conversation_id,
        account_id=conversation["account_id"],
        message_id=message_id,
        media_id=media_id,
        body_text=display_text
    )
    
    if not template_result.get("success"):
        error_message = "; ".join(template_result.get("errors", ["Erreur inconnue"]))
        logger.error(f"❌ Erreur de création du template: {error_message}")
        if get_pool():
            await execute(
                "UPDATE messages SET status = 'failed', error_message = $2 WHERE id = $1::uuid",
                message_id,
                error_message,
            )
        else:
            await supabase_execute(
                supabase.table("messages")
                .update({"status": "failed", "error_message": error_message})
                .eq("id", message_id)
            )
        return {
            "error": "template_creation_failed",
            "message": error_message
        }
    
    logger.info(f"✅ Template créé avec succès, en attente d'approbation Meta")
    return {
        "status": "pending",
        "message_id": message_id,
        "template_name": template_result.get("template_name"),
        "message": "Image en cours de validation par Meta. Elle sera envoyée automatiquement une fois approuvée."
    }


def _extract_media_metadata(message: Dict[str, Any]) -> Dict[str, Optional[str]]:
    msg_type = message.get("type")
    if isinstance(msg_type, str):
        msg_type = msg_type.lower()
    media_section: Optional[Dict[str, Any]] = None

    logger.debug(f"🔍 [MEDIA EXTRACT] Extracting media metadata for type: {msg_type}")

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

    if media_section:
        logger.debug(f"🔍 [MEDIA EXTRACT] Found media_section: {media_section}")
        if media_section.get("id"):
            result = {
                "media_id": media_section.get("id"),
                "media_mime_type": media_section.get("mime_type"),
                "media_filename": media_section.get("filename") or media_section.get("sha256"),
            }
            logger.info(f"✅ [MEDIA EXTRACT] Extracted media_id: {result.get('media_id')}")
            return result
        else:
            logger.warning(f"⚠️ [MEDIA EXTRACT] media_section found but no 'id' field: {media_section}")
    else:
        logger.debug(f"ℹ️ [MEDIA EXTRACT] No media_section found for type: {msg_type}")

    return {}


async def get_message_by_id(message_id: str) -> Optional[Dict[str, Any]]:
    if get_pool():
        row = await fetch_one("SELECT * FROM messages WHERE id = $1::uuid LIMIT 1", message_id)
        return dict(row) if row else None
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
    logger.info(f"🚀 [MEDIA DOWNLOAD] Starting media download and storage: message_id={message_db_id}, media_id={media_id}, account_id={account.get('id')}, account_name={account.get('name')}")
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
        # Télécharger et stocker dans Supabase Storage (asynchrone et non-bloquant)
        # IMPORTANT: Passer le token pour authentifier la requête de téléchargement
        # L'upload se fait maintenant en arrière-plan, cette fonction retourne immédiatement
        await download_and_store_message_media(
            message_id=message_db_id,
            media_url=download_url,
            content_type=detected_mime_type,
            filename=filename or meta_json.get("file_name"),
            access_token=token,  # Passer le token pour authentifier le téléchargement
            account=account  # Passer le compte pour Google Drive si configuré
        )
        
        # L'upload et la mise à jour du message se font maintenant en arrière-plan
        # via la tâche asynchrone dans storage_service._upload_media_task
        logger.info(f"✅ [ASYNC UPLOAD] Media download and upload task created: message_id={message_db_id}")
            
    except Exception as e:
        logger.error(f"❌ Error downloading and storing media: message_id={message_db_id}, error={e}", exc_info=True)


async def _upload_to_google_drive_async(
    message_db_id: str,
    account: Dict[str, Any],
    storage_url: str,
    filename: str,
    mime_type: str
):
    """
    Upload un fichier vers Google Drive de manière asynchrone et non-bloquante.
    Cette fonction est appelée dans une tâche séparée pour ne pas bloquer le traitement principal.
    """
    try:
        logger.info(f"🚀 [GOOGLE DRIVE] Starting upload task: message_id={message_db_id}, account_id={account.get('id')}, filename={filename}")
        
        # Récupérer le message pour obtenir conversation_id
        logger.info(f"🔍 [GOOGLE DRIVE] Fetching conversation_id for message_id={message_db_id}")
        msg_result = await supabase_execute(
            supabase.table("messages")
            .select("conversation_id")
            .eq("id", message_db_id)
            .limit(1)
        )
        
        if not msg_result.data or not msg_result.data[0].get("conversation_id"):
            logger.warning(f"⚠️ [GOOGLE DRIVE] No conversation_id found for message_id={message_db_id}")
            return
        
        conversation_id = msg_result.data[0]["conversation_id"]
        logger.info(f"✅ [GOOGLE DRIVE] Found conversation_id={conversation_id} for message_id={message_db_id}")
        
        # Récupérer la conversation pour obtenir client_number
        logger.info(f"🔍 [GOOGLE DRIVE] Fetching client_number for conversation_id={conversation_id}")
        conv_result = await supabase_execute(
            supabase.table("conversations")
            .select("client_number")
            .eq("id", conversation_id)
            .limit(1)
        )
        
        if not conv_result.data or not conv_result.data[0].get("client_number"):
            logger.warning(f"⚠️ [GOOGLE DRIVE] No client_number found for conversation_id={conversation_id}")
            return
        
        client_number = conv_result.data[0]["client_number"]
        logger.info(f"✅ [GOOGLE DRIVE] Found client_number={client_number} for conversation_id={conversation_id}")
        
        # Télécharger le fichier depuis Supabase Storage pour l'upload vers Google Drive
        from app.services.google_drive_service import upload_document_to_google_drive
        import httpx
        
        logger.info(f"📥 [GOOGLE DRIVE] Downloading file from Supabase Storage: storage_url={storage_url}, message_id={message_db_id}")
        # Télécharger depuis storage_url
        async with httpx.AsyncClient(timeout=60.0) as client:
            file_response = await client.get(storage_url)
            file_response.raise_for_status()
            file_data = file_response.content
            logger.info(f"✅ [GOOGLE DRIVE] File downloaded successfully: size={len(file_data)} bytes, message_id={message_db_id}")
        
        logger.info(f"📤 [GOOGLE DRIVE] Calling upload_document_to_google_drive: message_id={message_db_id}, phone={client_number}, filename={filename}, mime_type={mime_type}, account_id={account.get('id')}")
        # Upload vers Google Drive
        drive_file_id = await upload_document_to_google_drive(
            account=account,
            phone_number=client_number,
            file_data=file_data,
            filename=filename,
            mime_type=mime_type
        )
        
        if drive_file_id:
            logger.info(f"✅ [GOOGLE DRIVE] Upload successful: message_id={message_db_id}, drive_file_id={drive_file_id}, phone={client_number}, filename={filename}")
            # Marquer le message comme uploadé dans la DB
            await supabase_execute(
                supabase.table("messages")
                .update({"google_drive_file_id": drive_file_id})
                .eq("id", message_db_id)
            )
            logger.info(f"✅ [GOOGLE DRIVE] Message marked as uploaded in DB: message_id={message_db_id}")
        else:
            logger.warning(f"⚠️ [GOOGLE DRIVE] Upload returned None: message_id={message_db_id}, phone={client_number}, filename={filename}. Check Google Drive service logs for details.")
            
    except Exception as gd_error:
        # Ne pas faire échouer le stockage Supabase si Google Drive échoue
        logger.error(f"❌ [GOOGLE DRIVE] Upload error (non-blocking): message_id={message_db_id}, account_id={account.get('id')}, error={gd_error}", exc_info=True)


async def backfill_media_to_google_drive(account_id: str, limit: int = 100) -> Dict[str, Any]:
    """
    Upload les médias existants vers Google Drive pour un compte donné.
    Ne télécharge que les médias qui n'ont pas encore été uploadés (google_drive_file_id is null).
    
    Args:
        account_id: ID du compte WhatsApp
        limit: Nombre maximum de médias à traiter par batch
    
    Returns:
        Dict avec les statistiques du backfill
    """
    logger.info(f"🔄 [GOOGLE DRIVE BACKFILL] Starting backfill for account_id={account_id}, limit={limit}")
    
    # Récupérer le compte (forcer le refresh depuis la DB pour éviter le cache)
    from app.services.account_service import invalidate_account_cache
    invalidate_account_cache(account_id)
    account = await get_account_by_id(account_id)
    if not account:
        raise ValueError(f"Account {account_id} not found")
    
    # Vérifier que Google Drive est configuré avec des logs détaillés
    google_drive_enabled = account.get("google_drive_enabled", False)
    has_access_token = bool(account.get("google_drive_access_token"))
    has_refresh_token = bool(account.get("google_drive_refresh_token"))
    google_drive_connected = has_access_token and has_refresh_token
    
    logger.info(f"🔍 [GOOGLE DRIVE BACKFILL] Account check: enabled={google_drive_enabled}, has_access_token={has_access_token}, has_refresh_token={has_refresh_token}, connected={google_drive_connected}")
    logger.info(f"🔍 [GOOGLE DRIVE BACKFILL] Account keys: {list(account.keys())}")
    
    if not (google_drive_enabled and google_drive_connected):
        missing = []
        if not google_drive_enabled:
            missing.append("google_drive_enabled=False")
        if not has_access_token:
            missing.append("access_token missing")
        if not has_refresh_token:
            missing.append("refresh_token missing")
        
        logger.warning(f"⚠️ [GOOGLE DRIVE BACKFILL] Google Drive not configured for account_id={account_id}. Missing: {', '.join(missing)}")
        return {
            "status": "skipped",
            "reason": f"Google Drive not configured: {', '.join(missing)}",
            "processed": 0,
            "uploaded": 0,
            "failed": 0
        }
    
    # Récupérer les conversations pour ce compte
    convs_result = await supabase_execute(
        supabase.table("conversations")
        .select("id, client_number")
        .eq("account_id", account_id)
    )
    
    if not convs_result.data:
        logger.info(f"✅ [GOOGLE DRIVE BACKFILL] No conversations found for account_id={account_id}")
        return {
            "status": "completed",
            "processed": 0,
            "uploaded": 0,
            "failed": 0
        }
    
    conversation_ids = [conv["id"] for conv in convs_result.data]
    conv_map = {conv["id"]: conv["client_number"] for conv in convs_result.data}
    
    # Récupérer les messages avec médias qui n'ont pas encore été uploadés vers Google Drive
    # Vérifier d'abord si la colonne google_drive_file_id existe
    column_exists = False
    try:
        # Tester si la colonne existe en essayant de la sélectionner
        test_query = supabase.table("messages").select("google_drive_file_id").limit(1)
        await supabase_execute(test_query)
        column_exists = True
        logger.info("✅ [GOOGLE DRIVE BACKFILL] Column google_drive_file_id exists")
    except Exception:
        # La colonne n'existe pas encore
        logger.warning("⚠️ [GOOGLE DRIVE BACKFILL] Column google_drive_file_id does not exist yet. Will process all media files. Please apply migration 029_add_google_drive_file_id_to_messages.sql")
    
    # Requêtes par chunks pour éviter URL trop longue (Cloudflare 400)
    result_data = []
    for i in range(0, len(conversation_ids), SUPABASE_IN_CLAUSE_CHUNK_SIZE):
        chunk = conversation_ids[i : i + SUPABASE_IN_CLAUSE_CHUNK_SIZE]
        query = (
            supabase.table("messages")
            .select("id, storage_url, media_filename, media_mime_type, conversation_id")
            .not_.is_("storage_url", "null")
            .in_("conversation_id", chunk)
            .in_("message_type", ["image", "video", "audio", "document", "sticker"])
        )
        if column_exists:
            query = query.is_("google_drive_file_id", "null")
        query = query.limit(limit)
        result = await supabase_execute(query)
        result_data.extend(result.data or [])
    result_data = result_data[:limit]
    
    if not result_data:
        logger.info(f"✅ [GOOGLE DRIVE BACKFILL] No media to upload for account_id={account_id}")
        return {
            "status": "completed",
            "processed": 0,
            "uploaded": 0,
            "failed": 0
        }
    
    logger.info(f"📋 [GOOGLE DRIVE BACKFILL] Found {len(result_data)} media files to upload for account_id={account_id}")
    
    uploaded = 0
    failed = 0
    
    for msg in result_data:
        message_id = msg["id"]
        storage_url = msg["storage_url"]
        conversation_id = msg["conversation_id"]
        client_number = conv_map.get(conversation_id)
        
        if not client_number:
            logger.warning(f"⚠️ [GOOGLE DRIVE BACKFILL] No client_number for conversation_id={conversation_id}, message_id={message_id}, skipping")
            failed += 1
            continue
        
        try:
            logger.info(f"🔄 [GOOGLE DRIVE BACKFILL] Processing message_id={message_id}, phone={client_number}")
            
            # Télécharger le fichier depuis Supabase Storage
            import httpx
            async with httpx.AsyncClient(timeout=60.0) as client:
                file_response = await client.get(storage_url)
                file_response.raise_for_status()
                file_data = file_response.content
            
            # Upload vers Google Drive
            from app.services.google_drive_service import upload_document_to_google_drive
            
            filename = msg.get("media_filename") or f"file_{message_id}"
            mime_type = msg.get("media_mime_type") or "application/octet-stream"
            
            drive_file_id = await upload_document_to_google_drive(
                account=account,
                phone_number=client_number,
                file_data=file_data,
                filename=filename,
                mime_type=mime_type
            )
            
            if drive_file_id:
                # Marquer le message comme uploadé (si la colonne existe)
                try:
                    await supabase_execute(
                        supabase.table("messages")
                        .update({"google_drive_file_id": drive_file_id})
                        .eq("id", message_id)
                    )
                    logger.info(f"✅ [GOOGLE DRIVE BACKFILL] Uploaded and marked message_id={message_id}, drive_file_id={drive_file_id}")
                except Exception as update_error:
                    # La colonne n'existe peut-être pas encore, mais l'upload a réussi
                    logger.warning(f"⚠️ [GOOGLE DRIVE BACKFILL] Uploaded message_id={message_id} but could not mark in DB (column may not exist): {update_error}")
                uploaded += 1
            else:
                failed += 1
                logger.warning(f"⚠️ [GOOGLE DRIVE BACKFILL] Upload failed for message_id={message_id}")
                
        except Exception as e:
            failed += 1
            logger.error(f"❌ [GOOGLE DRIVE BACKFILL] Error processing message_id={message_id}: {e}", exc_info=True)
    
    logger.info(f"✅ [GOOGLE DRIVE BACKFILL] Completed for account_id={account_id}: uploaded={uploaded}, failed={failed}, total={len(result.data)}")
    
    return {
        "status": "completed",
        "processed": len(result.data),
        "uploaded": uploaded,
        "failed": failed
    }