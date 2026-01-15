import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.db import supabase, supabase_execute
from app.services.account_service import get_account_by_id
from app.services.conversation_service import find_or_create_conversation as _find_or_create_conversation
from app.services.message_service import (
    send_message,
    is_within_free_window,
)
from app.services.pending_template_service import create_and_queue_template

logger = logging.getLogger(__name__)


# ==================== GROUPES ====================

async def create_broadcast_group(
    account_id: str,
    name: str,
    description: Optional[str] = None,
    created_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Crée un nouveau groupe de diffusion"""
    result = await supabase_execute(
        supabase.table("broadcast_groups")
        .insert({
            "account_id": account_id,
            "name": name,
            "description": description,
            "created_by": created_by,
        })
    )
    
    if not result.data or len(result.data) == 0:
        raise ValueError("Failed to create broadcast group")
    
    return result.data[0]


async def get_broadcast_group(group_id: str) -> Optional[Dict[str, Any]]:
    """Récupère un groupe par son ID"""
    result = await supabase_execute(
        supabase.table("broadcast_groups")
        .select("*")
        .eq("id", group_id)
        .single()
    )
    return result.data if result.data else None


async def get_broadcast_groups(account_id: str) -> List[Dict[str, Any]]:
    """Récupère tous les groupes d'un compte"""
    result = await supabase_execute(
        supabase.table("broadcast_groups")
        .select("*")
        .eq("account_id", account_id)
        .order("created_at", desc=True)
    )
    return result.data or []


async def update_broadcast_group(
    group_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Met à jour un groupe"""
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if name is not None:
        update_data["name"] = name
    if description is not None:
        update_data["description"] = description
    
    await supabase_execute(
        supabase.table("broadcast_groups")
        .update(update_data)
        .eq("id", group_id)
    )
    
    # Récupérer le groupe mis à jour
    updated = await supabase_execute(
        supabase.table("broadcast_groups")
        .select("*")
        .eq("id", group_id)
        .single()
    )
    
    return updated.data if updated.data else None


async def delete_broadcast_group(group_id: str) -> bool:
    """Supprime un groupe (cascade sur recipients et campaigns)"""
    result = await supabase_execute(
        supabase.table("broadcast_groups")
        .delete()
        .eq("id", group_id)
    )
    return True


# ==================== DESTINATAIRES ====================

async def add_recipient_to_group(
    group_id: str,
    phone_number: str,
    contact_id: Optional[str] = None,
    display_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Ajoute un destinataire à un groupe"""
    result = await supabase_execute(
        supabase.table("broadcast_group_recipients")
        .insert({
            "group_id": group_id,
            "contact_id": contact_id,
            "phone_number": phone_number,
            "display_name": display_name,
        })
    )
    
    if not result.data or len(result.data) == 0:
        raise ValueError("Failed to add recipient to group")
    
    return result.data[0]


async def get_group_recipients(group_id: str) -> List[Dict[str, Any]]:
    """Récupère tous les destinataires d'un groupe"""
    result = await supabase_execute(
        supabase.table("broadcast_group_recipients")
        .select("*, contacts(display_name, whatsapp_number, profile_picture_url)")
        .eq("group_id", group_id)
        .order("created_at", desc=False)
    )
    return result.data or []


async def remove_recipient_from_group(recipient_id: str) -> bool:
    """Retire un destinataire d'un groupe"""
    await supabase_execute(
        supabase.table("broadcast_group_recipients")
        .delete()
        .eq("id", recipient_id)
    )
    return True


# ==================== CAMPAGNES ====================

async def create_broadcast_campaign(
    group_id: str,
    account_id: str,
    content_text: str,
    message_type: str = "text",
    media_url: Optional[str] = None,
    sent_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Crée une nouvelle campagne d'envoi groupé"""
    # Compter les destinataires
    recipients = await get_group_recipients(group_id)
    total_recipients = len(recipients)
    
    result = await supabase_execute(
        supabase.table("broadcast_campaigns")
        .insert({
            "group_id": group_id,
            "account_id": account_id,
            "content_text": content_text,
            "message_type": message_type,
            "media_url": media_url,
            "sent_by": sent_by,
            "total_recipients": total_recipients,
        })
    )
    
    if not result.data or len(result.data) == 0:
        raise ValueError("Failed to create broadcast campaign")
    
    return result.data[0]


async def get_broadcast_campaign(campaign_id: str) -> Optional[Dict[str, Any]]:
    """Récupère une campagne par son ID"""
    result = await supabase_execute(
        supabase.table("broadcast_campaigns")
        .select("*")
        .eq("id", campaign_id)
        .single()
    )
    return result.data if result.data else None


async def get_broadcast_campaigns(group_id: Optional[str] = None, account_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Récupère les campagnes (optionnellement filtrées par groupe ou compte)"""
    query = supabase.table("broadcast_campaigns").select("*")
    
    if group_id:
        query = query.eq("group_id", group_id)
    if account_id:
        query = query.eq("account_id", account_id)
    
    query = query.order("sent_at", desc=True)
    
    result = await supabase_execute(query)
    return result.data or []


async def send_broadcast_campaign(
    group_id: str,
    account_id: str,
    content_text: str,
    message_type: str = "text",
    media_url: Optional[str] = None,
    sent_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Envoie un message à tous les destinataires d'un groupe et crée une campagne de suivi
    """
    # 1. Créer la campagne
    campaign = await create_broadcast_campaign(
        group_id=group_id,
        account_id=account_id,
        content_text=content_text,
        message_type=message_type,
        media_url=media_url,
        sent_by=sent_by,
    )
    
    # 2. Récupérer tous les destinataires
    recipients = await get_group_recipients(group_id)
    
    if not recipients:
        logger.warning(f"No recipients in group {group_id}")
        return campaign
    
    # 3. Vérifier si on est hors fenêtre (vérifier une conversation représentative)
    account = await get_account_by_id(account_id)
    if not account:
        raise ValueError("Account not found")
    
    # Vérifier si on doit utiliser un template (hors fenêtre)
    use_template = False
    if recipients:
        first_recipient = recipients[0]
        first_conversation = await _find_or_create_conversation(account_id, first_recipient["phone_number"])
        if first_conversation:
            is_free, _ = await is_within_free_window(first_conversation["id"])
            if not is_free:
                use_template = True
                logger.info(f"📧 Broadcast campaign outside 24h window, will create template for: '{content_text[:50]}...'")
            else:
                logger.info("✅ Broadcast campaign within 24h window, sending as free messages")
    
    # 4. Si hors fenêtre, créer un template et des messages "fake" pour tous
    if use_template:
        # Créer un message "fake" principal pour la campagne (utilisé pour le template)
        # On utilise la première conversation comme référence
        first_conversation = await _find_or_create_conversation(account_id, recipients[0]["phone_number"])
        if not first_conversation:
            raise ValueError("Failed to create reference conversation")
        
        timestamp_iso = datetime.now(timezone.utc).isoformat()
        fake_message_payload = {
            "conversation_id": first_conversation["id"],
            "direction": "outbound",
            "content_text": content_text,
            "timestamp": timestamp_iso,
            "message_type": "text",
            "status": "sent",  # Message "fake" marqué comme envoyé
        }
        
        fake_message_result = await supabase_execute(
            supabase.table("messages").insert(fake_message_payload)
        )
        
        if not fake_message_result.data:
            raise ValueError("Failed to create fake message for template")
        
        fake_message_id = fake_message_result.data[0]["id"]
        
        # Créer le template pour la campagne (un seul template pour tous)
        template_result = await create_and_queue_template(
            conversation_id=first_conversation["id"],
            account_id=account_id,
            message_id=fake_message_id,
            text_content=content_text,
            campaign_id=campaign["id"]
        )
        
        if not template_result.get("success"):
            error_message = "; ".join(template_result.get("errors", ["Erreur inconnue"]))
            logger.error(f"❌ Failed to create template for broadcast: {error_message}")
            # Marquer la campagne comme échouée
            await supabase_execute(
                supabase.table("broadcast_campaigns")
                .update({"failed_count": len(recipients)})
                .eq("id", campaign["id"])
            )
            raise ValueError(f"Template creation failed: {error_message}")
        
        # Lier le template à la campagne (déjà fait dans create_and_queue_template si campaign_id est passé)
        # Mais on doit le mettre à jour car create_and_queue_template ne prend pas encore campaign_id
        await supabase_execute(
            supabase.table("pending_template_messages")
            .update({"campaign_id": campaign["id"]})
            .eq("message_id", fake_message_id)
        )
        
        logger.info(f"✅ Template '{template_result.get('template_name')}' created and queued for campaign {campaign['id']}")
        
        # Créer des messages "fake" pour tous les destinataires
        for recipient in recipients:
            phone_number = recipient["phone_number"]
            conversation = await _find_or_create_conversation(account_id, phone_number)
            if not conversation:
                logger.error(f"Failed to find/create conversation for {phone_number}")
                failed_count += 1
                continue
            
            # Créer un message "fake" pour ce destinataire
            recipient_fake_message = {
                "conversation_id": conversation["id"],
                "direction": "outbound",
                "content_text": content_text,
                "timestamp": timestamp_iso,
                "message_type": "text",
                "status": "sent",  # Message "fake" marqué comme envoyé
            }
            
            recipient_message_result = await supabase_execute(
                supabase.table("messages").insert(recipient_fake_message)
            )
            
            message_db_id = None
            if recipient_message_result.data:
                message_db_id = recipient_message_result.data[0]["id"]
            
            # Créer la stat pour ce destinataire
            await create_recipient_stat(
                campaign_id=campaign["id"],
                recipient_id=recipient["id"],
                phone_number=phone_number,
                message_id=message_db_id,
            )
            sent_count += 1
        
        # Mettre à jour les compteurs
        await update_campaign_counters(campaign["id"])
        return campaign
    
    # 5. Si dans la fenêtre, envoyer normalement à tous
    sent_count = 0
    failed_count = 0
    
    for recipient in recipients:
        try:
            phone_number = recipient["phone_number"]
            
            # Trouver ou créer la conversation
            conversation = await _find_or_create_conversation(account_id, phone_number)
            if not conversation:
                logger.error(f"Failed to find/create conversation for {phone_number}")
                failed_count += 1
                continue
            
            # Envoyer le message normalement
            message_result = await send_message({
                "conversation_id": conversation["id"],
                "content": content_text,
            }, force_send=True)
            
            if message_result.get("error"):
                logger.error(f"Failed to send message to {phone_number}: {message_result.get('error')}")
                failed_count += 1
                # Créer quand même la stat avec failed_at
                await create_recipient_stat(
                    campaign_id=campaign["id"],
                    recipient_id=recipient["id"],
                    phone_number=phone_number,
                    message_id=None,
                    failed_at=datetime.now(timezone.utc).isoformat(),
                    error_message=message_result.get("message", "Unknown error"),
                )
            else:
                # Récupérer l'UUID du message depuis la base (le message est inséré en arrière-plan)
                import asyncio
                await asyncio.sleep(0.5)  # Attendre 500ms pour l'insertion asynchrone
                
                wa_message_id = message_result.get("message_id")
                message_db = None
                if wa_message_id:
                    # Chercher le message en base par wa_message_id
                    message_db_result = await supabase_execute(
                        supabase.table("messages")
                        .select("id")
                        .eq("wa_message_id", wa_message_id)
                        .single()
                    )
                    if message_db_result.data:
                        message_db = message_db_result.data["id"]
                
                # Créer l'entrée de stats
                await create_recipient_stat(
                    campaign_id=campaign["id"],
                    recipient_id=recipient["id"],
                    phone_number=phone_number,
                    message_id=message_db,
                )
                sent_count += 1
                
        except Exception as e:
            logger.error(f"Error sending to recipient {recipient.get('phone_number')}: {e}", exc_info=True)
            failed_count += 1
    
    # Mettre à jour les compteurs de la campagne
    await update_campaign_counters(campaign["id"])
    
    return campaign


# ==================== STATISTIQUES ====================

async def create_recipient_stat(
    campaign_id: str,
    recipient_id: str,
    phone_number: str,
    message_id: Optional[str] = None,
    sent_at: Optional[str] = None,
    failed_at: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Dict[str, Any]:
    """Crée une entrée de statistique pour un destinataire"""
    stat_data = {
        "campaign_id": campaign_id,
        "recipient_id": recipient_id,
        "phone_number": phone_number,
        "message_id": message_id,
    }
    
    if sent_at:
        stat_data["sent_at"] = sent_at
    elif not failed_at:
        # Si pas de sent_at ni failed_at, utiliser maintenant
        stat_data["sent_at"] = datetime.now(timezone.utc).isoformat()
    
    if failed_at:
        stat_data["failed_at"] = failed_at
        stat_data["error_message"] = error_message
    
    result = await supabase_execute(
        supabase.table("broadcast_recipient_stats")
        .insert(stat_data)
    )
    
    if not result.data or len(result.data) == 0:
        raise ValueError("Failed to create recipient stat")
    
    return result.data[0]


async def get_recipient_stat_by_message_id(message_id: str) -> Optional[Dict[str, Any]]:
    """Trouve une stat par l'ID du message"""
    result = await supabase_execute(
        supabase.table("broadcast_recipient_stats")
        .select("*")
        .eq("message_id", message_id)
        .single()
    )
    return result.data if result.data else None


async def update_recipient_stat(
    stat_id: str,
    update_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Met à jour une stat"""
    # Calculer time_to_read si read_at est défini
    if "read_at" in update_data and update_data["read_at"]:
        # Récupérer sent_at pour calculer le délai
        stat = await supabase_execute(
            supabase.table("broadcast_recipient_stats")
            .select("sent_at")
            .eq("id", stat_id)
            .single()
        )
        if stat.data and stat.data.get("sent_at"):
            from datetime import datetime as dt
            sent_time = dt.fromisoformat(stat.data["sent_at"].replace('Z', '+00:00'))
            read_time = dt.fromisoformat(update_data["read_at"].replace('Z', '+00:00'))
            update_data["time_to_read"] = str(read_time - sent_time)
    
    # Calculer time_to_reply si replied_at est défini
    if "replied_at" in update_data and update_data["replied_at"]:
        stat = await supabase_execute(
            supabase.table("broadcast_recipient_stats")
            .select("sent_at")
            .eq("id", stat_id)
            .single()
        )
        if stat.data and stat.data.get("sent_at"):
            from datetime import datetime as dt
            sent_time = dt.fromisoformat(stat.data["sent_at"].replace('Z', '+00:00'))
            reply_time = dt.fromisoformat(update_data["replied_at"].replace('Z', '+00:00'))
            update_data["time_to_reply"] = str(reply_time - sent_time)
    
    result = await supabase_execute(
        supabase.table("broadcast_recipient_stats")
        .update(update_data)
        .eq("id", stat_id)
        .select()
    )
    
    return result.data[0] if result.data else None


async def update_recipient_stat_from_webhook(
    wa_message_id: str,
    status: str,
    timestamp: str,
    error_message: Optional[str] = None,
) -> bool:
    """
    Met à jour les stats quand on reçoit un webhook de statut WhatsApp
    """
    # Trouver le message par wa_message_id
    message_result = await supabase_execute(
        supabase.table("messages")
        .select("id")
        .eq("wa_message_id", wa_message_id)
        .single()
    )
    
    if not message_result.data:
        logger.debug(f"No message found with wa_message_id: {wa_message_id}")
        return False
    
    message_id = message_result.data["id"]
    
    # Trouver la stat associée
    stat_result = await supabase_execute(
        supabase.table("broadcast_recipient_stats")
        .select("id, campaign_id")
        .eq("message_id", message_id)
        .single()
    )
    
    if not stat_result.data:
        return False
    
    # Gérer le cas où plusieurs stats pourraient correspondre (ne devrait pas arriver)
    stat_data = stat_result.data[0] if isinstance(stat_result.data, list) else stat_result.data
    stat_id = stat_data["id"]
    
    # Mettre à jour selon le statut
    update_data = {}
    if status == "sent":
        update_data["sent_at"] = timestamp
    elif status == "delivered":
        update_data["delivered_at"] = timestamp
    elif status == "read":
        update_data["read_at"] = timestamp
    elif status == "failed":
        update_data["failed_at"] = timestamp
        if error_message:
            update_data["error_message"] = error_message
    
    if update_data:
        await update_recipient_stat(stat_id, update_data)
        # Mettre à jour les compteurs de la campagne
        campaign_id = stat_data.get("campaign_id")
        if campaign_id:
            await update_campaign_counters(campaign_id)
    
    return True


async def track_reply(conversation_id: str, message_id: str) -> bool:
    """
    Marque qu'un destinataire a répondu à une campagne
    """
    # Trouver la conversation pour obtenir le numéro
    conv_result = await supabase_execute(
        supabase.table("conversations")
        .select("client_number, account_id")
        .eq("id", conversation_id)
        .single()
    )
    
    if not conv_result.data:
        return False
    
    phone_number = conv_result.data["client_number"]
    
    # Trouver la campagne active la plus récente pour ce numéro
    # (on prend la dernière campagne où le message a été envoyé mais pas encore répondu)
    stats_result = await supabase_execute(
        supabase.table("broadcast_recipient_stats")
        .select("id, campaign_id, sent_at")
        .eq("phone_number", phone_number)
        .is_("replied_at", "null")
        .not_.is_("sent_at", "null")
        .order("sent_at", desc=True)
        .limit(1)
    )
    
    if not stats_result.data or len(stats_result.data) == 0:
        return False
    
    stat = stats_result.data[0]
    
    # Mettre à jour la stat
    await update_recipient_stat(stat["id"], {
        "replied_at": datetime.now(timezone.utc).isoformat(),
        "reply_message_id": message_id,
    })
    
    # Mettre à jour le compteur de la campagne
    await update_campaign_counters(stat["campaign_id"])
    
    return True


async def update_campaign_counters(campaign_id: str) -> bool:
    """Met à jour les compteurs agrégés d'une campagne"""
    # Compter les stats
    stats_result = await supabase_execute(
        supabase.table("broadcast_recipient_stats")
        .select("sent_at, delivered_at, read_at, replied_at, failed_at")
        .eq("campaign_id", campaign_id)
    )
    
    if not stats_result.data:
        return False
    
    stats = stats_result.data
    
    sent_count = sum(1 for s in stats if s.get("sent_at"))
    delivered_count = sum(1 for s in stats if s.get("delivered_at"))
    read_count = sum(1 for s in stats if s.get("read_at"))
    replied_count = sum(1 for s in stats if s.get("replied_at"))
    failed_count = sum(1 for s in stats if s.get("failed_at"))
    
    # Mettre à jour la campagne
    await supabase_execute(
        supabase.table("broadcast_campaigns")
        .update({
            "sent_count": sent_count,
            "delivered_count": delivered_count,
            "read_count": read_count,
            "replied_count": replied_count,
            "failed_count": failed_count,
        })
        .eq("id", campaign_id)
    )
    
    return True


async def get_campaign_stats(campaign_id: str) -> Dict[str, Any]:
    """Récupère les statistiques complètes d'une campagne"""
    campaign = await get_broadcast_campaign(campaign_id)
    if not campaign:
        raise ValueError("Campaign not found")
    
    # Récupérer toutes les stats des destinataires
    stats_result = await supabase_execute(
        supabase.table("broadcast_recipient_stats")
        .select("*, broadcast_group_recipients(display_name, phone_number, contacts(display_name, whatsapp_number))")
        .eq("campaign_id", campaign_id)
        .order("created_at", desc=False)
    )
    
    recipients = stats_result.data or []
    
    # Calculer les taux
    total = campaign.get("total_recipients", 0)
    delivered = campaign.get("delivered_count", 0)
    read = campaign.get("read_count", 0)
    
    delivery_rate = (delivered / total * 100) if total > 0 else 0
    read_rate = (read / delivered * 100) if delivered > 0 else 0
    reply_rate = (campaign.get("replied_count", 0) / read * 100) if read > 0 else 0
    
    return {
        "campaign": campaign,
        "overview": {
            "total": total,
            "sent": campaign.get("sent_count", 0),
            "delivered": delivered,
            "read": read,
            "replied": campaign.get("replied_count", 0),
            "failed": campaign.get("failed_count", 0),
            "delivery_rate": round(delivery_rate, 2),
            "read_rate": round(read_rate, 2),
            "reply_rate": round(reply_rate, 2),
        },
        "recipients": recipients,
    }


async def get_campaign_heatmap(campaign_id: str) -> Dict[str, Any]:
    """Récupère les données pour la heat map (heures/jours)"""
    # Récupérer les stats avec read_at et replied_at
    stats_result = await supabase_execute(
        supabase.table("broadcast_recipient_stats")
        .select("read_at, replied_at")
        .eq("campaign_id", campaign_id)
    )
    
    stats = stats_result.data or []
    
    # Grouper par heure (0-23)
    read_by_hour = [0] * 24
    reply_by_hour = [0] * 24
    
    # Grouper par jour de la semaine (0=lundi, 6=dimanche)
    read_by_day = [0] * 7
    reply_by_day = [0] * 7
    
    for stat in stats:
        if stat.get("read_at"):
            from datetime import datetime as dt
            read_time = dt.fromisoformat(stat["read_at"].replace('Z', '+00:00'))
            hour = read_time.hour
            day = read_time.weekday()  # 0=lundi, 6=dimanche
            read_by_hour[hour] += 1
            read_by_day[day] += 1
        
        if stat.get("replied_at"):
            from datetime import datetime as dt
            reply_time = dt.fromisoformat(stat["replied_at"].replace('Z', '+00:00'))
            hour = reply_time.hour
            day = reply_time.weekday()
            reply_by_hour[hour] += 1
            reply_by_day[day] += 1
    
    # Formater pour le frontend
    read_by_hour_formatted = [{"hour": h, "count": read_by_hour[h]} for h in range(24)]
    reply_by_hour_formatted = [{"hour": h, "count": reply_by_hour[h]} for h in range(24)]
    
    day_names = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    read_by_day_formatted = [{"day": day_names[d], "count": read_by_day[d]} for d in range(7)]
    reply_by_day_formatted = [{"day": day_names[d], "count": reply_by_day[d]} for d in range(7)]
    
    return {
        "read_by_hour": read_by_hour_formatted,
        "reply_by_hour": reply_by_hour_formatted,
        "read_by_day": read_by_day_formatted,
        "reply_by_day": reply_by_day_formatted,
    }


async def get_campaign_timeline(campaign_id: str) -> List[Dict[str, Any]]:
    """Récupère la timeline pour les courbes temporelles"""
    campaign = await get_broadcast_campaign(campaign_id)
    if not campaign:
        return []
    
    sent_at = campaign.get("sent_at")
    if not sent_at:
        return []
    
    from datetime import datetime as dt
    start_time = dt.fromisoformat(sent_at.replace('Z', '+00:00'))
    
    # Récupérer toutes les stats avec timestamps
    stats_result = await supabase_execute(
        supabase.table("broadcast_recipient_stats")
        .select("read_at, replied_at")
        .eq("campaign_id", campaign_id)
        .order("read_at", desc=False)
    )
    
    stats = stats_result.data or []
    
    # Créer des points de timeline (cumulatif)
    timeline = []
    read_count = 0
    reply_count = 0
    
    # Grouper par heure
    from collections import defaultdict
    reads_by_hour = defaultdict(int)
    replies_by_hour = defaultdict(int)
    
    for stat in stats:
        if stat.get("read_at"):
            read_time = dt.fromisoformat(stat["read_at"].replace('Z', '+00:00'))
            hour_key = read_time.strftime("%Y-%m-%d %H:00:00")
            reads_by_hour[hour_key] += 1
        
        if stat.get("replied_at"):
            reply_time = dt.fromisoformat(stat["replied_at"].replace('Z', '+00:00'))
            hour_key = reply_time.strftime("%Y-%m-%d %H:00:00")
            replies_by_hour[hour_key] += 1
    
    # Créer la timeline
    all_hours = sorted(set(list(reads_by_hour.keys()) + list(replies_by_hour.keys())))
    
    cumulative_reads = 0
    cumulative_replies = 0
    
    for hour in all_hours:
        cumulative_reads += reads_by_hour.get(hour, 0)
        cumulative_replies += replies_by_hour.get(hour, 0)
        
        timeline.append({
            "timestamp": hour,
            "reads": cumulative_reads,
            "replies": cumulative_replies,
        })
    
    return timeline

