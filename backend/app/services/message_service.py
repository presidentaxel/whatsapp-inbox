import asyncio
import json
import logging
import sys
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

        # Pour les réponses de boutons, traiter comme un message texte normal
        # car le contenu est maintenant extrait dans content_text
        stored_message_type = "text" if msg_type == "button" else msg_type

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
        
        # Faire l'upsert
        await supabase_execute(
            supabase.table("messages").upsert(
                message_payload,
                on_conflict="wa_message_id",
            )
        )
        
        # Récupérer l'ID du message en cherchant par wa_message_id
        message_db_id = None
        if message.get("id"):
            existing_msg = await supabase_execute(
                supabase.table("messages")
                .select("id")
                .eq("wa_message_id", message.get("id"))
                .limit(1)
            )
            if existing_msg.data:
                message_db_id = existing_msg.data[0].get("id")
                logger.debug(f"✅ Message ID retrieved: {message_db_id}")
            else:
                logger.warning(f"⚠️ Message inserted but ID not found by wa_message_id: {message.get('id')}")
        else:
            logger.warning("⚠️ Message has no wa_message_id, cannot retrieve database ID")

        # Si c'est un média, télécharger et stocker dans Supabase Storage en arrière-plan
        if message_db_id and media_meta.get("media_id") and msg_type in ("image", "video", "audio", "document", "sticker"):
            logger.info(f"📥 Media detected: message_id={message_db_id}, media_id={media_meta.get('media_id')}, type={msg_type}")
            # Récupérer l'account pour le token
            account = await get_account_by_id(account_id)
            if account:
                logger.info(f"✅ Account found, starting async media download for message_id={message_db_id}")
                
                # Créer la tâche avec gestion d'erreur
                task = asyncio.create_task(_download_and_store_media_async(
                    message_db_id=message_db_id,
                    media_id=media_meta.get("media_id"),
                    account=account,
                    mime_type=media_meta.get("media_mime_type"),
                    filename=media_meta.get("media_filename")
                ))
                
                # Ajouter un callback pour logger les erreurs
                def log_task_result(t):
                    try:
                        if t.exception() is not None:
                            logger.error(f"❌ Media download task failed for message_id={message_db_id}: {t.exception()}", exc_info=t.exception())
                        else:
                            logger.debug(f"✅ Media download task completed for message_id={message_db_id}")
                    except Exception as e:
                        logger.error(f"❌ Error in task callback: {e}")
                
                task.add_done_callback(log_task_result)
            else:
                logger.warning(f"❌ Account not found for account_id={account_id}, cannot download media")
        elif message_db_id and media_meta.get("media_id"):
            logger.warning(f"⚠️ Media detected but type '{msg_type}' not in supported types for storage")
        elif message_db_id:
            logger.debug(f"ℹ️ Message {message_db_id} has no media_id")
        else:
            logger.warning(f"⚠️ Could not determine message_db_id for media storage")

        await _update_conversation_timestamp(conversation["id"], timestamp_iso)
        await _increment_unread_count(conversation)

        # Recharger la conversation pour s'assurer qu'on a la valeur à jour de bot_enabled
        # (l'upsert pourrait avoir préservé une ancienne valeur)
        refreshed_conversation = await get_conversation_by_id(conversation["id"])
        if refreshed_conversation:
            conversation = refreshed_conversation
        
        logger.info(f"🔍 [BOT DEBUG] Processing incoming message: conversation_id={conversation['id']}, bot_enabled={conversation.get('bot_enabled')}, content_text length={len(content_text or '')}")
        await _maybe_trigger_bot_reply(conversation["id"], content_text, contact, message.get("type"))
        
        logger.info(f"✅ Message processed successfully: conversation_id={conversation['id']}, type={msg_type}, from={wa_id}")
        
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
            elif error_code == 131026:
                error_message += " (Vérifiez que le numéro est valide et que le destinataire a WhatsApp installé)"
            elif error_code == 131047:
                error_message += " (Utilisez un template de message approuvé pour envoyer hors fenêtre gratuite)"
        elif status_payload.get("error"):
            # Format alternatif
            error_message = str(status_payload.get("error"))

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
        # Ne mettre à jour que le statut et le timestamp, ne pas toucher au content_text
        update_data = {"status": status_value, "timestamp": timestamp_iso}
        if error_message:
            update_data["error_message"] = error_message
        await supabase_execute(
            supabase.table("messages")
            .update(update_data)
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

    # Vérifier si un message avec ce wa_message_id existe déjà
    existing_msg = await supabase_execute(
        supabase.table("messages")
        .select("id, content_text")
        .eq("wa_message_id", message_id)
        .limit(1)
    )
    
    # Si le message existe déjà, ne mettre à jour que le statut
    if existing_msg.data:
        existing_record = existing_msg.data[0]
        update_data = {"status": status_value, "timestamp": timestamp_iso}
        if error_message:
            update_data["error_message"] = error_message
        await supabase_execute(
            supabase.table("messages")
            .update(update_data)
            .eq("id", existing_record["id"])
        )
    else:
        # Si le message n'existe pas, créer un nouveau message de statut
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
    # Vérifier si la conversation existe déjà pour préserver bot_enabled
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
    
    # Préserver bot_enabled si la conversation existe déjà
    if bot_enabled is not None:
        upsert_data["bot_enabled"] = bot_enabled
    
    res = await supabase_execute(
        supabase.table("conversations").upsert(
            upsert_data,
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


async def _update_conversation_timestamp(conversation_id: str, timestamp_iso: Optional[str] = None):
    await supabase_execute(
        supabase.table("conversations")
        .update({"updated_at": timestamp_iso or datetime.now(timezone.utc).isoformat()})
        .eq("id", conversation_id)
    )
    # Invalider le cache pour garantir la cohérence
    from app.core.cache import invalidate_cache_pattern
    await invalidate_cache_pattern(f"conversation:{conversation_id}")


async def _save_failed_message(conversation_id: str, content_text: str, timestamp_iso: str, error_message: str):
    """Stocke un message échoué dans la base de données"""
    try:
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


async def update_message_content(
    message_id: str, new_content: str, user_id: str
) -> Dict[str, Any]:
    """
    Met à jour le contenu d'un message texte (édition locale uniquement).
    Conserve la première version dans edited_original_content et marque edited_at/edited_by.
    """
    msg_res = await supabase_execute(
        supabase.table("messages")
        .select("id, content_text, conversation_id, message_type, direction, edited_original_content")
        .eq("id", message_id)
        .range(0, 0)
    )
    if not msg_res.data:
        return {"error": "message_not_found"}

    msg = msg_res.data[0]

    # Limiter l'édition aux messages texte émis par nous
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

    # Recharger le message mis à jour (l'update builder ne supporte pas select/returning)
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
    Note: la suppression côté WhatsApp Cloud API n'est pas disponible : marquage DB/UX uniquement.
    """
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
        supabase.table("messages")
        .update(update_payload)
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


async def send_message(payload: dict, skip_bot_trigger: bool = False, force_send: bool = False):
    """
    Envoie un message WhatsApp.
    
    Si force_send=True, envoie même hors fenêtre gratuite (sera facturé comme message conversationnel par WhatsApp).
    Si force_send=False, essaie d'abord gratuitement, puis utilise template si hors fenêtre.
    
    Args:
        payload: Dict avec 'conversation_id' et 'content'
        skip_bot_trigger: Si True, ne déclenche pas le bot après envoi (utilisé quand le bot envoie lui-même)
        force_send: Si True, force l'envoi même hors fenêtre (sans template, message conversationnel normal)
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
    }

    # Exécuter l'insertion en base en arrière-plan (fire-and-forget)
    async def _save_message_async():
        try:
            await asyncio.gather(
                supabase_execute(
                    supabase.table("messages").upsert(message_payload, on_conflict="wa_message_id")
                ),
                _update_conversation_timestamp(conv_id, timestamp_iso)
            )
        except Exception as e:
            logger.error("Error saving message to database in background: %s", e, exc_info=True)
    
    # Lancer la sauvegarde en arrière-plan sans attendre
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

    # Faire l'upsert
    await supabase_execute(
        supabase.table("messages").upsert(message_payload, on_conflict="wa_message_id")
    )
    
    # Récupérer l'ID du message en cherchant par wa_message_id
    message_db_id = None
    if message_id:
        existing_msg = await supabase_execute(
            supabase.table("messages")
            .select("id")
            .eq("wa_message_id", message_id)
            .limit(1)
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