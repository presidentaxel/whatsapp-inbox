import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from app.core.db import supabase, supabase_execute
from app.services.message_service import is_within_free_window, send_message
from app.services.conversation_service import get_conversation_by_id

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


async def queue_pin_notification(
    message_id: str,
    conversation_id: str,
    notification_text: str,
    reply_to_message_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Met en file d'attente une notification d'épinglage.
    La notification sera envoyée automatiquement quand la fenêtre gratuite reviendra.
    """
    result = await supabase_execute(
        supabase.table("pinned_message_notifications")
        .insert({
            "message_id": message_id,
            "conversation_id": conversation_id,
            "notification_text": notification_text,
            "reply_to_message_id": reply_to_message_id,
            "status": "pending"
        })
    )
    
    if result.data:
        logger.info(f"📌 [PIN QUEUE] Notification mise en file d'attente: message_id={message_id}, conversation_id={conversation_id}")
        return {"status": "queued", "notification_id": result.data[0]["id"]}
    else:
        logger.error(f"❌ [PIN QUEUE] Erreur lors de la mise en file d'attente: {result}")
        return {"status": "error", "error": "Failed to queue notification"}


async def send_pending_pin_notifications():
    """
    Vérifie et envoie les notifications d'épinglage en attente
    pour les conversations qui sont maintenant dans la fenêtre gratuite.
    """
    # Récupérer toutes les notifications en attente
    result = await supabase_execute(
        supabase.table("pinned_message_notifications")
        .select("*")
        .eq("status", "pending")
        .order("created_at", desc=False)  # Plus anciennes en premier
    )
    
    if not result.data:
        return
    
    logger.info(f"📌 [PIN QUEUE] Vérification de {len(result.data)} notification(s) en attente")
    
    for notification in result.data:
        conversation_id = notification["conversation_id"]
        notification_id = notification["id"]
        
        try:
            # Vérifier si on est maintenant dans la fenêtre gratuite
            is_free, _ = await is_within_free_window(conversation_id)
            
            if is_free:
                # Envoyer la notification
                conversation = await get_conversation_by_id(conversation_id)
                if not conversation:
                    logger.warning(f"⚠️ [PIN QUEUE] Conversation {conversation_id} non trouvée")
                    await _mark_notification_failed(notification_id, "Conversation not found")
                    continue
                
                message_payload = {
                    "conversation_id": conversation_id,
                    "content": notification["notification_text"]
                }
                
                if notification.get("reply_to_message_id"):
                    message_payload["reply_to_message_id"] = notification["reply_to_message_id"]
                
                # Envoyer le message
                send_result = await send_message(
                    message_payload,
                    skip_bot_trigger=True,
                    force_send=False,  # On est dans la fenêtre gratuite, pas besoin de forcer
                    is_system=True  # Message système, ne pas afficher dans l'interface
                )
                
                if send_result.get("error"):
                    error_msg = send_result.get("error", "Unknown error")
                    logger.error(f"❌ [PIN QUEUE] Erreur lors de l'envoi: {error_msg}")
                    await _mark_notification_failed(notification_id, error_msg)
                else:
                    # Marquer comme envoyé
                    await supabase_execute(
                        supabase.table("pinned_message_notifications")
                        .update({
                            "status": "sent",
                            "sent_at": datetime.now(timezone.utc).isoformat()
                        })
                        .eq("id", notification_id)
                    )
                    logger.info(f"✅ [PIN QUEUE] Notification envoyée avec succès: notification_id={notification_id}")
            else:
                # Pas encore dans la fenêtre gratuite, on attend
                logger.debug(f"⏳ [PIN QUEUE] Conversation {conversation_id} pas encore dans la fenêtre gratuite")
                
        except Exception as e:
            logger.error(f"❌ [PIN QUEUE] Erreur lors du traitement de la notification {notification_id}: {e}", exc_info=True)
            await _mark_notification_failed(notification_id, str(e))


async def _mark_notification_failed(notification_id: str, error_message: str):
    """Marque une notification comme échouée."""
    # Récupérer le retry_count actuel
    result = await supabase_execute(
        supabase.table("pinned_message_notifications")
        .select("retry_count")
        .eq("id", notification_id)
        .single()
    )
    
    current_retry_count = 0
    if result.data:
        current_retry_count = result.data.get("retry_count", 0)
    
    await supabase_execute(
        supabase.table("pinned_message_notifications")
        .update({
            "status": "failed",
            "error_message": error_message,
            "retry_count": current_retry_count + 1,
            "last_retry_at": datetime.now(timezone.utc).isoformat()
        })
        .eq("id", notification_id)
    )


async def periodic_pin_notification_check():
    """
    Tâche périodique qui vérifie et envoie les notifications d'épinglage en attente.
    Tourne toutes les 5 minutes.
    """
    CHECK_INTERVAL_SECONDS = 300  # 5 minutes
    
    logger.info(f"🔄 [PIN QUEUE] Starting periodic pin notification check task (interval: {CHECK_INTERVAL_SECONDS}s)")
    
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            await send_pending_pin_notifications()
        except asyncio.CancelledError:
            logger.info("🛑 [PIN QUEUE] Periodic task cancelled")
            break
        except Exception as e:
            logger.error(f"❌ [PIN QUEUE] Error in periodic task: {e}", exc_info=True)
            # Continuer même en cas d'erreur
            await asyncio.sleep(60)  # Attendre 1 minute avant de réessayer

