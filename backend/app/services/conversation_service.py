import logging
from typing import Optional

from fastapi import HTTPException

from app.core.cache import cached, invalidate_cache_pattern
from app.core.db import supabase, supabase_execute
from app.services.account_service import get_account_by_id

logger = logging.getLogger(__name__)


async def get_all_conversations(
    account_id: str,
    limit: int = 200,
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
    """
    Marque une conversation comme lue (unread_count = 0).
    Gère les erreurs gracieusement pour éviter les ECONNRESET.
    """
    try:
        await supabase_execute(
            supabase.table("conversations").update({"unread_count": 0}).eq("id", conversation_id)
        )
        # Invalider le cache pour forcer le rechargement (ne pas faire échouer si ça échoue)
        try:
            await invalidate_cache_pattern(f"conversation:{conversation_id}")
        except Exception as cache_error:
            logger.warning(f"Failed to invalidate cache for conversation {conversation_id}: {cache_error}")
        return True
    except Exception as e:
        logger.error(f"Error marking conversation {conversation_id} as read: {e}", exc_info=True)
        # Ne pas lever l'exception pour éviter ECONNRESET, mais retourner False
        return False


async def mark_conversation_unread(conversation_id: str) -> bool:
    """
    Marque une conversation comme non lue en mettant unread_count à 1.
    Permet à l'utilisateur de marquer manuellement une conversation pour y revenir plus tard.
    Gère les erreurs gracieusement pour éviter les ECONNRESET.
    """
    try:
        await supabase_execute(
            supabase.table("conversations").update({"unread_count": 1}).eq("id", conversation_id)
        )
        # Invalider le cache pour forcer le rechargement (ne pas faire échouer si ça échoue)
        try:
            await invalidate_cache_pattern(f"conversation:{conversation_id}")
        except Exception as cache_error:
            logger.warning(f"Failed to invalidate cache for conversation {conversation_id}: {cache_error}")
        return True
    except Exception as e:
        logger.error(f"Error marking conversation {conversation_id} as unread: {e}", exc_info=True)
        # Ne pas lever l'exception pour éviter ECONNRESET, mais retourner False
        return False


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


def normalize_phone_number(phone: str) -> Optional[str]:
    """
    Normalise un numéro de téléphone pour WhatsApp.
    Retire les espaces, tirets, parenthèses et le + initial.
    Convertit les numéros français (commençant par 0) en format international.
    Exemple: "+33 6 12 34 56 78" -> "33612345678"
    Exemple: "06 12 34 56 78" -> "33612345678"
    
    Returns:
        Numéro normalisé ou None si invalide
    """
    if not phone or not isinstance(phone, str):
        return None
    
    # Retirer tous les caractères non numériques sauf le + au début
    cleaned = phone.strip()
    has_plus = cleaned.startswith("+")
    if has_plus:
        cleaned = cleaned[1:]
    # Retirer tous les caractères non numériques
    cleaned = "".join(c for c in cleaned if c.isdigit())
    
    # Validation: WhatsApp nécessite au moins 7 chiffres (format international minimum)
    if len(cleaned) < 7:
        logger.warning(f"Phone number too short: {phone} -> {cleaned} (length: {len(cleaned)})")
        return None
    
    # Si le numéro commence par 0 et fait 10 chiffres (format français),
    # le convertir en format international en remplaçant le 0 par 33
    if cleaned.startswith("0") and len(cleaned) == 10:
        cleaned = "33" + cleaned[1:]  # Remplacer le 0 initial par 33
        logger.info(f"French phone number converted to international format: {phone} -> {cleaned}")
    
    # Si le numéro commence déjà par 33 et fait 11 chiffres, c'est déjà au format international
    # (33 + 9 chiffres = 11 chiffres au total)
    if cleaned.startswith("33") and len(cleaned) == 11:
        logger.debug(f"Phone number already in international format: {cleaned}")
    
    return cleaned


async def find_or_create_conversation(account_id: str, phone_number: str) -> Optional[dict]:
    """
    Trouve ou crée une conversation avec un numéro de téléphone.
    
    Args:
        account_id: ID du compte WhatsApp
        phone_number: Numéro de téléphone (format libre, sera normalisé)
    
    Returns:
        Dict de la conversation ou None si erreur
    """
    from fastapi import HTTPException
    
    # Normaliser le numéro
    try:
        normalized_phone = normalize_phone_number(phone_number)
        
        if not normalized_phone:
            logger.warning(f"Invalid phone number format: {phone_number} (normalized: {normalized_phone})")
            # Ne pas retourner None directement, lever une exception pour que l'endpoint puisse retourner un 400
            raise ValueError(f"Invalid phone number format: {phone_number}")
        
        logger.info(f"Normalized phone number: {phone_number} -> {normalized_phone}")
    except ValueError as e:
        # Re-raise ValueError pour que l'endpoint puisse retourner un 400
        raise
    except Exception as e:
        logger.error(f"Error normalizing phone number '{phone_number}': {e}", exc_info=True)
        raise ValueError(f"Error processing phone number: {str(e)}")
    
    # Vérifier que le compte existe
    try:
        account = await get_account_by_id(account_id)
        if not account:
            logger.warning(f"Account not found: {account_id}")
            return None
    except HTTPException:
        # Re-raise HTTPException pour que l'endpoint API puisse la gérer
        raise
    except Exception as e:
        logger.error(f"Error getting account {account_id}: {e}", exc_info=True)
        return None
    
    # Chercher une conversation existante
    try:
        logger.debug(f"Checking for existing conversation: account_id={account_id}, phone={normalized_phone}")
        existing = await supabase_execute(
            supabase.table("conversations")
            .select("*, contacts(display_name, whatsapp_number, profile_picture_url)")
            .eq("account_id", account_id)
            .eq("client_number", normalized_phone)
            .limit(1)
        )
        
        if existing.data and len(existing.data) > 0:
            # Conversation existante trouvée
            logger.info(f"Found existing conversation: {existing.data[0]['id']}")
            await invalidate_cache_pattern(f"conversation:{existing.data[0]['id']}")
            return existing.data[0]
        logger.debug("No existing conversation found, will create new one")
    except HTTPException:
        # Re-raise HTTPException pour que l'endpoint API puisse la gérer
        raise
    except Exception as e:
        logger.error(f"Error checking existing conversation: {e}", exc_info=True)
        return None
    
    # Créer le contact s'il n'existe pas
    try:
        logger.debug(f"Checking for existing contact: phone={normalized_phone}")
        contact_res = await supabase_execute(
            supabase.table("contacts")
            .select("id")
            .eq("whatsapp_number", normalized_phone)
            .limit(1)
        )
        
        contact_id = None
        if contact_res.data and len(contact_res.data) > 0:
            contact_id = contact_res.data[0]["id"]
            logger.debug(f"Found existing contact: {contact_id}")
        else:
            # Créer un nouveau contact
            logger.debug(f"Creating new contact: phone={normalized_phone}")
            try:
                # Insérer le contact (sans select car supabase_execute ne le supporte pas)
                await supabase_execute(
                    supabase.table("contacts")
                    .insert({"whatsapp_number": normalized_phone})
                )
                # Récupérer l'ID du contact créé
                new_contact = await supabase_execute(
                    supabase.table("contacts")
                    .select("id")
                    .eq("whatsapp_number", normalized_phone)
                    .limit(1)
                )
                if new_contact.data and len(new_contact.data) > 0:
                    contact_id = new_contact.data[0]["id"]
                    logger.info(f"Created new contact: {contact_id} for phone: {normalized_phone}")
                else:
                    logger.error(f"Contact creation returned no data for phone: {normalized_phone}")
            except HTTPException as he:
                logger.error(f"HTTPException creating contact: {he.detail} (status: {he.status_code})")
                # Re-raise HTTPException pour que l'endpoint API puisse la gérer
                raise
            except Exception as e:
                # Si erreur de duplication, récupérer le contact existant
                logger.warning(f"Error creating contact (may be duplicate): {e}", exc_info=True)
                try:
                    contact_retry = await supabase_execute(
                        supabase.table("contacts")
                        .select("id")
                        .eq("whatsapp_number", normalized_phone)
                        .limit(1)
                    )
                    if contact_retry.data and len(contact_retry.data) > 0:
                        contact_id = contact_retry.data[0]["id"]
                        logger.info(f"Retrieved existing contact after creation failure: {contact_id}")
                except HTTPException:
                    raise
                except Exception as e2:
                    logger.error(f"Error retrieving contact after creation failure: {e2}", exc_info=True)
        
        if not contact_id:
            logger.error(f"Failed to get or create contact for phone: {normalized_phone}")
            return None
    except HTTPException:
        # Re-raise HTTPException pour que l'endpoint API puisse la gérer
        raise
    except Exception as e:
        logger.error(f"Error in contact creation/retrieval: {e}", exc_info=True)
        return None
    
    # Créer la conversation (ou la récupérer si elle existe déjà)
    # Utiliser upsert pour éviter les erreurs de duplication
    from datetime import datetime, timezone
    timestamp_iso = datetime.now(timezone.utc).isoformat()
    
    # Vérifier à nouveau si la conversation existe (race condition possible)
    try:
        existing_check = await supabase_execute(
            supabase.table("conversations")
            .select("*, contacts(display_name, whatsapp_number, profile_picture_url)")
            .eq("account_id", account_id)
            .eq("client_number", normalized_phone)
            .limit(1)
        )
        
        if existing_check.data and len(existing_check.data) > 0:
            conversation = existing_check.data[0]
            await invalidate_cache_pattern(f"conversation:{conversation['id']}")
            return conversation
    except HTTPException:
        # Re-raise HTTPException pour que l'endpoint API puisse la gérer
        raise
    except Exception as e:
        logger.error(f"Error checking existing conversation (race condition check): {e}", exc_info=True)
        return None
    
    # Créer la conversation
    try:
        logger.debug(f"Creating new conversation: account_id={account_id}, contact_id={contact_id}, phone={normalized_phone}")
        # Insérer la conversation (sans select car supabase_execute ne le supporte pas)
        await supabase_execute(
            supabase.table("conversations")
            .insert({
                "account_id": account_id,
                "contact_id": contact_id,
                "client_number": normalized_phone,
                "status": "open",
                "updated_at": timestamp_iso
            })
        )
        # Récupérer la conversation créée avec les informations du contact
        new_conversation = await supabase_execute(
            supabase.table("conversations")
            .select("*, contacts(display_name, whatsapp_number, profile_picture_url)")
            .eq("account_id", account_id)
            .eq("client_number", normalized_phone)
            .limit(1)
        )
        
        if new_conversation.data and len(new_conversation.data) > 0:
            conversation = new_conversation.data[0]
            logger.info(f"Successfully created conversation: {conversation['id']}")
            await invalidate_cache_pattern(f"conversation:{conversation['id']}")
            return conversation
        else:
            logger.error(f"Failed to create conversation: no data returned from insert")
    except HTTPException as he:
        logger.error(f"HTTPException creating conversation: {he.detail} (status: {he.status_code})")
        # Si c'est une erreur de duplication (contrainte unique), récupérer la conversation existante
        if he.status_code == 503 and "duplicate" in str(he.detail).lower():
            logger.warning("Duplicate conversation detected, retrieving existing one")
            try:
                existing_final = await supabase_execute(
                    supabase.table("conversations")
                    .select("*, contacts(display_name, whatsapp_number, profile_picture_url)")
                    .eq("account_id", account_id)
                    .eq("client_number", normalized_phone)
                    .limit(1)
                )
                if existing_final.data and len(existing_final.data) > 0:
                    conversation = existing_final.data[0]
                    logger.info(f"Retrieved existing conversation after duplicate error: {conversation['id']}")
                    await invalidate_cache_pattern(f"conversation:{conversation['id']}")
                    return conversation
            except Exception as e2:
                logger.error(f"Error retrieving existing conversation after duplicate error: {e2}", exc_info=True)
        # Re-raise HTTPException pour que l'endpoint API puisse la gérer
        raise
    except Exception as e:
        # Si erreur de duplication, récupérer la conversation existante
        error_str = str(e).lower()
        is_duplicate = "duplicate" in error_str or "unique" in error_str or "constraint" in error_str
        logger.warning(f"Error creating conversation (duplicate={is_duplicate}): {e}", exc_info=True)
        if is_duplicate:
            try:
                existing_final = await supabase_execute(
                    supabase.table("conversations")
                    .select("*, contacts(display_name, whatsapp_number, profile_picture_url)")
                    .eq("account_id", account_id)
                    .eq("client_number", normalized_phone)
                    .limit(1)
                )
                if existing_final.data and len(existing_final.data) > 0:
                    conversation = existing_final.data[0]
                    logger.info(f"Retrieved existing conversation after duplicate error: {conversation['id']}")
                    await invalidate_cache_pattern(f"conversation:{conversation['id']}")
                    return conversation
            except HTTPException:
                raise
            except Exception as e2:
                logger.error(f"Error retrieving existing conversation: {e2}", exc_info=True)
    
    logger.error(f"Failed to create or retrieve conversation for account_id={account_id}, phone={normalized_phone}")
    return None