"""
Service pour gérer les templates en attente de validation Meta
"""
import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any, List

from app.core.db import supabase, supabase_execute
from app.core.pg import execute as pg_execute, fetch_all, fetch_one, get_pool
from app.services import whatsapp_api_service
from app.services.template_validator import TemplateValidator
from app.services.message_service import send_template_message
from app.services.account_service import get_account_by_id
from app.services.conversation_service import normalize_phone_number

logger = logging.getLogger(__name__)

# Cache of template names known to not exist on Meta (error 132001).
# Avoids repeatedly calling the API for templates that will never work.
# Entries expire after 1 hour so a re-created template can be picked up.
_TEMPLATE_NOT_FOUND_TTL = 3600
_template_not_found_cache: Dict[str, float] = {}


def _is_template_blacklisted(template_name: str) -> bool:
    import time
    ts = _template_not_found_cache.get(template_name)
    if ts is None:
        return False
    if time.time() - ts > _TEMPLATE_NOT_FOUND_TTL:
        _template_not_found_cache.pop(template_name, None)
        return False
    return True


def _blacklist_template(template_name: str):
    import time
    _template_not_found_cache[template_name] = time.time()


# --- Polling statut template Meta (check_template_status_async) ---
TEMPLATE_ASYNC_INITIAL_DELAY_SEC = 60
TEMPLATE_ASYNC_POLL_INTERVAL_SEC = 300  # 5 minutes
# Beaucoup d'essais mais fini (~21 jours à pas de 5 min)
TEMPLATE_ASYNC_MAX_POLL_DAYS = 21
TEMPLATE_ASYNC_MAX_ATTEMPTS = max(
    1,
    int(TEMPLATE_ASYNC_MAX_POLL_DAYS * 24 * 60 * 60 / TEMPLATE_ASYNC_POLL_INTERVAL_SEC),
)

# Évite plusieurs boucles CHECK-ASYNC concurrentes pour le même message (redémarrages / doublons).
_active_template_async_polls: set[str] = set()

# Verrou par message_id : plusieurs tâches (periodic check, check async, endpoint manuel…)
# peuvent appeler send_pending_template en parallèle ; sans verrou, deux coroutines voient
# wa_message_id NULL et envoient deux fois le même template.
_template_send_registry_lock = asyncio.Lock()
_template_send_locks: Dict[str, asyncio.Lock] = {}


async def _template_send_lock_for(message_id: str) -> asyncio.Lock:
    async with _template_send_registry_lock:
        if message_id not in _template_send_locks:
            _template_send_locks[message_id] = asyncio.Lock()
        return _template_send_locks[message_id]


def schedule_check_template_status_async(message_id: str) -> None:
    """Lance au plus une boucle CHECK-ASYNC par message (évite doublons au redémarrage / double insert)."""
    if message_id in _active_template_async_polls:
        logger.info(
            "⏭️ [CHECK-ASYNC] Tâche déjà en cours pour le message %s, pas de doublon",
            message_id,
        )
        return

    _active_template_async_polls.add(message_id)

    async def _runner():
        try:
            await check_template_status_async(message_id)
        finally:
            _active_template_async_polls.discard(message_id)

    asyncio.create_task(_runner())


async def create_and_queue_template(
    conversation_id: str,
    account_id: str,
    message_id: str,
    text_content: str,
    campaign_id: Optional[str] = None,
    header_text: Optional[str] = None,
    body_text: Optional[str] = None,
    footer_text: Optional[str] = None,
    buttons: Optional[list] = None,
    created_by_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Crée un template Meta et le met en file d'attente
    
    Args:
        conversation_id: ID de la conversation
        account_id: ID du compte WhatsApp
        message_id: ID du message
        text_content: Texte complet (utilisé si body_text n'est pas fourni)
        campaign_id: ID de la campagne (optionnel)
        header_text: Texte du header (optionnel)
        body_text: Texte du body (optionnel, utilise text_content si non fourni)
        footer_text: Texte du footer (optionnel)
        buttons: Liste de boutons [{"id": "...", "title": "..."}] (optionnel)
        created_by_user_id: Utilisateur ayant demandé l'envoi (optionnel)
    """
    
    logger.info("=" * 80)
    logger.info(f"🔧 [CREATE-TEMPLATE] ========== DÉBUT CRÉATION TEMPLATE ==========")
    logger.info(f"🔧 [CREATE-TEMPLATE] conversation_id={conversation_id}")
    logger.info(f"🔧 [CREATE-TEMPLATE] account_id={account_id}")
    logger.info(f"🔧 [CREATE-TEMPLATE] message_id={message_id}")
    logger.info(f"🔧 [CREATE-TEMPLATE] =============================================")
    
    # Normaliser les valeurs None et chaînes vides
    # S'assurer que header_text et footer_text sont None (pas "") si vides
    logger.info(f"🔍 [CREATE-TEMPLATE] Analyse des paramètres reçus:")
    logger.info(f"   - header_text (avant normalisation): {repr(header_text)} (type: {type(header_text).__name__})")
    logger.info(f"   - body_text (avant normalisation): {repr(body_text)} (type: {type(body_text).__name__})")
    logger.info(f"   - footer_text (avant normalisation): {repr(footer_text)} (type: {type(footer_text).__name__})")
    logger.info(f"   - buttons (avant normalisation): {repr(buttons)} (type: {type(buttons).__name__})")
    logger.info(f"   - text_content: {repr(text_content[:100] if text_content else None)}")
    
    normalized_header_text = header_text.strip() if header_text and header_text.strip() else None
    normalized_footer_text = footer_text.strip() if footer_text and footer_text.strip() else None
    
    logger.info(f"🔍 [CREATE-TEMPLATE] Après normalisation:")
    logger.info(f"   - normalized_header_text: {repr(normalized_header_text)}")
    logger.info(f"   - normalized_footer_text: {repr(normalized_footer_text)}")
    
    # Utiliser body_text si fourni, sinon text_content
    actual_body_text = body_text if body_text is not None else text_content
    logger.info(f"🔍 [CREATE-TEMPLATE] actual_body_text: {repr(actual_body_text[:100] if actual_body_text else None)}")
    logger.info(f"🔍 [CREATE-TEMPLATE] Header: {normalized_header_text}, Footer: {normalized_footer_text}, Buttons: {len(buttons) if buttons else 0}")
    if buttons:
        logger.info(f"🔍 [CREATE-TEMPLATE] Détails des boutons:")
        for idx, btn in enumerate(buttons):
            logger.info(f"   Bouton {idx + 1}: {repr(btn)}")
    
    # Valider le texte du body
    is_valid, errors = TemplateValidator.validate_text(actual_body_text)
    
    # Valider header et footer avec leurs limites spécifiques
    if normalized_header_text:
        # Vérifier la longueur du header (max 60 caractères)
        if len(normalized_header_text) > TemplateValidator.MAX_HEADER_LENGTH:
            errors.append(f"Le header ne peut pas dépasser {TemplateValidator.MAX_HEADER_LENGTH} caractères (actuellement: {len(normalized_header_text)})")
        header_valid, header_errors = TemplateValidator.validate_text(normalized_header_text)
        if not header_valid:
            errors.extend(header_errors)
    
    if normalized_footer_text:
        # Vérifier la longueur du footer (max 60 caractères)
        if len(normalized_footer_text) > TemplateValidator.MAX_FOOTER_LENGTH:
            errors.append(f"Le footer ne peut pas dépasser {TemplateValidator.MAX_FOOTER_LENGTH} caractères (actuellement: {len(normalized_footer_text)})")
        footer_valid, footer_errors = TemplateValidator.validate_text(normalized_footer_text)
        if not footer_valid:
            errors.extend(footer_errors)
    
    # is_valid est maintenant False si on a des erreurs
    is_valid = len(errors) == 0
    
    logger.info(f"✅ [CREATE-TEMPLATE] Validation du texte: is_valid={is_valid}, errors={errors}")
    if not is_valid:
        logger.error(f"❌ [CREATE-TEMPLATE] Texte invalide: {errors}")
        return {
            "success": False,
            "errors": errors
        }
    
    # Générer un nom de template unique (utiliser le body pour le nom)
    template_name = TemplateValidator.generate_template_name(actual_body_text, conversation_id)
    
    # Valider le nom généré
    name_valid, name_errors = TemplateValidator.validate_template_name(template_name)
    if not name_valid:
        return {
            "success": False,
            "errors": name_errors
        }
    
    # Sanitizer les textes
    sanitized_body = TemplateValidator.sanitize_for_template(actual_body_text)
    
    # Pour header et footer, respecter les limites Meta (60 caractères max)
    sanitized_header = None
    if normalized_header_text:
        sanitized_header = TemplateValidator.sanitize_for_template(normalized_header_text)
        if len(sanitized_header) > TemplateValidator.MAX_HEADER_LENGTH:
            sanitized_header = sanitized_header[:TemplateValidator.MAX_HEADER_LENGTH-3] + "..."
    
    sanitized_footer = None
    if normalized_footer_text:
        sanitized_footer = TemplateValidator.sanitize_for_template(normalized_footer_text)
        if len(sanitized_footer) > TemplateValidator.MAX_FOOTER_LENGTH:
            sanitized_footer = sanitized_footer[:TemplateValidator.MAX_FOOTER_LENGTH-3] + "..."
    
    # Récupérer le compte
    account = await get_account_by_id(account_id)
    if not account:
        logger.error(f"❌ Compte {account_id} non trouvé pour la création du template")
        return {"success": False, "errors": ["Compte non trouvé"]}
    
    waba_id = account.get("waba_id")
    access_token = account.get("access_token")
    account_name = account.get("name", "Inconnu")
    
    logger.info(f"📝 Création du template '{template_name}' pour le message {message_id}")
    logger.info(f"   Compte WhatsApp: {account_name} (ID: {account_id}, WABA: {waba_id})")
    
    if not waba_id or not access_token:
        logger.error(f"❌ WhatsApp non configuré pour le compte {account_name}: waba_id={waba_id}, access_token={'présent' if access_token else 'absent'}")
        return {"success": False, "errors": ["WhatsApp non configuré (waba_id ou access_token manquant)"]}
    
    # Créer le template via Meta API
    try:
        # Construire les composants du template
        components = []
        
        # HEADER (si fourni)
        if sanitized_header:
            components.append({
                "type": "HEADER",
                "format": "TEXT",
                "text": sanitized_header
            })
        
        # BODY (toujours présent)
        components.append({
            "type": "BODY",
            "text": sanitized_body
        })
        
        # FOOTER (si fourni)
        if sanitized_footer:
            components.append({
                "type": "FOOTER",
                "text": sanitized_footer
            })
        
        # BUTTONS (si fournis)
        meta_buttons = []
        if buttons and len(buttons) > 0:
            # Convertir les boutons au format Meta (QUICK_REPLY)
            for btn in buttons[:3]:  # Max 3 boutons
                if btn.get("title"):
                    meta_buttons.append({
                        "type": "QUICK_REPLY",
                        "text": btn["title"][:20]  # Max 20 caractères pour QUICK_REPLY
                    })
            
            if meta_buttons:
                components.append({
                    "type": "BUTTONS",
                    "buttons": meta_buttons
                })
        
        logger.info(f"📤 [CREATE-TEMPLATE] ========== AVANT APPEL API META ==========")
        logger.info(f"📤 [CREATE-TEMPLATE] WABA ID: {waba_id}")
        logger.info(f"📤 [CREATE-TEMPLATE] Template name: {template_name}")
        logger.info(f"📤 [CREATE-TEMPLATE] Category: UTILITY")
        logger.info(f"📤 [CREATE-TEMPLATE] Language: fr")
        logger.info(f"📤 [CREATE-TEMPLATE] Nombre de components: {len(components)}")
        logger.info(f"📤 [CREATE-TEMPLATE] Header: {sanitized_header if sanitized_header else 'None (aucun header)'}")
        logger.info(f"📤 [CREATE-TEMPLATE] Body: {sanitized_body[:100] if len(sanitized_body) > 100 else sanitized_body}")
        logger.info(f"📤 [CREATE-TEMPLATE] Footer: {sanitized_footer if sanitized_footer else 'None (aucun footer)'}")
        logger.info(f"📤 [CREATE-TEMPLATE] Nombre de boutons: {len(meta_buttons)}")
        if meta_buttons:
            logger.info(f"📤 [CREATE-TEMPLATE] Boutons détaillés:")
            for idx, btn in enumerate(meta_buttons):
                logger.info(f"   Bouton {idx + 1}: type={btn.get('type')}, text={btn.get('text')}")
        else:
            logger.warning(f"⚠️ [CREATE-TEMPLATE] AUCUN BOUTON DÉTECTÉ!")
        logger.info(f"📤 [CREATE-TEMPLATE] Components complets (JSON):")
        logger.info(f"   {json.dumps(components, indent=2, ensure_ascii=False)}")
        logger.info(f"📤 [CREATE-TEMPLATE] =============================================")
        
        logger.info(f"📤 [CREATE-TEMPLATE] Appel à whatsapp_api_service.create_message_template...")
        result = await whatsapp_api_service.create_message_template(
            waba_id=waba_id,
            access_token=access_token,
            name=template_name,
            category="UTILITY",  # UTILITY pour les messages transactionnels
            language="fr",
            components=components
        )
        
        logger.info(f"📥 [CREATE-TEMPLATE] ========== RÉPONSE META ==========")
        logger.info(f"📥 [CREATE-TEMPLATE] Réponse complète: {json.dumps(result, indent=2, ensure_ascii=False)}")
        logger.info(f"📥 [CREATE-TEMPLATE] =================================")
        
        meta_template_id = result.get("id")
        
        if not meta_template_id:
            logger.error(f"❌ [CREATE-TEMPLATE] Meta n'a pas retourné d'ID pour le template '{template_name}'")
            logger.error(f"   Réponse complète: {result}")
            return {
                "success": False,
                "errors": ["Erreur lors de la création du template: aucun ID retourné par Meta"]
            }
        
        logger.info(f"✅ [CREATE-TEMPLATE] Template créé sur Meta avec l'ID: {meta_template_id}")
        
        # Stocker dans la base
        from app.core.db import supabase
        from app.services.template_deduplication import TemplateDeduplication
        
        # Calculer le hash du template pour la déduplication
        # Utiliser les versions sanitized (ou None si non fournis)
        template_hash = TemplateDeduplication.compute_template_hash(
            sanitized_body, sanitized_header, sanitized_footer
        )
        
        if get_pool():
            await pg_execute(
                """
                INSERT INTO pending_template_messages
                (message_id, conversation_id, account_id, template_name, text_content, meta_template_id, template_status, template_hash, campaign_id, created_by_user_id)
                VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9, $10::uuid)
                """,
                message_id, conversation_id, account_id, template_name, text_content,
                meta_template_id, "PENDING", template_hash, campaign_id, created_by_user_id,
            )
        else:
            pending_template_payload = {
                "message_id": message_id,
                "conversation_id": conversation_id,
                "account_id": account_id,
                "template_name": template_name,
                "text_content": text_content,
                "meta_template_id": meta_template_id,
                "template_status": "PENDING",
                "template_hash": template_hash,
            }
            if campaign_id:
                pending_template_payload["campaign_id"] = campaign_id
            if created_by_user_id is not None:
                pending_template_payload["created_by_user_id"] = created_by_user_id
            await supabase_execute(
                supabase.table("pending_template_messages").insert(pending_template_payload)
            )
        
        logger.info(f"✅ Template '{template_name}' créé et mis en file d'attente (ID Meta: {meta_template_id})")
        logger.info(f"   Compte: {account_name} (WABA: {waba_id})")
        
        # Faire une première vérification immédiate (le template peut être approuvé très rapidement)
        asyncio.create_task(check_template_status_once(message_id))
        
        # Lancer la vérification périodique en arrière-plan (non bloquant)
        schedule_check_template_status_async(message_id)
        
        # Vérifier si le message est déjà lu (au cas où il serait lu très rapidement)
        # et nettoyer le template si nécessaire
        message_read = False
        if get_pool():
            row = await fetch_one("SELECT status FROM messages WHERE id = $1::uuid LIMIT 1", message_id)
            message_read = row and row.get("status") == "read"
        else:
            from app.core.db import supabase
            message_check = await supabase_execute(
                supabase.table("messages").select("status").eq("id", message_id).limit(1)
            )
            message_read = bool(message_check.data and len(message_check.data) > 0 and message_check.data[0].get("status") == "read")
        if message_read:
            # Le message est déjà lu, supprimer le template immédiatement
            asyncio.create_task(delete_auto_template_for_message(message_id))
        
        return {
            "success": True,
            "template_name": template_name,
            "meta_template_id": meta_template_id
        }
        
    except Exception as e:
        logger.error(f"❌ [CREATE-TEMPLATE] Erreur lors de la création du template: {e}", exc_info=True)
        error_msg = str(e)
        
        # Extraire le message d'erreur de Meta si disponible
        if hasattr(e, 'response'):
            try:
                if hasattr(e.response, 'json'):
                    error_data = e.response.json()
                    logger.error(f"❌ [CREATE-TEMPLATE] Détails de l'erreur Meta: {error_data}")
                    if 'error' in error_data:
                        error_info = error_data['error']
                        error_msg = error_info.get('message', error_msg)
                        # Ajouter les détails supplémentaires si disponibles
                        if 'error_subcode' in error_info:
                            error_msg += f" (subcode: {error_info['error_subcode']})"
                        if 'error_user_title' in error_info:
                            error_msg += f" - {error_info['error_user_title']}"
                elif hasattr(e.response, 'text'):
                    error_text = e.response.text
                    logger.error(f"❌ [CREATE-TEMPLATE] Réponse texte d'erreur Meta: {error_text}")
                    error_msg = error_text[:200]  # Limiter la longueur
            except Exception as parse_error:
                logger.error(f"❌ [CREATE-TEMPLATE] Erreur lors du parsing de l'erreur: {parse_error}")
        
        return {
            "success": False,
            "errors": [f"Erreur lors de la création du template: {error_msg}"]
        }


async def create_and_queue_image_template(
    conversation_id: str,
    account_id: str,
    message_id: str,
    media_id: str,
    body_text: str = "(image)",
    created_by_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Crée un template Meta avec HEADER IMAGE et le met en file d'attente
    
    Args:
        conversation_id: ID de la conversation
        account_id: ID du compte WhatsApp
        message_id: ID du message
        media_id: ID du média WhatsApp (image)
        body_text: Texte du body (par défaut "(image)")
        created_by_user_id: Utilisateur ayant demandé l'envoi (optionnel)
    """
    
    logger.info("=" * 80)
    logger.info(f"🖼️ [CREATE-IMAGE-TEMPLATE] ========== DÉBUT CRÉATION TEMPLATE IMAGE ==========")
    logger.info(f"🖼️ [CREATE-IMAGE-TEMPLATE] conversation_id={conversation_id}")
    logger.info(f"🖼️ [CREATE-IMAGE-TEMPLATE] account_id={account_id}")
    logger.info(f"🖼️ [CREATE-IMAGE-TEMPLATE] message_id={message_id}")
    logger.info(f"🖼️ [CREATE-IMAGE-TEMPLATE] media_id={media_id}")
    logger.info(f"🖼️ [CREATE-IMAGE-TEMPLATE] body_text={body_text}")
    logger.info(f"🖼️ [CREATE-IMAGE-TEMPLATE] =============================================")
    
    # Valider le texte du body
    is_valid, errors = TemplateValidator.validate_text(body_text)
    
    if not is_valid:
        logger.error(f"❌ [CREATE-IMAGE-TEMPLATE] Texte invalide: {errors}")
        return {
            "success": False,
            "errors": errors
        }
    
    # Générer un nom de template unique pour les images
    # Utiliser un préfixe "auto_img_" pour identifier les templates d'images auto-créés
    template_name = f"auto_img_{conversation_id[:8]}_{message_id[:8]}_{int(datetime.now(timezone.utc).timestamp())}"
    
    # Valider le nom généré
    name_valid, name_errors = TemplateValidator.validate_template_name(template_name)
    if not name_valid:
        return {
            "success": False,
            "errors": name_errors
        }
    
    # Sanitizer le texte du body
    sanitized_body = TemplateValidator.sanitize_for_template(body_text)
    
    # Récupérer le compte
    account = await get_account_by_id(account_id)
    if not account:
        logger.error(f"❌ Compte {account_id} non trouvé pour la création du template")
        return {"success": False, "errors": ["Compte non trouvé"]}
    
    waba_id = account.get("waba_id")
    access_token = account.get("access_token")
    account_name = account.get("name", "Inconnu")
    
    logger.info(f"📝 Création du template image '{template_name}' pour le message {message_id}")
    logger.info(f"   Compte WhatsApp: {account_name} (ID: {account_id}, WABA: {waba_id})")
    
    if not waba_id or not access_token:
        logger.error(f"❌ WhatsApp non configuré pour le compte {account_name}: waba_id={waba_id}, access_token={'présent' if access_token else 'absent'}")
        return {"success": False, "errors": ["WhatsApp non configuré (waba_id ou access_token manquant)"]}
    
    # Récupérer le phone_number_id pour l'upload
    phone_number_id = account.get("phone_number_id")
    if not phone_number_id:
        logger.error(f"❌ phone_number_id manquant pour le compte {account_name}")
        return {"success": False, "errors": ["phone_number_id manquant"]}
    
    # Créer le template via Meta API avec HEADER IMAGE
    try:
        # Meta exige un exemple (example) pour les templates avec HEADER IMAGE
        # Il faut télécharger l'image depuis WhatsApp, puis l'uploader vers le WABA
        # pour obtenir un media_id à utiliser dans header_handle
        logger.info(f"📥 [CREATE-IMAGE-TEMPLATE] Téléchargement de l'image depuis WhatsApp (media_id: {media_id})...")
        
        # Télécharger l'image depuis WhatsApp
        from app.services.whatsapp_api_service import get_media_url, upload_media_from_bytes
        import asyncio
        
        uploaded_media_id = None  # Initialiser pour éviter les problèmes de scope
        result = None  # Résultat de la création du template
        meta_template_id = None  # ID du template créé sur Meta
        
        try:
            # Récupérer l'URL de téléchargement
            media_info = await get_media_url(media_id, access_token)
            download_url = media_info.get("url")
            
            if not download_url:
                logger.error(f"❌ [CREATE-IMAGE-TEMPLATE] Pas d'URL de téléchargement pour media_id: {media_id}")
                return {"success": False, "errors": ["Impossible de télécharger l'image depuis WhatsApp"]}
            
            # Télécharger le contenu de l'image
            logger.info(f"📥 [CREATE-IMAGE-TEMPLATE] Téléchargement depuis l'URL: {download_url[:100]}...")
            from app.core.http_client import get_http_client_for_media
            client = await get_http_client_for_media()
            media_response = await client.get(download_url, headers={"Authorization": f"Bearer {access_token}"})
            media_response.raise_for_status()
            
            # Détecter le content-type
            content_type = media_response.headers.get("content-type", "image/jpeg")
            media_data = media_response.content
            
            logger.info(f"📥 [CREATE-IMAGE-TEMPLATE] Image téléchargée: {len(media_data)} bytes, type: {content_type}")
            
            # Uploader vers Supabase Storage pour obtenir une URL publique accessible
            # Meta exige une URL publique pour les exemples de templates (pas un media_id)
            # Selon la documentation Meta: https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates
            from app.services.storage_service import upload_template_media
            
            logger.info(f"📤 [CREATE-IMAGE-TEMPLATE] Upload de l'image vers Supabase Storage pour obtenir une URL publique...")
            public_url = await upload_template_media(
                template_name=template_name,
                template_language="fr",
                account_id=account_id,
                media_data=media_data,
                media_type="IMAGE",
                content_type=content_type
            )
            
            if not public_url:
                logger.error(f"❌ [CREATE-IMAGE-TEMPLATE] Impossible d'obtenir une URL publique pour l'image")
                return {"success": False, "errors": ["Impossible d'obtenir une URL publique pour l'exemple"]}
            
            logger.info(f"✅ [CREATE-IMAGE-TEMPLATE] Image uploadée vers Supabase Storage, URL publique: {public_url}")
            
            # Uploader vers WhatsApp API (WABA) pour obtenir un media_id
            # Selon la documentation Meta, header_handle doit utiliser un media_id uploadé via leur API
            logger.info(f"📤 [CREATE-IMAGE-TEMPLATE] Upload de l'image vers WhatsApp API (WABA) pour obtenir le media_id...")
            upload_result = await upload_media_from_bytes(
                phone_number_id=phone_number_id,
                access_token=access_token,
                file_content=media_data,
                filename=f"{template_name}_image.png",
                mime_type=content_type
            )
            
            uploaded_media_id = upload_result.get("id")
            
            if not uploaded_media_id:
                logger.error(f"❌ [CREATE-IMAGE-TEMPLATE] Pas de media_id retourné par WhatsApp API")
                return {"success": False, "errors": ["Impossible d'uploader l'image vers WhatsApp API"]}
            
            logger.info(f"✅ [CREATE-IMAGE-TEMPLATE] Image uploadée vers WABA avec media_id: {uploaded_media_id}")
            
            # Attendre que l'image soit validée par Meta avant de créer le template
            # Meta exige que le media_id soit validé avant de pouvoir être utilisé dans un template
            logger.info(f"⏳ [CREATE-IMAGE-TEMPLATE] Attente de validation de l'image par Meta...")
            max_retries = 60  # 60 tentatives maximum (5 minutes au total)
            retry_delay = 5.0  # 5 secondes entre chaque tentative
            template_created = False
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    # Construire les composants du template avec le media_id (en string)
                    components = [
                        {
                            "type": "HEADER",
                            "format": "IMAGE",
                            "example": {
                                "header_handle": [str(uploaded_media_id)]  # Utiliser le media_id uploadé
                            }
                        },
                        {
                            "type": "BODY",
                            "text": sanitized_body
                        }
                    ]
                    
                    # Essayer de créer le template
                    if attempt == 0:
                        logger.info(f"🔄 [CREATE-IMAGE-TEMPLATE] Première tentative de création du template avec media_id: {uploaded_media_id}")
                    elif attempt % 10 == 0:  # Logger tous les 10 essais
                        logger.info(f"🔄 [CREATE-IMAGE-TEMPLATE] Tentative {attempt + 1}/{max_retries} de création du template...")
                    
                    result = await whatsapp_api_service.create_message_template(
                        waba_id=waba_id,
                        access_token=access_token,
                        name=template_name,
                        category="UTILITY",
                        language="fr",
                        components=components
                    )
                    
                    # Si on arrive ici, le template a été créé avec succès
                    meta_template_id = result.get("id")
                    if meta_template_id:
                        logger.info(f"✅ [CREATE-IMAGE-TEMPLATE] Template créé avec succès après {attempt + 1} tentatives!")
                        logger.info(f"📥 [CREATE-IMAGE-TEMPLATE] ========== RÉPONSE META ==========")
                        logger.info(f"📥 [CREATE-IMAGE-TEMPLATE] Réponse complète: {json.dumps(result, indent=2, ensure_ascii=False)}")
                        logger.info(f"📥 [CREATE-IMAGE-TEMPLATE] =================================")
                        template_created = True
                        break
                    else:
                        logger.warning(f"⚠️ [CREATE-IMAGE-TEMPLATE] Template créé mais pas d'ID retourné, nouvelle tentative...")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                        
                except Exception as template_error:
                    last_error = template_error
                    error_str = str(template_error)
                    
                    # Extraire le error_subcode depuis WhatsAppAPIError
                    error_subcode = None
                    if hasattr(template_error, 'error_subcode'):
                        error_subcode = template_error.error_subcode
                    elif hasattr(template_error, 'detail'):
                        error_detail = template_error.detail
                        if isinstance(error_detail, dict):
                            error_obj = error_detail.get('error', {})
                            error_subcode = error_obj.get('error_subcode')
                    
                    # Convertir en int pour la comparaison
                    if error_subcode is not None:
                        try:
                            error_subcode = int(error_subcode)
                        except (ValueError, TypeError):
                            pass
                    
                    # Si l'erreur indique que le media n'est pas valide (2388273 ou 2494102), on continue à attendre
                    is_media_validation_error = (
                        error_subcode == 2388273 or
                        error_subcode == 2494102 or
                        "2494102" in error_str or
                        "2388273" in error_str or
                        "Uploaded Media Handle Is Invalid" in error_str or
                        "Paramètre d'exemple manquant" in error_str or
                        ("Invalid parameter" in error_str and ("header_handle" in error_str.lower() or "IMAGE" in error_str))
                    )
                    
                    if is_media_validation_error:
                        if attempt < max_retries - 1:
                            if attempt == 0 or attempt % 10 == 0:  # Logger au début et tous les 10 essais
                                logger.info(f"⏳ [CREATE-IMAGE-TEMPLATE] Image pas encore validée par Meta (tentative {attempt + 1}/{max_retries}, error_subcode={error_subcode}), nouvelle tentative dans {retry_delay}s...")
                            await asyncio.sleep(retry_delay)
                        else:
                            logger.error(f"❌ [CREATE-IMAGE-TEMPLATE] Image non validée après {max_retries} tentatives (error_subcode={error_subcode})")
                    else:
                        # Autre erreur, on la propage
                        logger.error(f"❌ [CREATE-IMAGE-TEMPLATE] Erreur non liée à la validation du media: {error_str} (error_subcode={error_subcode})")
                        raise
            
            if not template_created:
                logger.error(f"❌ [CREATE-IMAGE-TEMPLATE] Impossible de créer le template après {max_retries} tentatives")
                if last_error:
                    raise last_error
                return {"success": False, "errors": [f"Impossible de créer le template: image non validée après {max_retries} tentatives"]}
            
            meta_template_id = result.get("id")
            
            if not meta_template_id:
                logger.error(f"❌ [CREATE-IMAGE-TEMPLATE] Meta n'a pas retourné d'ID pour le template '{template_name}'")
                return {
                    "success": False,
                    "errors": ["Erreur lors de la création du template: aucun ID retourné par Meta"]
                }
            
            logger.info(f"✅ [CREATE-IMAGE-TEMPLATE] Template créé sur Meta avec l'ID: {meta_template_id}")
            logger.info(f"📥 [CREATE-IMAGE-TEMPLATE] ========== RÉPONSE META ==========")
            logger.info(f"📥 [CREATE-IMAGE-TEMPLATE] Réponse complète: {json.dumps(result, indent=2, ensure_ascii=False)}")
            logger.info(f"📥 [CREATE-IMAGE-TEMPLATE] =================================")
            
        except Exception as media_error:
            logger.error(f"❌ [CREATE-IMAGE-TEMPLATE] Erreur lors du téléchargement/upload de l'image: {media_error}", exc_info=True)
            return {"success": False, "errors": [f"Erreur lors du traitement de l'image: {str(media_error)}"]}
        
        # Vérification de sécurité
        if not meta_template_id:
            logger.error(f"❌ [CREATE-IMAGE-TEMPLATE] meta_template_id n'est pas défini")
            return {"success": False, "errors": ["Erreur: template non créé"]}
        
        # Stocker dans la base avec le media_id pour référence
        from app.services.template_deduplication import TemplateDeduplication
        
        template_hash = TemplateDeduplication.compute_template_hash(
            sanitized_body, None, None  # Pas de header/footer texte pour les images
        )
        
        if get_pool():
            await pg_execute(
                """
                INSERT INTO pending_template_messages
                (message_id, conversation_id, account_id, template_name, text_content, meta_template_id, template_status, template_hash, header_media_id, created_by_user_id)
                VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9, $10::uuid)
                """,
                message_id, conversation_id, account_id, template_name, body_text,
                meta_template_id, "PENDING", template_hash, uploaded_media_id, created_by_user_id,
            )
        else:
            pending_template_payload = {
                "message_id": message_id,
                "conversation_id": conversation_id,
                "account_id": account_id,
                "template_name": template_name,
                "text_content": body_text,
                "meta_template_id": meta_template_id,
                "template_status": "PENDING",
                "template_hash": template_hash,
                "header_media_id": uploaded_media_id,
            }
            if created_by_user_id is not None:
                pending_template_payload["created_by_user_id"] = created_by_user_id
            await supabase_execute(
                supabase.table("pending_template_messages").insert(pending_template_payload)
            )
        
        logger.info(f"✅ Template image '{template_name}' créé et mis en file d'attente (ID Meta: {meta_template_id})")
        logger.info(f"   Compte: {account_name} (WABA: {waba_id})")
        
        # Faire une première vérification immédiate
        asyncio.create_task(check_template_status_once(message_id))
        
        # Lancer la vérification périodique en arrière-plan
        schedule_check_template_status_async(message_id)
        
        # Vérifier si le message est déjà lu
        message_read = False
        if get_pool():
            row = await fetch_one("SELECT status FROM messages WHERE id = $1::uuid LIMIT 1", message_id)
            message_read = row and row.get("status") == "read"
        else:
            message_check = await supabase_execute(
                supabase.table("messages").select("status").eq("id", message_id).limit(1)
            )
            message_read = bool(message_check.data and len(message_check.data) > 0 and message_check.data[0].get("status") == "read")
        if message_read:
            asyncio.create_task(delete_auto_template_for_message(message_id))
        
        return {
            "success": True,
            "template_name": template_name,
            "meta_template_id": meta_template_id
        }
        
    except Exception as e:
        logger.error(f"❌ [CREATE-IMAGE-TEMPLATE] Erreur lors de la création du template: {e}", exc_info=True)
        error_msg = str(e)
        
        # Extraire le message d'erreur de Meta si disponible
        if hasattr(e, 'response'):
            try:
                if hasattr(e.response, 'json'):
                    error_data = e.response.json()
                    logger.error(f"❌ [CREATE-IMAGE-TEMPLATE] Détails de l'erreur Meta: {error_data}")
                    if 'error' in error_data:
                        error_info = error_data['error']
                        error_msg = error_info.get('message', error_msg)
                        if 'error_subcode' in error_info:
                            error_msg += f" (subcode: {error_info['error_subcode']})"
                        if 'error_user_title' in error_info:
                            error_msg += f" - {error_info['error_user_title']}"
                elif hasattr(e.response, 'text'):
                    error_text = e.response.text
                    logger.error(f"❌ [CREATE-IMAGE-TEMPLATE] Réponse texte d'erreur Meta: {error_text}")
                    error_msg = error_text[:200]
            except Exception as parse_error:
                logger.error(f"❌ [CREATE-IMAGE-TEMPLATE] Erreur lors du parsing de l'erreur: {parse_error}")
        
        return {
            "success": False,
            "errors": [f"Erreur lors de la création du template: {error_msg}"]
        }


async def check_template_status_once(message_id: str):
    """Fait une vérification unique du statut du template (pour vérification immédiate)"""
    # Attendre 5 secondes pour que Meta synchronise
    logger.info(f"⏳ [CHECK-ONCE] Attente de 5 secondes avant vérification immédiate pour le message {message_id}")
    await asyncio.sleep(5)
    
    try:
        logger.info(f"🔍 [CHECK-ONCE] Vérification immédiate du statut pour le message {message_id}")
        
        result = await check_and_update_template_status(message_id)
        
        logger.info(f"📊 [CHECK-ONCE] Résultat pour message {message_id}: statut={result.get('status')}")
        
        if result["status"] == "APPROVED":
            logger.info(f"✅ [CHECK-ONCE] Template approuvé immédiatement pour le message {message_id}, envoi en cours...")
            await send_pending_template(message_id)
        elif result["status"] == "NOT_FOUND":
            logger.warning(
                f"⚠️ [CHECK-ONCE] Template introuvable pour le message {message_id} - abandon et nettoyage"
            )
            await abandon_stale_pending_template(
                message_id,
                "Suivi template introuvable (entrée supprimée ou incohérente).",
            )
        elif result["status"] == "REJECTED":
            logger.warning(f"❌ [CHECK-ONCE] Template rejeté immédiatement pour le message {message_id}: {result.get('rejection_reason', 'Raison inconnue')}")
            # Vérifier si c'est une campagne broadcast
            campaign_id = None
            if get_pool():
                row = await fetch_one("SELECT campaign_id FROM pending_template_messages WHERE message_id = $1::uuid LIMIT 1", message_id)
                if row:
                    campaign_id = row.get("campaign_id")
            else:
                pending_result = await supabase_execute(
                    supabase.table("pending_template_messages")
                    .select("campaign_id")
                    .eq("message_id", message_id)
                    .limit(1)
                )
                if pending_result.data and len(pending_result.data) > 0:
                    campaign_id = pending_result.data[0].get("campaign_id")
            
            if campaign_id:
                # Marquer tous les destinataires payants de la campagne comme échoués
                await _mark_campaign_as_failed(campaign_id, result.get("rejection_reason", "Template rejeté par Meta"))
            else:
                await mark_message_as_failed(message_id, result.get("rejection_reason", "Template rejeté par Meta"))
        else:
            logger.info(f"⏳ [CHECK-ONCE] Template encore en attente pour le message {message_id} (statut: {result.get('status')})")
    except Exception as e:
        logger.error(f"❌ [CHECK-ONCE] Erreur lors de la vérification immédiate pour le message {message_id}: {e}", exc_info=True)


async def check_template_status_async(message_id: str):
    """Vérifie le statut d'un template en arrière-plan de manière périodique"""
    # Attendre un peu avant la première vérification (Meta peut prendre quelques secondes)
    # On a déjà fait une vérification immédiate, donc on attend plus longtemps ici
    await asyncio.sleep(TEMPLATE_ASYNC_INITIAL_DELAY_SEC)

    max_attempts = TEMPLATE_ASYNC_MAX_ATTEMPTS

    logger.info(
        f"🔄 [CHECK-ASYNC] Début pour le message {message_id} "
        f"(max {max_attempts} essais ≈ {TEMPLATE_ASYNC_MAX_POLL_DAYS} jours, toutes les {TEMPLATE_ASYNC_POLL_INTERVAL_SEC // 60} min)"
    )
    print(
        f"🔄 [CHECK-ASYNC] Début de la vérification périodique du statut du template pour le message {message_id}"
    )

    attempt = 0
    while attempt < max_attempts:
        try:
            logger.info(
                f"🔍 [CHECK-ASYNC] Vérification #{attempt + 1}/{max_attempts} pour le message {message_id}"
            )
            print(
                f"🔍 [CHECK-ASYNC] Vérification #{attempt + 1}/{max_attempts} pour le message {message_id}"
            )

            result = await check_and_update_template_status(message_id)

            logger.info(
                f"📊 [CHECK-ASYNC] Résultat pour message {message_id}: statut={result.get('status')}"
            )
            print(
                f"📊 [CHECK-ASYNC] Résultat pour message {message_id}: statut={result.get('status')}"
            )

            if result["status"] in ["APPROVED", "REJECTED"]:
                if result["status"] == "APPROVED":
                    logger.info(
                        f"✅ [CHECK-ASYNC] Template approuvé pour le message {message_id}, envoi en cours..."
                    )
                    print(
                        f"✅ [CHECK-ASYNC] Template approuvé pour le message {message_id}, envoi en cours..."
                    )
                    await send_pending_template(message_id)
                else:
                    logger.warning(
                        f"❌ [CHECK-ASYNC] Template rejeté pour le message {message_id}: "
                        f"{result.get('rejection_reason', 'Raison inconnue')}"
                    )
                    print(
                        f"❌ [CHECK-ASYNC] Template rejeté pour le message {message_id}: "
                        f"{result.get('rejection_reason', 'Raison inconnue')}"
                    )
                    campaign_id = None
                    if get_pool():
                        row = await fetch_one(
                            "SELECT campaign_id FROM pending_template_messages WHERE message_id = $1::uuid LIMIT 1",
                            message_id,
                        )
                        if row:
                            campaign_id = row.get("campaign_id")
                    else:
                        pending_result = await supabase_execute(
                            supabase.table("pending_template_messages")
                            .select("campaign_id")
                            .eq("message_id", message_id)
                            .limit(1)
                        )
                        if pending_result.data and len(pending_result.data) > 0:
                            campaign_id = pending_result.data[0].get("campaign_id")

                    if campaign_id:
                        await _mark_campaign_as_failed(
                            campaign_id,
                            result.get("rejection_reason", "Template rejeté par Meta"),
                        )
                    else:
                        await mark_message_as_failed(
                            message_id,
                            result.get("rejection_reason", "Template rejeté par Meta"),
                        )
                break
            if result["status"] == "NOT_FOUND":
                logger.warning(
                    f"⚠️ [CHECK-ASYNC] Template non trouvé pour le message {message_id} - abandon et nettoyage"
                )
                print(
                    f"⚠️ [CHECK-ASYNC] Template non trouvé pour le message {message_id}, arrêt de la vérification"
                )
                await abandon_stale_pending_template(
                    message_id,
                    "Suivi template introuvable (entrée supprimée ou incohérente).",
                )
                break
            logger.info(
                f"⏳ [CHECK-ASYNC] Template encore en attente pour le message {message_id} "
                f"(statut: {result.get('status')})"
            )
            print(
                f"⏳ [CHECK-ASYNC] Template encore en attente pour le message {message_id} "
                f"(statut: {result.get('status')})"
            )

        except Exception as e:
            logger.error(
                f"❌ [CHECK-ASYNC] Erreur lors de la vérification du statut du template pour {message_id}: {e}",
                exc_info=True,
            )
            print(
                f"❌ [CHECK-ASYNC] Erreur lors de la vérification du statut du template pour {message_id}: {e}"
            )

        if attempt < max_attempts - 1:
            logger.info(
                f"⏰ [CHECK-ASYNC] Attente de {TEMPLATE_ASYNC_POLL_INTERVAL_SEC // 60} minutes "
                f"avant la prochaine vérification pour le message {message_id}"
            )
            print(
                f"⏰ [CHECK-ASYNC] Attente de 5 minutes avant la prochaine vérification pour le message {message_id}"
            )
            await asyncio.sleep(TEMPLATE_ASYNC_POLL_INTERVAL_SEC)
        attempt += 1

    if attempt >= max_attempts:
        logger.warning(
            f"⏰ [CHECK-ASYNC] Limite d'essais atteinte ({max_attempts}) pour le message {message_id} "
            f"(≈ {TEMPLATE_ASYNC_MAX_POLL_DAYS} jours) - abandon"
        )
        print(
            f"⏰ [CHECK-ASYNC] Timeout: Le template pour le message {message_id} n'a pas été approuvé après "
            f"{TEMPLATE_ASYNC_MAX_POLL_DAYS} jours"
        )
        await abandon_stale_pending_template(
            message_id,
            f"Délai d'approbation Meta dépassé ({TEMPLATE_ASYNC_MAX_POLL_DAYS} jours).",
        )


async def check_and_update_template_status(message_id: str) -> Dict[str, Any]:
    """Vérifie le statut d'un template auprès de Meta et met à jour la base"""
    from app.core.db import supabase
    
    logger.info(f"🔍 [CHECK-STATUS] Vérification du statut Meta pour le message {message_id}")
    
    pending = None
    if get_pool():
        row = await fetch_one(
            """
            SELECT p.id, p.message_id, p.conversation_id, p.account_id, p.template_name, p.text_content,
                   p.meta_template_id, p.template_status, p.rejection_reason, p.template_hash, p.header_media_id, p.campaign_id,
                   w.waba_id, w.access_token
            FROM pending_template_messages p
            INNER JOIN whatsapp_accounts w ON w.id = p.account_id
            WHERE p.message_id = $1::uuid AND p.template_status IN ('PENDING', 'APPROVED')
            LIMIT 1
            """,
            message_id,
        )
        if row:
            pending = dict(row)
        if not pending:
            row_all = await fetch_one(
                """
                SELECT p.template_status, w.waba_id, w.access_token
                FROM pending_template_messages p
                INNER JOIN whatsapp_accounts w ON w.id = p.account_id
                WHERE p.message_id = $1::uuid
                LIMIT 1
                """,
                message_id,
            )
            if row_all:
                status = row_all.get("template_status", "UNKNOWN")
                logger.info(f"ℹ️ [CHECK-STATUS] Template trouvé avec statut {status} pour le message {message_id}")
                return {"status": status}
            logger.warning(f"❌ [CHECK-STATUS] Aucun template trouvé pour le message {message_id}")
            return {"status": "NOT_FOUND"}
    else:
        result = await supabase_execute(
            supabase.table("pending_template_messages")
            .select("*, whatsapp_accounts!inner(waba_id, access_token)")
            .eq("message_id", message_id)
            .in_("template_status", ["PENDING", "APPROVED"])
            .limit(1)
        )
        if not result.data or len(result.data) == 0:
            logger.info(f"⚠️ [CHECK-STATUS] Template non trouvé avec statut PENDING/APPROVED pour le message {message_id}, recherche de tous les statuts...")
            result_all = await supabase_execute(
                supabase.table("pending_template_messages")
                .select("*, whatsapp_accounts!inner(waba_id, access_token)")
                .eq("message_id", message_id)
                .limit(1)
            )
            if result_all.data and len(result_all.data) > 0:
                status = result_all.data[0].get("template_status", "UNKNOWN")
                logger.info(f"ℹ️ [CHECK-STATUS] Template trouvé avec statut {status} pour le message {message_id}")
                return {"status": status}
            logger.warning(f"❌ [CHECK-STATUS] Aucun template trouvé pour le message {message_id}")
            return {"status": "NOT_FOUND"}
        pending = result.data[0]
        account_info = pending.get("whatsapp_accounts", {})
        if isinstance(account_info, list) and len(account_info) > 0:
            account_info = account_info[0]
        elif not isinstance(account_info, dict):
            account_info = {}
        pending["waba_id"] = account_info.get("waba_id")
        pending["access_token"] = account_info.get("access_token")
    
    template_name = pending.get("template_name", "inconnu")
    logger.info(f"📋 [CHECK-STATUS] Template trouvé: {template_name} (ID Meta: {pending.get('meta_template_id')}) pour le message {message_id}")
    
    # Vérifier le statut auprès de Meta
    try:
        # Essayer d'abord de récupérer le template directement par ID (plus rapide et fiable)
        template = None
        if pending.get("meta_template_id"):
            logger.info(f"🔍 [CHECK-STATUS] Récupération directe du template par ID: {pending['meta_template_id']}")
            template = await whatsapp_api_service.get_message_template_by_id(
                template_id=pending["meta_template_id"],
                access_token=pending["access_token"]
            )
        
        # Si pas trouvé par ID (peut arriver si le template vient d'être créé), chercher par nom dans la liste
        if not template:
            logger.info(f"🔍 [CHECK-STATUS] Template non trouvé par ID, recherche par nom dans la liste...")
            all_templates = []
            after = None
            limit = 100
            
            while True:
                templates_result = await whatsapp_api_service.list_message_templates(
                    waba_id=pending["waba_id"],
                    access_token=pending["access_token"],
                    limit=limit,
                    after=after
                )
                
                templates_batch = templates_result.get("data", [])
                if not templates_batch:
                    break
                
                all_templates.extend(templates_batch)
                
                # Vérifier s'il y a une page suivante
                paging = templates_result.get("paging", {})
                after = paging.get("cursors", {}).get("after")
                if not after:
                    break
            
            # Chercher notre template par nom
            for t in all_templates:
                if t.get("name") == pending["template_name"]:
                    template = t
                    break
        
        if not template:
            logger.warning(f"⚠️ [CHECK-STATUS] Template {pending['template_name']} (ID: {pending['meta_template_id']}) non trouvé dans Meta - peut-être pas encore synchronisé")
            return {"status": "PENDING"}  # Peut-être pas encore synchronisé
        
        status = template.get("status", "PENDING")
        
        # Normaliser le statut Meta vers notre format
        # Meta peut retourner "APPROVED", "PENDING", "REJECTED", etc.
        meta_status_upper = status.upper() if isinstance(status, str) else str(status).upper()
        
        # Mettre à jour dans la base seulement si le statut a changé
        current_status = pending.get("template_status", "PENDING")
        
        logger.info(f"📊 [CHECK-STATUS] Statut Meta: {meta_status_upper}, Statut base: {current_status} pour le message {message_id}")
        
        if meta_status_upper == "APPROVED" and current_status != "APPROVED":
            if get_pool():
                await pg_execute(
                    "UPDATE pending_template_messages SET template_status = $2 WHERE message_id = $1::uuid",
                    message_id, "APPROVED",
                )
            else:
                await supabase_execute(
                    supabase.table("pending_template_messages")
                    .update({"template_status": "APPROVED"})
                    .eq("message_id", message_id)
                )
            logger.info(f"✅ [CHECK-STATUS] Template {pending['template_name']} approuvé par Meta (statut mis à jour) pour le message {message_id}")
        elif meta_status_upper == "REJECTED" and current_status != "REJECTED":
            reason = template.get("reason", "Rejeté par Meta")
            if get_pool():
                await pg_execute(
                    "UPDATE pending_template_messages SET template_status = $2, rejection_reason = $3 WHERE message_id = $1::uuid",
                    message_id, "REJECTED", reason,
                )
            else:
                await supabase_execute(
                    supabase.table("pending_template_messages")
                    .update({"template_status": "REJECTED", "rejection_reason": reason})
                    .eq("message_id", message_id)
                )
            logger.warning(f"❌ [CHECK-STATUS] Template {pending['template_name']} rejeté par Meta: {reason} pour le message {message_id}")
        elif meta_status_upper == "APPROVED" and current_status == "APPROVED":
            logger.info(f"ℹ️ [CHECK-STATUS] Template {pending['template_name']} déjà marqué comme approuvé pour le message {message_id}")
        
        return {"status": meta_status_upper, "rejection_reason": template.get("reason")}
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de la vérification du statut du template: {e}", exc_info=True)
        return {"status": "PENDING"}


async def cleanup_read_auto_templates():
    """Nettoie les templates auto-créés pour les messages déjà lus"""
    from app.core.db import supabase
    
    try:
        if get_pool():
            rows = await fetch_all(
                """
                SELECT p.message_id, p.template_name
                FROM pending_template_messages p
                INNER JOIN messages m ON m.id = p.message_id
                WHERE m.status = $1
                LIMIT 1000
                """,
                "read",
            )
            auto_templates = [
                {"message_id": r["message_id"], "template_name": r["template_name"]}
                for r in rows
                if (r.get("template_name") or "").startswith("auto_") or (r.get("template_name") or "").startswith("auto_img_")
            ]
        else:
            result = await supabase_execute(
                supabase.table("pending_template_messages")
                .select("message_id, template_name, messages!inner(status)")
                .eq("messages.status", "read")
                .limit(1000)
            )
            if not result.data or len(result.data) == 0:
                return
            auto_templates = [
                row for row in result.data
                if row.get("template_name", "").startswith("auto_") or row.get("template_name", "").startswith("auto_img_")
            ]
        
        if not auto_templates:
            return
        
        logger.info(f"🧹 Nettoyage de {len(auto_templates)} templates auto-créés pour messages déjà lus")
        
        for row in auto_templates:
            try:
                await delete_auto_template_for_message(row["message_id"])
            except Exception as e:
                logger.warning(f"⚠️ Erreur lors du nettoyage du template pour message {row['message_id']}: {e}")
        
    except Exception as e:
        logger.error(f"❌ Erreur lors du nettoyage des templates auto-créés: {e}", exc_info=True)


async def send_pending_template(message_id: str):
    """Envoie un template une fois qu'il est approuvé (message individuel ou campagne broadcast)"""
    lock = await _template_send_lock_for(message_id)
    async with lock:
        await _send_pending_template_unlocked(message_id)


async def _send_pending_template_unlocked(message_id: str):
    """Implémentation réelle de l'envoi ; appeler uniquement via send_pending_template (verrouillé)."""
    from app.core.db import supabase

    logger.info(f"📤 [SEND-TEMPLATE] Début de l'envoi du template pour le message {message_id}")

    # Vérifier d'abord si le message n'a pas déjà été envoyé (éviter les doublons)
    if get_pool():
        msg_check = await fetch_one(
            "SELECT wa_message_id, status FROM messages WHERE id = $1::uuid LIMIT 1",
            message_id,
        )
        if msg_check and msg_check.get("wa_message_id"):
            logger.info(f"✅ [SEND-TEMPLATE] Message {message_id} déjà envoyé (wa_message_id: {msg_check['wa_message_id']}), skip")
            return
    else:
        msg_check_result = await supabase_execute(
            supabase.table("messages")
            .select("wa_message_id, status")
            .eq("id", message_id)
            .limit(1)
        )
        if msg_check_result.data and msg_check_result.data[0].get("wa_message_id"):
            logger.info(f"✅ [SEND-TEMPLATE] Message {message_id} déjà envoyé (wa_message_id: {msg_check_result.data[0]['wa_message_id']}), skip")
            return
    
    pending = None
    if get_pool():
        row = await fetch_one(
            """
            SELECT p.id, p.message_id, p.conversation_id, p.account_id, p.template_name, p.text_content,
                   p.meta_template_id, p.template_status, p.header_media_id, p.campaign_id, p.created_by_user_id,
                   c.client_number, w.phone_number_id, w.access_token
            FROM pending_template_messages p
            INNER JOIN conversations c ON c.id = p.conversation_id
            INNER JOIN whatsapp_accounts w ON w.id = p.account_id
            WHERE p.message_id = $1::uuid AND p.template_status = $2
            LIMIT 1
            """,
            message_id, "APPROVED",
        )
        if row:
            pending = dict(row)
            phone_number_id = pending.get("phone_number_id")
            access_token = pending.get("access_token")
            conversation_info = {"client_number": pending.get("client_number")}
            account_info = {"phone_number_id": phone_number_id, "access_token": access_token}
    else:
        result = await supabase_execute(
            supabase.table("pending_template_messages")
            .select("*, conversations!inner(client_number), whatsapp_accounts!inner(phone_number_id, access_token)")
            .eq("message_id", message_id)
            .eq("template_status", "APPROVED")
            .limit(1)
        )
        if not result.data or len(result.data) == 0:
            logger.warning(f"⚠️ [SEND-TEMPLATE] Aucun template approuvé trouvé pour le message {message_id}")
            return
        pending = result.data[0]
        conversation_info = pending.get("conversations", {})
        if isinstance(conversation_info, list) and len(conversation_info) > 0:
            conversation_info = conversation_info[0]
        account_info = pending.get("whatsapp_accounts", {})
        if isinstance(account_info, list) and len(account_info) > 0:
            account_info = account_info[0]
        phone_number_id = account_info.get("phone_number_id")
        access_token = account_info.get("access_token")
    
    if not pending:
        logger.warning(f"⚠️ [SEND-TEMPLATE] Aucun template approuvé trouvé pour le message {message_id}")
        return
    
    template_name = pending.get("template_name", "inconnu")
    campaign_id = pending.get("campaign_id")
    header_media_id = pending.get("header_media_id")
    
    if not phone_number_id or not access_token:
        logger.error(f"❌ WhatsApp non configuré pour le compte {pending['account_id']}")
        if campaign_id:
            # Marquer tous les destinataires de la campagne comme échoués
            await _mark_campaign_as_failed(campaign_id, "WhatsApp non configuré")
        else:
            await mark_message_as_failed(message_id, "WhatsApp non configuré")
        return
    
    # Si c'est une campagne broadcast, envoyer à tous les destinataires
    if campaign_id:
        logger.info(f"📧 [SEND-TEMPLATE] Template approuvé pour campagne broadcast {campaign_id}, envoi à tous les destinataires")
        await _send_broadcast_template(campaign_id, template_name, phone_number_id, access_token, pending.get("text_content"))
        return
    
    # Sinon, envoi normal pour un message individuel
    conversation_id = pending.get("conversation_id")
    text_content = (pending.get("text_content") or "").strip()
    if not text_content:
        logger.warning(f"⚠️ [SEND-TEMPLATE] Pas de text_content pour le message {message_id}, envoi template")
    else:
        # Fallback: si la fenêtre est redevenue gratuite pendant l'attente, envoyer en gratuit et annuler le template
        from app.services.message_service import is_within_free_window, send_message
        is_free, _ = await is_within_free_window(conversation_id, skip_cache=True)
        if is_free:
            logger.info(f"✅ [SEND-TEMPLATE] Fenêtre gratuite rouverte pour {conversation_id} - envoi en gratuit et annulation du template")
            payload = {
                "conversation_id": conversation_id,
                "content": text_content,
                "existing_message_id": message_id,
            }
            if pending.get("created_by_user_id"):
                payload["sent_by_user_id"] = pending["created_by_user_id"]
            result = await send_message(payload, skip_bot_trigger=True)
            if result.get("error"):
                logger.warning(f"⚠️ [SEND-TEMPLATE] Envoi gratuit échoué: {result.get('error')}, on tente le template")
            else:
                await delete_auto_template_for_message(message_id)
                return

    logger.info(f"📋 [SEND-TEMPLATE] Template à envoyer: {template_name} pour le message {message_id}")

    if _is_template_blacklisted(template_name):
        logger.warning(f"⛔ [SEND-TEMPLATE] Template '{template_name}' blacklisté, re-création pour message {message_id}")
        if get_pool():
            await pg_execute("DELETE FROM pending_template_messages WHERE message_id = $1::uuid", message_id)
        else:
            await supabase_execute(
                supabase.table("pending_template_messages").delete().eq("message_id", message_id)
            )
        try:
            from app.services.template_deduplication import find_or_create_template
            await find_or_create_template(
                conversation_id=conversation_id,
                account_id=pending["account_id"],
                message_id=message_id,
                text_content=text_content or pending.get("text_content", ""),
                campaign_id=campaign_id,
                created_by_user_id=pending.get("created_by_user_id"),
            )
            return
        except Exception as retry_err:
            logger.error(f"❌ [SEND-TEMPLATE] Échec re-création après blacklist pour {message_id}: {retry_err}")
            await mark_message_as_failed(message_id, f"Impossible de créer un nouveau template: {retry_err}")
            return

    to_number = conversation_info.get("client_number")
    
    try:
        logger.info(f"📤 [SEND-TEMPLATE] Envoi du template '{template_name}' vers {to_number} pour le message {message_id}")
        
        # Si c'est un template avec image, inclure l'image dans les components
        components = None
        if header_media_id:
            components = [
                {
                    "type": "HEADER",
                    "format": "IMAGE",
                    "image": {
                        "id": header_media_id
                    }
                }
            ]
            logger.info(f"🖼️ [SEND-TEMPLATE] Template avec image, media_id: {header_media_id}")
        
        # Utiliser la fonction existante pour envoyer le template
        response = await whatsapp_api_service.send_template_message(
            phone_number_id=phone_number_id,
            access_token=access_token,
            to=to_number,
            template_name=template_name,
            language_code="fr",
            components=components  # Inclure l'image si présente
        )
        
        logger.info(f"📥 [SEND-TEMPLATE] Réponse Meta pour le message {message_id}: {response}")
        
        # Mettre à jour le message avec le wa_message_id si disponible
        wa_message_id = response.get("messages", [{}])[0].get("id") if response.get("messages") else None
        if wa_message_id:
            logger.info(f"✅ [SEND-TEMPLATE] Message envoyé avec succès! wa_message_id={wa_message_id} pour le message {message_id}")
            if get_pool():
                await pg_execute(
                    "UPDATE messages SET wa_message_id = $2, status = $3 WHERE id = $1::uuid",
                    message_id, wa_message_id, "sent",
                )
            else:
                await supabase_execute(
                    supabase.table("messages")
                    .update({"wa_message_id": wa_message_id, "status": "sent"})
                    .eq("id", message_id)
                )
        else:
            logger.warning(f"⚠️ [SEND-TEMPLATE] Pas de wa_message_id dans la réponse pour le message {message_id}, mais on marque comme envoyé")
            if get_pool():
                await pg_execute("UPDATE messages SET status = $2 WHERE id = $1::uuid", message_id, "sent")
            else:
                await supabase_execute(
                    supabase.table("messages").update({"status": "sent"}).eq("id", message_id)
                )
        
        logger.info(f"✅ [SEND-TEMPLATE] Template '{template_name}' envoyé avec succès et message {message_id} mis à jour")
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de l'envoi du template pour le message {message_id}: {e}", exc_info=True)
        error_msg = str(e)
        error_code = None
        if hasattr(e, 'response') and hasattr(e.response, 'json'):
            try:
                error_data = e.response.json()
                if 'error' in error_data:
                    error_msg = error_data['error'].get('message', error_msg)
                    error_code = error_data['error'].get('code')
            except Exception:
                pass
        if error_code == 132001:
            _blacklist_template(template_name)
            logger.warning(f"⛔ [SEND-TEMPLATE] Template '{template_name}' supprimé sur Meta, nettoyage et re-création")
            # Delete the stale pending entry so find_or_create_template can create a fresh one
            if get_pool():
                await pg_execute(
                    "DELETE FROM pending_template_messages WHERE message_id = $1::uuid",
                    message_id,
                )
            else:
                await supabase_execute(
                    supabase.table("pending_template_messages").delete().eq("message_id", message_id)
                )
            # Retry: create a new template for this message
            try:
                from app.services.template_deduplication import find_or_create_template
                await find_or_create_template(
                    conversation_id=conversation_id,
                    account_id=pending["account_id"],
                    message_id=message_id,
                    text_content=text_content or pending.get("text_content", ""),
                    campaign_id=campaign_id,
                    created_by_user_id=pending.get("created_by_user_id"),
                )
                logger.info(f"🔄 [SEND-TEMPLATE] Nouveau template créé pour message {message_id} après 132001")
                return
            except Exception as retry_err:
                logger.error(f"❌ [SEND-TEMPLATE] Échec re-création template pour {message_id}: {retry_err}")
        await mark_message_as_failed(message_id, f"Erreur lors de l'envoi: {error_msg}")


async def _send_broadcast_template(
    campaign_id: str,
    template_name: str,
    phone_number_id: str,
    access_token: str,
    text_content: str
):
    """Envoie un template approuvé à tous les destinataires d'une campagne broadcast"""
    from app.core.db import supabase
    from app.services.broadcast_service import get_group_recipients, update_recipient_stat, update_campaign_counters
    
    logger.info(f"📧 [BROADCAST-TEMPLATE] Envoi du template '{template_name}' à tous les destinataires de la campagne {campaign_id}")
    
    campaign = None
    if get_pool():
        campaign = await fetch_one(
            "SELECT group_id, account_id FROM broadcast_campaigns WHERE id = $1::uuid LIMIT 1",
            campaign_id,
        )
    else:
        campaign_result = await supabase_execute(
            supabase.table("broadcast_campaigns")
            .select("group_id, account_id")
            .eq("id", campaign_id)
            .limit(1)
        )
        if campaign_result.data and len(campaign_result.data) > 0:
            campaign = campaign_result.data[0]
    if not campaign:
        logger.error(f"❌ [BROADCAST-TEMPLATE] Campagne {campaign_id} non trouvée")
        return
    
    group_id = campaign["group_id"]
    account_id = campaign["account_id"]
    
    # Récupérer tous les destinataires
    recipients = await get_group_recipients(group_id)
    
    if not recipients:
        logger.warning(f"⚠️ [BROADCAST-TEMPLATE] Aucun destinataire pour la campagne {campaign_id}")
        return
    
    # Récupérer toutes les stats de la campagne
    if get_pool():
        stats_rows = await fetch_all(
            "SELECT id, phone_number, message_id, sent_at FROM broadcast_recipient_stats WHERE campaign_id = $1::uuid",
            campaign_id,
        )
    else:
        stats_result = await supabase_execute(
            supabase.table("broadcast_recipient_stats")
            .select("id, phone_number, message_id, sent_at")
            .eq("campaign_id", campaign_id)
        )
        stats_rows = stats_result.data or []

    stats = {s["phone_number"]: s for s in stats_rows}
    
    if not stats:
        logger.warning(f"⚠️ [BROADCAST-TEMPLATE] Aucune stat trouvée pour la campagne {campaign_id}")
        return

    def _digits_only(p: str) -> str:
        return "".join(c for c in (p or "") if c.isdigit())

    stats_by_digits = {_digits_only(k): v for k, v in stats.items()}

    # Même contact avec formats différents (ex. "06 …" vs "336…") : clé unique = normalize_phone_number
    stats_by_normalized: Dict[str, Any] = {}
    for s in stats_rows:
        raw = s.get("phone_number") or ""
        n = normalize_phone_number(raw)
        if n:
            stats_by_normalized[n] = s

    def _resolve_recipient_stat(raw_phone: str):
        """Aligne groupe / stats sur le même format (ex. FR national 06… vs international 33…)."""
        if stats.get(raw_phone):
            return stats[raw_phone]
        d = _digits_only(raw_phone)
        if d and stats_by_digits.get(d):
            return stats_by_digits[d]
        n = normalize_phone_number(raw_phone or "")
        if n and stats_by_normalized.get(n):
            return stats_by_normalized[n]
        return None

    sent_count = 0
    failed_count = 0
    
    for recipient in recipients:
        phone_number = recipient["phone_number"]
        stat = _resolve_recipient_stat(phone_number)
        
        if not stat:
            logger.warning(f"⚠️ [BROADCAST-TEMPLATE] Pas de stat trouvée pour {phone_number}")
            continue
        
        # Dans le cas mix, les gratuits ont déjà reçu leur message normalement et ont un sent_at
        # On ne doit envoyer le template qu'aux payants qui n'ont pas encore de sent_at
        if stat.get("sent_at"):
            logger.info(f"⏭️ [BROADCAST-TEMPLATE] Destinataire {phone_number} a déjà reçu le message (sent_at={stat.get('sent_at')}), skip")
            continue
        
        if _is_template_blacklisted(template_name):
            logger.warning(f"⛔ [BROADCAST-TEMPLATE] Template '{template_name}' blacklisté, skip {phone_number}")
            failed_count += 1
            await update_recipient_stat(stat["id"], {
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "error_message": f"Template '{template_name}' n'existe pas sur Meta (132001)"
            })
            continue

        try:
            # Meta attend le numéro en format international sans + ; aligné sur normalize_phone_number
            to_whatsapp = normalize_phone_number(phone_number) or phone_number
            response = await whatsapp_api_service.send_template_message(
                phone_number_id=phone_number_id,
                access_token=access_token,
                to=to_whatsapp,
                template_name=template_name,
                language_code="fr",
                components=None,
            )
            
            wa_message_id = response.get("messages", [{}])[0].get("id") if response.get("messages") else None
            timestamp_iso = datetime.now(timezone.utc).isoformat()
            
            if stat.get("message_id"):
                if get_pool():
                    from app.services.message_service import _parse_timestamp_iso
                    await pg_execute(
                        "UPDATE messages SET wa_message_id = $2, status = $3, timestamp = $4::timestamptz WHERE id = $1::uuid",
                        stat["message_id"], wa_message_id, "sent", _parse_timestamp_iso(timestamp_iso),
                    )
                else:
                    await supabase_execute(
                        supabase.table("messages")
                        .update({
                            "wa_message_id": wa_message_id,
                            "status": "sent",
                            "timestamp": timestamp_iso
                        })
                        .eq("id", stat["message_id"])
                    )
            
            await update_recipient_stat(stat["id"], {
                "sent_at": timestamp_iso,
            })
            
            sent_count += 1
            logger.info(f"✅ [BROADCAST-TEMPLATE] Template envoyé à {phone_number} (wa_message_id: {wa_message_id})")
            
        except Exception as e:
            logger.error(f"❌ [BROADCAST-TEMPLATE] Erreur lors de l'envoi à {phone_number}: {e}", exc_info=True)
            failed_count += 1
            error_code = None
            if hasattr(e, 'response') and hasattr(e.response, 'json'):
                try:
                    error_code = e.response.json().get('error', {}).get('code')
                except Exception:
                    pass
            if error_code == 132001:
                _blacklist_template(template_name)
                logger.warning(f"⛔ [BROADCAST-TEMPLATE] Template '{template_name}' blacklisté (132001), skip reste campagne")
            
            await update_recipient_stat(stat["id"], {
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "error_message": str(e)
            })
    
    # Mettre à jour les compteurs de la campagne
    await update_campaign_counters(campaign_id)
    
    logger.info(f"✅ [BROADCAST-TEMPLATE] Campagne {campaign_id} terminée: {sent_count} envoyés, {failed_count} échoués")


async def _mark_campaign_as_failed(campaign_id: str, error_message: str):
    """Marque tous les destinataires payants d'une campagne comme échoués (ceux qui attendaient le template)"""
    from app.core.db import supabase
    from app.services.broadcast_service import update_recipient_stat, update_campaign_counters
    
    stats_list = []
    if get_pool():
        stats_list = await fetch_all(
            "SELECT id FROM broadcast_recipient_stats WHERE campaign_id = $1::uuid AND sent_at IS NULL",
            campaign_id,
        )
    else:
        stats_result = await supabase_execute(
            supabase.table("broadcast_recipient_stats")
            .select("id")
            .eq("campaign_id", campaign_id)
            .is_("sent_at", "null")
        )
        stats_list = stats_result.data or []
    
    if stats_list:
        for stat in stats_list:
            await update_recipient_stat(stat["id"], {
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "error_message": error_message
            })
        
        await update_campaign_counters(campaign_id)


async def mark_message_as_failed(message_id: str, error_message: str):
    """Marque un message comme échoué dans la base"""
    from app.core.db import supabase
    if get_pool():
        await pg_execute(
            "UPDATE messages SET status = $2, error_message = $3 WHERE id = $1::uuid",
            message_id, "failed", error_message,
        )
    else:
        await supabase_execute(
            supabase.table("messages")
            .update({"status": "failed", "error_message": error_message})
            .eq("id", message_id)
        )
    logger.info(f"❌ Message {message_id} marqué comme échoué: {error_message}")


async def delete_auto_template_for_message(message_id: str):
    """Supprime le template auto-créé associé à un message une fois qu'il est lu"""
    from app.core.db import supabase
    
    try:
        pending = None
        if get_pool():
            row = await fetch_one(
                """
                SELECT p.id, p.message_id, p.template_name, w.waba_id, w.access_token
                FROM pending_template_messages p
                INNER JOIN whatsapp_accounts w ON w.id = p.account_id
                WHERE p.message_id = $1::uuid
                LIMIT 1
                """,
                message_id,
            )
            if row:
                pending = dict(row)
        else:
            result = await supabase_execute(
                supabase.table("pending_template_messages")
                .select("*, whatsapp_accounts!inner(waba_id, access_token)")
                .eq("message_id", message_id)
                .limit(1)
            )
            if not result.data or len(result.data) == 0:
                return
            pending = result.data[0]
            account_info = pending.get("whatsapp_accounts", {})
            if isinstance(account_info, list) and len(account_info) > 0:
                account_info = account_info[0]
            elif not isinstance(account_info, dict):
                account_info = {}
            pending["waba_id"] = account_info.get("waba_id")
            pending["access_token"] = account_info.get("access_token")
        
        if not pending:
            return
        
        template_name = pending["template_name"]
        
        # Vérifier que c'est bien un template auto-créé (commence par "auto_" ou "auto_img_")
        if not (template_name.startswith("auto_") or template_name.startswith("auto_img_")):
            logger.info(f"ℹ️ Template {template_name} n'est pas un template auto-créé, pas de suppression")
            return
        
        waba_id = pending["waba_id"]
        access_token = pending["access_token"]
        
        if not waba_id or not access_token:
            logger.warning(f"⚠️ Impossible de supprimer le template {template_name}: waba_id ou access_token manquant")
            return
        
        logger.info(f"🗑️ Suppression du template auto-créé '{template_name}' pour le message {message_id}")
        
        # Supprimer le template via l'API Meta
        try:
            await whatsapp_api_service.delete_message_template(
                waba_id=waba_id,
                access_token=access_token,
                name=template_name
            )
            logger.info(f"✅ Template '{template_name}' supprimé avec succès de Meta")
        except Exception as e:
            logger.warning(f"⚠️ Erreur lors de la suppression du template '{template_name}' depuis Meta: {e}")
            # Continuer quand même pour supprimer l'entrée en base
        
        # Blacklist the template so other messages using the same name will
        # detect it and silently re-create a new template instead of failing.
        _blacklist_template(template_name)

        if get_pool():
            await pg_execute("DELETE FROM pending_template_messages WHERE message_id = $1::uuid", message_id)
        else:
            from app.core.db import supabase
            await supabase_execute(
                supabase.table("pending_template_messages").delete().eq("message_id", message_id)
            )

        logger.info(f"✅ Template '{template_name}' supprimé de Meta et blacklisté, entrée pending du message {message_id} supprimée")
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de la suppression du template auto-créé pour le message {message_id}: {e}", exc_info=True)


def _coerce_created_at(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        try:
            d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    return None


def _pending_template_too_old(created_at_raw: Any) -> bool:
    created = _coerce_created_at(created_at_raw)
    if not created:
        return False
    return datetime.now(timezone.utc) - created > timedelta(days=TEMPLATE_ASYNC_MAX_POLL_DAYS)


async def abandon_stale_pending_template(message_id: str, reason: str) -> None:
    """
    Marque le message outbound en échec (si toujours bloqué sans wa_message_id),
    supprime l'entrée pending et tente de retirer le template auto sur Meta.
    """
    from app.core.db import supabase

    async def _delete_pending_row() -> None:
        if get_pool():
            await pg_execute(
                "DELETE FROM pending_template_messages WHERE message_id = $1::uuid",
                message_id,
            )
        else:
            await supabase_execute(
                supabase.table("pending_template_messages").delete().eq("message_id", message_id)
            )

    msg = None
    if get_pool():
        msg = await fetch_one(
            "SELECT wa_message_id, status FROM messages WHERE id = $1::uuid LIMIT 1",
            message_id,
        )
    else:
        mr = await supabase_execute(
            supabase.table("messages")
            .select("wa_message_id, status")
            .eq("id", message_id)
            .limit(1)
        )
        if mr.data:
            msg = mr.data[0]

    if not msg:
        logger.warning("⚠️ [ABANDON-TEMPLATE] Message %s introuvable - nettoyage pending", message_id)
        await _delete_pending_row()
        logger.info("🛑 [ABANDON-TEMPLATE] %s - %s", message_id, reason)
        return

    if msg.get("wa_message_id"):
        logger.info(
            "ℹ️ [ABANDON-TEMPLATE] Message %s déjà envoyé (wa_message_id présent), nettoyage pending",
            message_id,
        )
        await _delete_pending_row()
        return

    st = (msg.get("status") or "").lower()
    if st in ("sent", "delivered", "read"):
        logger.info(
            "ℹ️ [ABANDON-TEMPLATE] Message %s au statut %s - nettoyage pending seulement",
            message_id,
            st,
        )
        await _delete_pending_row()
        return

    if st != "failed":
        await mark_message_as_failed(message_id, reason)

    try:
        await delete_auto_template_for_message(message_id)
    except Exception as e:
        logger.warning(
            "⚠️ [ABANDON-TEMPLATE] delete_auto_template_for_message %s: %s",
            message_id,
            e,
        )

    await _delete_pending_row()
    logger.info("🛑 [ABANDON-TEMPLATE] Message %s - %s", message_id, reason)


async def resume_pending_templates_on_startup():
    """
    Reprend les templates en attente au démarrage du backend.
    - Templates APPROVED : envoie immédiatement
    - Templates PENDING : relance la vérification
    """
    logger.info("=" * 80)
    logger.info("🔄 [STARTUP] Reprise des templates en attente...")
    
    try:
        # Reprendre les entrées récentes (même fenêtre que le polling max) + marge
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=TEMPLATE_ASYNC_MAX_POLL_DAYS + 2)
        if cutoff_time.tzinfo is None:
            cutoff_time = cutoff_time.replace(tzinfo=timezone.utc)

        if get_pool():
            rows = await fetch_all(
                """
                SELECT p.message_id, p.template_status, p.template_name, p.created_at, m.wa_message_id
                FROM pending_template_messages p
                INNER JOIN messages m ON m.id = p.message_id
                WHERE p.template_status IN ('APPROVED', 'PENDING')
                  AND p.created_at > $1::timestamptz
                  AND m.wa_message_id IS NULL
                ORDER BY p.created_at ASC
                """,
                cutoff_time,
            )
            pending_templates = [dict(r) for r in rows]
        else:
            result = await supabase_execute(
                supabase.table("pending_template_messages")
                .select("message_id, template_status, template_name, created_at, messages!inner(wa_message_id)")
                .in_("template_status", ["APPROVED", "PENDING"])
                .gte("created_at", cutoff_time.isoformat())
                .is_("messages.wa_message_id", "null")
                .order("created_at")
            )
            pending_templates = result.data or []

        if not pending_templates:
            logger.info("✅ [STARTUP] Aucun template en attente à reprendre")
            return

        logger.info(f"📋 [STARTUP] {len(pending_templates)} template(s) en attente trouvé(s)")

        approved_count = 0
        pending_count = 0

        for template in pending_templates:
            message_id = template["message_id"]
            status = template["template_status"]
            template_name = template["template_name"]

            if _pending_template_too_old(template.get("created_at")):
                logger.warning(
                    "⏰ [STARTUP] Template %s (message %s) trop ancien (> %s jours) - abandon",
                    template_name,
                    message_id,
                    TEMPLATE_ASYNC_MAX_POLL_DAYS,
                )
                await abandon_stale_pending_template(
                    message_id,
                    f"File d'attente template expirée (>{TEMPLATE_ASYNC_MAX_POLL_DAYS} jours).",
                )
                continue

            if status == "APPROVED":
                # Template déjà approuvé, envoyer immédiatement
                logger.info(f"✅ [STARTUP] Template APPROVED trouvé: {template_name} (message {message_id}), envoi...")
                try:
                    await send_pending_template(message_id)
                    approved_count += 1
                except Exception as e:
                    logger.error(f"❌ [STARTUP] Erreur lors de l'envoi du template {template_name}: {e}")
            
            elif status == "PENDING":
                # Template en attente, relancer la vérification
                logger.info(f"⏳ [STARTUP] Template PENDING trouvé: {template_name} (message {message_id}), vérification...")
                try:
                    result = await check_and_update_template_status(message_id)
                    rs = result.get("status")
                    if rs == "APPROVED":
                        await send_pending_template(message_id)
                        approved_count += 1
                    elif rs == "NOT_FOUND":
                        await abandon_stale_pending_template(
                            message_id,
                            "Suivi template introuvable (entrée supprimée ou incohérente).",
                        )
                    else:
                        schedule_check_template_status_async(message_id)
                        pending_count += 1
                except Exception as e:
                    logger.error(f"❌ [STARTUP] Erreur lors de la vérification du template {template_name}: {e}")
        
        logger.info(f"✅ [STARTUP] Reprise terminée: {approved_count} envoyé(s), {pending_count} en attente de validation")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ [STARTUP] Erreur lors de la reprise des templates: {e}", exc_info=True)


async def periodic_template_check():
    """
    Tâche périodique pour vérifier les templates en attente toutes les 5 minutes.
    Utile si le backend a été coupé ou si des vérifications ont échoué.
    """
    logger.info("🔄 [PERIODIC] Démarrage de la vérification périodique des templates en attente")
    
    while True:
        try:
            await asyncio.sleep(TEMPLATE_ASYNC_POLL_INTERVAL_SEC)

            logger.info("🔍 [PERIODIC] Vérification des templates en attente...")

            cutoff_time = datetime.now(timezone.utc) - timedelta(days=TEMPLATE_ASYNC_MAX_POLL_DAYS + 2)
            if cutoff_time.tzinfo is None:
                cutoff_time = cutoff_time.replace(tzinfo=timezone.utc)

            if get_pool():
                rows = await fetch_all(
                    """
                    SELECT p.message_id, p.template_status, p.template_name, p.created_at
                    FROM pending_template_messages p
                    INNER JOIN messages m ON m.id = p.message_id
                    WHERE p.template_status IN ('APPROVED', 'PENDING')
                      AND p.created_at > $1::timestamptz
                      AND m.wa_message_id IS NULL
                    """,
                    cutoff_time,
                )
                pending_templates = [dict(r) for r in rows]
            else:
                result = await supabase_execute(
                    supabase.table("pending_template_messages")
                    .select(
                        "message_id, template_status, template_name, created_at, messages!inner(wa_message_id)"
                    )
                    .in_("template_status", ["APPROVED", "PENDING"])
                    .gte("created_at", cutoff_time.isoformat())
                    .is_("messages.wa_message_id", "null")
                )
                pending_templates = result.data or []

            if not pending_templates:
                logger.debug("✅ [PERIODIC] Aucun template en attente")
                continue

            logger.info(f"📋 [PERIODIC] {len(pending_templates)} template(s) en attente")

            for template in pending_templates:
                message_id = template["message_id"]
                status = template["template_status"]

                if _pending_template_too_old(template.get("created_at")):
                    logger.warning(
                        "⏰ [PERIODIC] Message %s - entrée template trop ancienne (> %s jours), abandon",
                        message_id,
                        TEMPLATE_ASYNC_MAX_POLL_DAYS,
                    )
                    await abandon_stale_pending_template(
                        message_id,
                        f"File d'attente template expirée (>{TEMPLATE_ASYNC_MAX_POLL_DAYS} jours).",
                    )
                    continue

                if status == "APPROVED":
                    # Template approuvé mais pas encore envoyé, envoyer maintenant
                    try:
                        await send_pending_template(message_id)
                    except Exception as e:
                        logger.error(f"❌ [PERIODIC] Erreur envoi template {message_id}: {e}")
                
                elif status == "PENDING":
                    # Vérifier le statut auprès de Meta
                    try:
                        result = await check_and_update_template_status(message_id)
                        rs = result.get("status")
                        if rs == "APPROVED":
                            await send_pending_template(message_id)
                        elif rs == "NOT_FOUND":
                            await abandon_stale_pending_template(
                                message_id,
                                "Suivi template introuvable (entrée supprimée ou incohérente).",
                            )
                    except Exception as e:
                        logger.error(f"❌ [PERIODIC] Erreur vérification template {message_id}: {e}")
        
        except asyncio.CancelledError:
            logger.info("🛑 [PERIODIC] Arrêt de la vérification périodique des templates")
            break
        except Exception as e:
            logger.error(f"❌ [PERIODIC] Erreur dans la vérification périodique: {e}", exc_info=True)
            # Continuer malgré l'erreur

