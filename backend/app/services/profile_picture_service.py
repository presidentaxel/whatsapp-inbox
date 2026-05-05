"""
Service pour mettre à jour automatiquement les images de profil des contacts
de manière asynchrone sans bloquer les appels API
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Set
from collections import deque

from app.core.db import supabase, supabase_execute
from app.services.account_service import get_account_by_id, get_all_accounts
from app.services import whatsapp_api_service
from app.services.storage_service import download_and_store_profile_picture

logger = logging.getLogger(__name__)

# Queue globale pour les mises à jour de profil
_profile_update_queue: deque = deque()
_processing_queue = False
_processed_contacts: Set[str] = set()  # Cache pour éviter les doublons récents
_last_update_time: Dict[str, datetime] = {}  # Cache par contact


async def queue_profile_picture_update(
    contact_id: str,
    whatsapp_number: str,
    account_id: str,
    priority: bool = False
):
    """
    Ajoute une mise à jour d'image de profil à la queue
    
    Args:
        contact_id: ID du contact
        whatsapp_number: Numéro WhatsApp du contact
        account_id: ID du compte WhatsApp à utiliser
        priority: Si True, traite en priorité (pour les nouveaux messages)
    """
    # Vérifier si on a déjà traité ce contact récemment (cache de 1h)
    cache_key = f"{contact_id}_{whatsapp_number}"
    now = datetime.now(timezone.utc)
    
    if cache_key in _last_update_time:
        time_diff = (now - _last_update_time[cache_key]).total_seconds()
        if time_diff < 3600:  # 1 heure
            logger.debug(f"Skipping {whatsapp_number} - recently updated")
            return
    
    # Vérifier si le contact a déjà une image
    try:
        contact_res = await supabase_execute(
            supabase.table("contacts")
            .select("profile_picture_url")
            .eq("id", contact_id)
            .limit(1)
        )
        
        if contact_res.data and contact_res.data[0].get("profile_picture_url"):
            # Déjà une image, pas besoin de mettre à jour
            _last_update_time[cache_key] = now
            logger.debug(f"Contact {whatsapp_number} already has profile picture")
            return
    except Exception as e:
        # Si erreur de base de données, continuer quand même (peut-être que le champ n'existe pas encore)
        logger.warning(f"Error checking existing profile picture for {whatsapp_number}: {e}")
        # Continuer pour essayer de mettre à jour
    
    # Ajouter à la queue
    task = {
        "contact_id": contact_id,
        "whatsapp_number": whatsapp_number,
        "account_id": account_id,
        "priority": priority,
        "queued_at": now
    }
    
    if priority:
        _profile_update_queue.appendleft(task)  # Priorité = début de queue
    else:
        _profile_update_queue.append(task)
    
    logger.info(f"📋 Queued profile picture update for {whatsapp_number} (queue size: {len(_profile_update_queue)})")
    
    # Démarrer le traitement si pas déjà en cours
    if not _processing_queue:
        logger.info("🚀 Starting profile picture update queue processor")
        asyncio.create_task(_process_profile_update_queue())


async def _process_profile_update_queue():
    """
    Traite la queue de mises à jour d'images de profil
    Traite par batch pour éviter de surcharger l'API WhatsApp
    """
    global _processing_queue
    
    if _processing_queue:
        return
    
    _processing_queue = True
    logger.info("Starting profile picture update queue processor")
    
    try:
        while _profile_update_queue:
            # Traiter par batch de 5 contacts max
            batch = []
            for _ in range(min(5, len(_profile_update_queue))):
                if _profile_update_queue:
                    batch.append(_profile_update_queue.popleft())
            
            if not batch:
                break
            
            # Traiter le batch
            await _process_batch(batch)
            
            # Attendre un peu entre les batches pour ne pas surcharger l'API
            await asyncio.sleep(2)
        
    except Exception as e:
        logger.error(f"Error processing profile update queue: {e}")
    finally:
        _processing_queue = False
        logger.info("Profile picture update queue processor stopped")


async def _process_batch(batch: list):
    """
    Traite un batch de mises à jour
    """
    tasks = []
    for task in batch:
        tasks.append(_update_single_profile_picture(task))
    
    # Traiter en parallèle mais avec un délai entre chaque
    for task in tasks:
        await task
        await asyncio.sleep(0.5)  # Petit délai entre chaque appel API


async def _update_single_profile_picture(task: dict):
    """
    Met à jour l'image de profil d'un seul contact
    """
    contact_id = task["contact_id"]
    whatsapp_number = task["whatsapp_number"]
    account_id = task["account_id"]
    
    try:
        # Récupérer le compte
        account = await get_account_by_id(account_id)
        if not account:
            logger.warning(f"Account {account_id} not found for profile update")
            return
        
        phone_number_id = account.get("phone_number_id")
        access_token = account.get("access_token")
        
        if not phone_number_id or not access_token:
            logger.warning(f"Account {account_id} not configured for profile update")
            return
        
        # Récupérer l'image de profil via Graph API
        profile_picture_url = await whatsapp_api_service.get_contact_profile_picture(
            phone_number_id=phone_number_id,
            access_token=access_token,
            phone_number=whatsapp_number
        )
        
        if profile_picture_url:
            # Télécharger et stocker l'image dans Supabase Storage
            logger.info(f"📥 Downloading profile picture from WhatsApp: {profile_picture_url}")
            # Utiliser async_upload=False pour attendre le résultat (besoin de l'URL pour la DB)
            stored_url = await download_and_store_profile_picture(
                contact_id=contact_id,
                image_url=profile_picture_url,
                async_upload=False  # Attendre le résultat pour mettre à jour la DB
            )
            
            if stored_url:
                # Utiliser l'URL Supabase au lieu de l'URL WhatsApp
                final_url = stored_url
                logger.info(f"💾 Profile picture stored in Supabase Storage: {stored_url}")
            else:
                # Si l'upload échoue, utiliser l'URL WhatsApp directement (moins idéal)
                final_url = profile_picture_url
                logger.warning("⚠️ Failed to store in Supabase Storage, using WhatsApp URL directly")
            
            # Mettre à jour le contact
            try:
                await supabase_execute(
                    supabase.table("contacts")
                    .update({"profile_picture_url": final_url})
                    .eq("id", contact_id)
                )
                
                # Mettre à jour le cache
                cache_key = f"{contact_id}_{whatsapp_number}"
                _last_update_time[cache_key] = datetime.now(timezone.utc)
                
                logger.info(f"✅ Updated profile picture for contact {contact_id} ({whatsapp_number})")
            except Exception as db_error:
                logger.error(f"Failed to update profile picture in database for {whatsapp_number}: {db_error}")
                # Peut-être que la colonne n'existe pas encore (migration non exécutée)
                if "profile_picture_url" in str(db_error).lower() or "column" in str(db_error).lower():
                    logger.warning("⚠️ Profile picture column may not exist. Please run migration 010_contacts_profile_picture.sql")
        else:
            logger.debug(f"No profile picture available for {whatsapp_number} via WhatsApp API")
            # Mettre quand même à jour le cache pour éviter de réessayer trop souvent
            cache_key = f"{contact_id}_{whatsapp_number}"
            _last_update_time[cache_key] = datetime.now(timezone.utc)
            
    except Exception as e:
        logger.error(f"Error updating profile picture for {whatsapp_number}: {e}")


async def update_all_contacts_profile_pictures(account_id: str, limit: int = 50):
    """
    Met à jour les images de profil de tous les contacts sans image
    Utile pour un job périodique ou une commande manuelle
    
    Args:
        account_id: ID du compte WhatsApp à utiliser
        limit: Nombre maximum de contacts à traiter
    """
    # Récupérer les contacts sans image de profil
    contacts_res = await supabase_execute(
        supabase.table("contacts")
        .select("id, whatsapp_number")
        .is_("profile_picture_url", "null")
        .limit(limit)
    )
    
    if not contacts_res.data:
        logger.info("No contacts without profile pictures")
        return
    
    logger.info(f"Updating profile pictures for {len(contacts_res.data)} contacts")
    
    for contact in contacts_res.data:
        await queue_profile_picture_update(
            contact_id=contact["id"],
            whatsapp_number=contact["whatsapp_number"],
            account_id=account_id,
            priority=False
        )
    
    # Démarrer le traitement
    if not _processing_queue:
        asyncio.create_task(_process_profile_update_queue())


async def refresh_old_profile_pictures(account_id: str, limit: int = 20, days_old: int = 7):
    """
    Rafraîchit les images de profil qui sont anciennes (plus de X jours)
    Utile pour mettre à jour les images qui ont pu changer
    
    Args:
        account_id: ID du compte WhatsApp à utiliser
        limit: Nombre maximum de contacts à traiter
        days_old: Nombre de jours minimum depuis la dernière mise à jour
    """
    # Récupérer les contacts avec une image
    contacts_res = await supabase_execute(
        supabase.table("contacts")
        .select("id, whatsapp_number, profile_picture_url")
        .not_.is_("profile_picture_url", "null")
        .limit(limit * 2)  # Récupérer plus pour filtrer
    )
    
    if not contacts_res.data:
        logger.debug("No contacts with profile pictures to refresh")
        return
    
    # Filtrer ceux qui n'ont pas été mis à jour récemment (basé sur le cache)
    contacts_to_refresh = []
    now = datetime.now(timezone.utc)
    seconds_old = days_old * 86400
    
    for contact in contacts_res.data:
        cache_key = f"{contact['id']}_{contact['whatsapp_number']}"
        last_update = _last_update_time.get(cache_key)
        
        # Si pas dans le cache ou mis à jour il y a plus de X jours, rafraîchir
        if not last_update or (now - last_update).total_seconds() > seconds_old:
            contacts_to_refresh.append(contact)
            
            # Limiter le nombre de contacts à rafraîchir
            if len(contacts_to_refresh) >= limit:
                break
    
    if not contacts_to_refresh:
        logger.debug("No contacts need profile picture refresh")
        return
    
    logger.info(f"Refreshing profile pictures for {len(contacts_to_refresh)} contacts (older than {days_old} days)")
    
    for contact in contacts_to_refresh:
        await queue_profile_picture_update(
            contact_id=contact["id"],
            whatsapp_number=contact["whatsapp_number"],
            account_id=account_id,
            priority=False
        )
    
    # Démarrer le traitement
    if not _processing_queue:
        asyncio.create_task(_process_profile_update_queue())


async def periodic_profile_picture_update():
    """
    Tâche périodique qui met à jour les images de profil automatiquement
    - Met à jour les contacts sans image
    - Rafraîchit les images anciennes
    """
    logger.info("🔄 Starting periodic profile picture update task")
    
    while True:
        try:
            # Attendre 1 heure entre chaque cycle
            await asyncio.sleep(3600)
            
            # Récupérer tous les comptes actifs
            accounts = await get_all_accounts()
            if not accounts:
                logger.debug("No active accounts found for profile picture update")
                continue
            
            for account in accounts:
                account_id = account["id"]
                
                try:
                    # 1. Mettre à jour les contacts sans image (priorité)
                    logger.info(f"Updating missing profile pictures for account {account_id}")
                    await update_all_contacts_profile_pictures(account_id, limit=30)
                    
                    # Attendre un peu entre les comptes
                    await asyncio.sleep(10)
                    
                    # 2. Rafraîchir les images anciennes (moins prioritaire)
                    logger.info(f"Refreshing old profile pictures for account {account_id}")
                    await refresh_old_profile_pictures(account_id, limit=20, days_old=7)
                    
                except Exception as e:
                    logger.error(f"Error updating profile pictures for account {account_id}: {e}", exc_info=True)
                    continue
            
            logger.info("✅ Periodic profile picture update cycle completed")
            
        except asyncio.CancelledError:
            logger.info("🛑 Periodic profile picture update task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in periodic profile picture update task: {e}", exc_info=True)
            # En cas d'erreur, attendre 5 minutes avant de réessayer
            try:
                await asyncio.sleep(300)
            except asyncio.CancelledError:
                logger.info("🛑 Periodic profile picture update task cancelled during error recovery")
                break

