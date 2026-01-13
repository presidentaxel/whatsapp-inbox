"""
Service de tâche en arrière-plan pour télécharger automatiquement les médias manquants.
Vérifie périodiquement les messages avec média qui n'ont pas de storage_url et les télécharge.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from app.core.db import supabase, supabase_execute
from app.services.account_service import get_account_by_id
from app.services.message_service import _download_and_store_media_async
from app.services.conversation_service import get_conversation_by_id

logger = logging.getLogger(__name__)

# Intervalle entre chaque vérification (en secondes)
# Par défaut: toutes les 5 minutes
CHECK_INTERVAL_SECONDS = 300  # 5 minutes

# Nombre maximum de messages à traiter par cycle
MAX_MESSAGES_PER_CYCLE = 10

# Ne pas essayer de télécharger les médias trop anciens (plus de 7 jours)
# Car WhatsApp peut avoir expiré les URLs
MAX_AGE_DAYS = 7


async def process_unsaved_media_for_conversation(conversation_id: str, limit: int = 50) -> Dict[str, int]:
    """
    Trouve et télécharge les médias manquants pour une conversation spécifique.
    
    Args:
        conversation_id: ID de la conversation
        limit: Nombre maximum de messages à traiter
    
    Returns:
        Dict avec les statistiques: {'processed': X, 'success': Y, 'errors': Z, 'skipped': W}
    """
    stats = {
        'processed': 0,
        'success': 0,
        'errors': 0,
        'skipped': 0,
        'expired': 0
    }
    
    try:
        # Calculer la date limite (ne pas traiter les médias trop anciens)
        max_age_date = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
        max_age_iso = max_age_date.isoformat()
        
        # Trouver les messages avec média mais sans storage_url pour cette conversation
        query = (
            supabase.table("messages")
            .select("id, message_type, media_id, conversation_id, media_mime_type, media_filename, timestamp")
            .eq("conversation_id", conversation_id)
            .in_("message_type", ["image", "video", "audio", "document", "sticker"])
            .is_("storage_url", "null")
            .not_.is_("media_id", "null")
            .gte("timestamp", max_age_iso)  # Seulement les messages récents
            .order("timestamp", desc=True)  # Traiter les plus récents en premier
            .limit(limit)
        )
        
        result = await supabase_execute(query)
        messages = result.data or []
        
        if not messages:
            logger.debug(f"ℹ️ [MEDIA BACKGROUND] No unsaved media messages found for conversation {conversation_id}")
            return stats
        
        logger.info(f"📋 [MEDIA BACKGROUND] Found {len(messages)} unsaved media messages for conversation {conversation_id}, processing...")
        
        # Récupérer la conversation pour obtenir l'account_id
        conversation = await get_conversation_by_id(conversation_id)
        if not conversation:
            logger.warning(f"❌ [MEDIA BACKGROUND] Conversation not found: {conversation_id}")
            return stats
        
        account_id = conversation.get("account_id")
        if not account_id:
            logger.warning(f"❌ [MEDIA BACKGROUND] No account_id in conversation")
            return stats
        
        # Récupérer l'account une seule fois
        account = await get_account_by_id(account_id)
        if not account:
            logger.warning(f"❌ [MEDIA BACKGROUND] Account not found: {account_id}")
            return stats
        
        for msg in messages:
            stats['processed'] += 1
            msg_id = msg.get("id")
            media_id = msg.get("media_id")
            msg_type = msg.get("message_type")
            timestamp = msg.get("timestamp")
            
            try:
                # Vérifier si le message est trop ancien
                if timestamp:
                    msg_date = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    age = datetime.now(timezone.utc) - msg_date.replace(tzinfo=timezone.utc)
                    if age.days > MAX_AGE_DAYS:
                        logger.debug(f"⏭️ [MEDIA BACKGROUND] Skipping message {msg_id[:8]}... (too old: {age.days} days)")
                        stats['skipped'] += 1
                        continue
                
                logger.info(f"📥 [MEDIA BACKGROUND] Processing message {msg_id[:8]}... (type: {msg_type}, media_id: {media_id[:20] if media_id else 'N/A'}...)")
                
                # Télécharger et stocker le média
                await _download_and_store_media_async(
                    message_db_id=msg_id,
                    media_id=media_id,
                    account=account,
                    mime_type=msg.get("media_mime_type"),
                    filename=msg.get("media_filename")
                )
                
                # Attendre un peu pour que le stockage se termine
                await asyncio.sleep(1)
                
                # Vérifier que storage_url a été mis à jour
                check_result = await supabase_execute(
                    supabase.table("messages")
                    .select("storage_url")
                    .eq("id", msg_id)
                    .limit(1)
                )
                
                if check_result.data and check_result.data[0].get("storage_url"):
                    storage_url = check_result.data[0].get("storage_url")
                    logger.info(f"✅ [MEDIA BACKGROUND] Media saved for message {msg_id[:8]}...: {storage_url[:60]}...")
                    stats['success'] += 1
                else:
                    # Attendre un peu plus et réessayer
                    await asyncio.sleep(2)
                    check_result = await supabase_execute(
                        supabase.table("messages")
                        .select("storage_url")
                        .eq("id", msg_id)
                        .limit(1)
                    )
                    if check_result.data and check_result.data[0].get("storage_url"):
                        logger.info(f"✅ [MEDIA BACKGROUND] Media saved after wait for message {msg_id[:8]}...")
                        stats['success'] += 1
                    else:
                        logger.warning(f"⚠️ [MEDIA BACKGROUND] Media not saved for message {msg_id[:8]}... (may be expired or download failed)")
                        stats['errors'] += 1
                
            except Exception as e:
                logger.error(f"❌ [MEDIA BACKGROUND] Error processing message {msg_id[:8]}...: {e}", exc_info=True)
                stats['errors'] += 1
            
            # Petite pause entre chaque message pour ne pas surcharger
            await asyncio.sleep(0.5)
        
        logger.info(
            f"✅ [MEDIA BACKGROUND] Conversation {conversation_id} completed: "
            f"processed={stats['processed']}, "
            f"success={stats['success']}, "
            f"errors={stats['errors']}, "
            f"skipped={stats['skipped']}"
        )
        
        return stats
        
    except Exception as e:
        logger.error(f"❌ [MEDIA BACKGROUND] Error in process_unsaved_media_for_conversation: {e}", exc_info=True)
        return stats


async def process_unsaved_media_messages(limit: int = MAX_MESSAGES_PER_CYCLE) -> Dict[str, int]:
    """
    Trouve et télécharge les médias des messages qui n'ont pas encore de storage_url.
    
    Args:
        limit: Nombre maximum de messages à traiter dans ce cycle
    
    Returns:
        Dict avec les statistiques: {'processed': X, 'success': Y, 'errors': Z, 'skipped': W}
    """
    stats = {
        'processed': 0,
        'success': 0,
        'errors': 0,
        'skipped': 0,
        'expired': 0
    }
    
    try:
        # Calculer la date limite (ne pas traiter les médias trop anciens)
        max_age_date = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
        max_age_iso = max_age_date.isoformat()
        
        # Trouver les messages avec média mais sans storage_url
        query = (
            supabase.table("messages")
            .select("id, message_type, media_id, conversation_id, media_mime_type, media_filename, timestamp")
            .in_("message_type", ["image", "video", "audio", "document", "sticker"])
            .is_("storage_url", "null")
            .not_.is_("media_id", "null")
            .gte("timestamp", max_age_iso)  # Seulement les messages récents
            .order("timestamp", desc=True)  # Traiter les plus récents en premier
            .limit(limit)
        )
        
        result = await supabase_execute(query)
        messages = result.data or []
        
        if not messages:
            logger.debug("ℹ️ [MEDIA BACKGROUND] No unsaved media messages found")
            return stats
        
        logger.info(f"📋 [MEDIA BACKGROUND] Found {len(messages)} messages with unsaved media, processing...")
        
        for msg in messages:
            stats['processed'] += 1
            msg_id = msg.get("id")
            media_id = msg.get("media_id")
            msg_type = msg.get("message_type")
            conv_id = msg.get("conversation_id")
            timestamp = msg.get("timestamp")
            
            try:
                # Vérifier si le message est trop ancien
                if timestamp:
                    msg_date = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    age = datetime.now(timezone.utc) - msg_date.replace(tzinfo=timezone.utc)
                    if age.days > MAX_AGE_DAYS:
                        logger.debug(f"⏭️ [MEDIA BACKGROUND] Skipping message {msg_id[:8]}... (too old: {age.days} days)")
                        stats['skipped'] += 1
                        continue
                
                logger.info(f"📥 [MEDIA BACKGROUND] Processing message {msg_id[:8]}... (type: {msg_type}, media_id: {media_id[:20] if media_id else 'N/A'}...)")
                
                # Récupérer la conversation pour obtenir l'account_id
                conversation = await get_conversation_by_id(conv_id)
                if not conversation:
                    logger.warning(f"❌ [MEDIA BACKGROUND] Conversation not found: {conv_id}")
                    stats['errors'] += 1
                    continue
                
                account_id = conversation.get("account_id")
                if not account_id:
                    logger.warning(f"❌ [MEDIA BACKGROUND] No account_id in conversation")
                    stats['errors'] += 1
                    continue
                
                # Récupérer l'account
                account = await get_account_by_id(account_id)
                if not account:
                    logger.warning(f"❌ [MEDIA BACKGROUND] Account not found: {account_id}")
                    stats['errors'] += 1
                    continue
                
                # Télécharger et stocker le média
                await _download_and_store_media_async(
                    message_db_id=msg_id,
                    media_id=media_id,
                    account=account,
                    mime_type=msg.get("media_mime_type"),
                    filename=msg.get("media_filename")
                )
                
                # Attendre un peu pour que le stockage se termine
                await asyncio.sleep(1)
                
                # Vérifier que storage_url a été mis à jour
                check_result = await supabase_execute(
                    supabase.table("messages")
                    .select("storage_url")
                    .eq("id", msg_id)
                    .limit(1)
                )
                
                if check_result.data and check_result.data[0].get("storage_url"):
                    storage_url = check_result.data[0].get("storage_url")
                    logger.info(f"✅ [MEDIA BACKGROUND] Media saved for message {msg_id[:8]}...: {storage_url[:60]}...")
                    stats['success'] += 1
                else:
                    # Attendre un peu plus et réessayer
                    await asyncio.sleep(2)
                    check_result = await supabase_execute(
                        supabase.table("messages")
                        .select("storage_url")
                        .eq("id", msg_id)
                        .limit(1)
                    )
                    if check_result.data and check_result.data[0].get("storage_url"):
                        logger.info(f"✅ [MEDIA BACKGROUND] Media saved after wait for message {msg_id[:8]}...")
                        stats['success'] += 1
                    else:
                        logger.warning(f"⚠️ [MEDIA BACKGROUND] Media not saved for message {msg_id[:8]}... (may be expired or download failed)")
                        stats['errors'] += 1
                
            except Exception as e:
                logger.error(f"❌ [MEDIA BACKGROUND] Error processing message {msg_id[:8]}...: {e}", exc_info=True)
                stats['errors'] += 1
            
            # Petite pause entre chaque message pour ne pas surcharger
            await asyncio.sleep(0.5)
        
        logger.info(
            f"✅ [MEDIA BACKGROUND] Cycle completed: "
            f"processed={stats['processed']}, "
            f"success={stats['success']}, "
            f"errors={stats['errors']}, "
            f"skipped={stats['skipped']}"
        )
        
        return stats
        
    except Exception as e:
        logger.error(f"❌ [MEDIA BACKGROUND] Error in process_unsaved_media_messages: {e}", exc_info=True)
        return stats


async def periodic_media_backfill():
    """
    Tâche périodique qui vérifie et télécharge les médias manquants.
    Tourne en boucle infinie avec un intervalle configuré.
    """
    logger.info(f"🚀 [MEDIA BACKGROUND] Starting periodic media backfill task (interval: {CHECK_INTERVAL_SECONDS}s)")
    
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            logger.debug(f"🔄 [MEDIA BACKGROUND] Starting new check cycle...")
            await process_unsaved_media_messages(limit=MAX_MESSAGES_PER_CYCLE)
        except asyncio.CancelledError:
            logger.info("🛑 [MEDIA BACKGROUND] Periodic task cancelled")
            break
        except Exception as e:
            logger.error(f"❌ [MEDIA BACKGROUND] Error in periodic task: {e}", exc_info=True)
            # Attendre un peu avant de réessayer en cas d'erreur
            await asyncio.sleep(60)  # 1 minute avant de réessayer

