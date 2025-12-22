import logging
import sys
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.auth import get_current_user

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
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.account_service import get_account_by_id
from app.services.conversation_service import get_conversation_by_id
from app.services.message_service import (
    add_reaction,
    fetch_message_media_content,
    get_message_by_id,
    get_messages,
    _download_and_store_media_async,
    remove_reaction,
    send_message,
    send_free_message,
    send_message_with_template_fallback,
    is_within_free_window,
    calculate_message_price,
    send_media_message_with_storage,
    send_interactive_message_with_storage,
    send_reaction_to_whatsapp,
    update_message_content,
    delete_message_scope,
)
from app.services import whatsapp_api_service
from app.services.whatsapp_api_service import check_phone_number_has_whatsapp

router = APIRouter()


@router.get("/{conversation_id}")
async def fetch_messages(
    conversation_id: str,
    limit: int = Query(100, ge=1, le=500, description="Nombre max de messages"),
    before: str | None = Query(
        None, description="ISO timestamp: renvoie les messages avant cette date"
    ),
    current_user: CurrentUser = Depends(get_current_user),
):
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])
    return await get_messages(conversation_id, limit=limit, before=before)


@router.get("/media/{message_id}")
async def fetch_message_media(
    message_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    message = await get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message_not_found")

    conversation = await get_conversation_by_id(message["conversation_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])
    
    account = await get_account_by_id(conversation["account_id"])
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")

    # Vérifier d'abord si le média est stocké dans Supabase Storage
    storage_url = message.get("storage_url")
    if storage_url:
        # Rediriger vers l'URL Supabase Storage (plus fiable que de servir le blob)
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=storage_url, status_code=302)
    
    # Sinon, essayer de récupérer depuis WhatsApp
    try:
        content, mime_type, filename = await fetch_message_media_content(message, account)
    except ValueError as exc:
        error_detail = str(exc)
        # Si le média est expiré ou invalide, retourner 410 Gone au lieu de 400
        if error_detail in ("media_expired_or_invalid", "media_not_found"):
            raise HTTPException(status_code=410, detail=error_detail)
        raise HTTPException(status_code=400, detail=error_detail)

    headers = {}
    if filename:
        headers["Content-Disposition"] = f'inline; filename="{filename}"'

    return StreamingResponse(iter([content]), media_type=mime_type, headers=headers)


@router.post("/send")
async def send_api_message(payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    """
    Envoie un message WhatsApp. 
    - Si dans la fenêtre gratuite de 24h : envoie un message conversationnel gratuit
    - Si hors fenêtre : utilise automatiquement un template UTILITY (payant mais fonctionne sans erreur)
    """
    print(f"📤 [SEND DEBUG] POST /messages/send called: conversation_id={payload.get('conversation_id')}, content_length={len(payload.get('content', '') or '')}")
    logger.info(f"📤 [SEND DEBUG] POST /messages/send called: conversation_id={payload.get('conversation_id')}, content_length={len(payload.get('content', '') or '')}")
    conversation_id = payload.get("conversation_id")
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id_required")
    conversation = await get_conversation_by_id(conversation_id)
    print(f"📤 [SEND DEBUG] Conversation found: {conversation is not None}, bot_enabled: {conversation.get('bot_enabled') if conversation else None}")
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    
    # Vérifier que l'utilisateur a accès au compte (pas en 'aucun' et pas en 'lecture' seule)
    access_level = current_user.permissions.account_access_levels.get(conversation["account_id"])
    if access_level == "aucun":
        raise HTTPException(status_code=403, detail="account_access_denied")
    if access_level == "lecture":
        raise HTTPException(status_code=403, detail="write_access_denied")
    
    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])
    
    # Envoyer le message normalement (force_send=True pour toujours envoyer, même hors fenêtre)
    # WhatsApp facturera automatiquement si hors fenêtre
    result = await send_message(payload, force_send=True)
    
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result.get("message", result.get("error")))
    
    return result


@router.post("/send-free")
async def send_free_api_message(payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    """
    Envoie un message WhatsApp uniquement si on est dans la fenêtre gratuite de 24h.
    
    Cette fonction vérifie automatiquement si le dernier message entrant date de moins de 24h.
    Si oui, le message est envoyé gratuitement. Sinon, une erreur est retournée indiquant
    qu'un template de message est nécessaire.
    
    Payload:
    {
        "conversation_id": "uuid",
        "content": "Texte du message"
    }
    """
    conversation_id = payload.get("conversation_id")
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id_required")
    
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    
    # Vérifier que l'utilisateur a accès au compte
    access_level = current_user.permissions.account_access_levels.get(conversation["account_id"])
    if access_level == "aucun":
        raise HTTPException(status_code=403, detail="account_access_denied")
    if access_level == "lecture":
        raise HTTPException(status_code=403, detail="write_access_denied")
    
    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])
    
    result = await send_free_message(payload)
    
    # Si erreur de fenêtre expirée, retourner 400 avec détails
    if result.get("error") == "free_window_expired":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "free_window_expired",
                "message": result.get("message"),
                "last_inbound_time": result.get("last_inbound_time"),
                "requires_template": True
            }
        )
    
    # Autres erreurs
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result.get("message", result.get("error")))
    
    return result


@router.get("/free-window/{conversation_id}")
async def check_free_window(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Vérifie si on est dans la fenêtre gratuite de 24h pour une conversation.
    
    Returns:
    {
        "is_free": true/false,
        "last_inbound_time": "2024-01-01T12:00:00Z" ou null,
        "hours_elapsed": 12.5 (si hors fenêtre),
        "hours_remaining": 11.5 (si dans fenêtre)
    }
    """
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    
    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])
    
    is_free, last_inbound_time = await is_within_free_window(conversation_id)
    
    result = {
        "is_free": is_free,
        "last_inbound_time": last_inbound_time.isoformat() if last_inbound_time else None
    }
    
    if last_inbound_time:
        now = datetime.now(timezone.utc)
        hours_elapsed = (now - last_inbound_time).total_seconds() / 3600
        result["hours_elapsed"] = round(hours_elapsed, 2)
        
        if is_free:
            result["hours_remaining"] = round(24.0 - hours_elapsed, 2)
        else:
            result["hours_remaining"] = 0
    
    return result


@router.get("/price/{conversation_id}")
async def get_message_price(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Calcule le prix d'un message pour une conversation.
    L'assistance classique 24h est gratuite (dans la fenêtre de 24h).
    Hors fenêtre, utilise un message conversationnel normal (0,0248 €).
    
    Returns:
    {
        "is_free": true/false,
        "price_usd": 0.0248 (ou 0.0 si gratuit),
        "price_eur": 0.0248 (ou 0.0 si gratuit),
        "currency": "USD",
        "category": "free" ou "conversational",
        "last_inbound_time": "2024-01-01T12:00:00Z" ou null
    }
    """
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    
    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])
    
    # Calculer le prix avec message conversationnel (pas de template)
    price_info = await calculate_message_price(conversation_id, use_conversational=True)
    return price_info


@router.get("/templates/{conversation_id}")
async def get_available_templates(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Récupère la liste des templates disponibles pour une conversation.
    Retourne les templates UTILITY, MARKETING et AUTHENTICATION approuvés.
    """
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    
    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])
    
    account = await get_account_by_id(conversation["account_id"])
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    waba_id = account.get("waba_id")
    access_token = account.get("access_token")
    phone_number_id = account.get("phone_number_id")
    
    # Si waba_id n'est pas configuré, essayer de le récupérer depuis phone_number_id
    if not waba_id and phone_number_id and access_token:
        try:
            from app.services.whatsapp_api_service import get_phone_number_details
            phone_details = await get_phone_number_details(phone_number_id, access_token)
            waba_id = phone_details.get("waba_id") or phone_details.get("whatsapp_business_account_id")
            
            # Sauvegarder le waba_id dans le compte si trouvé
            if waba_id:
                from app.core.db import supabase_execute, supabase
                await supabase_execute(
                    supabase.table("whatsapp_accounts")
                    .update({"waba_id": waba_id})
                    .eq("id", account["id"])
                )
                account["waba_id"] = waba_id
                logger.info(f"✅ WABA ID récupéré et sauvegardé pour le compte {account.get('name')}: {waba_id}")
        except Exception as e:
            logger.warning(f"⚠️ Impossible de récupérer le WABA ID depuis phone_number_id: {e}")
    
    if not access_token:
        raise HTTPException(
            status_code=400, 
            detail="account_not_configured: access_token is missing. Please configure the WhatsApp account."
        )
    
    if not waba_id:
        raise HTTPException(
            status_code=400, 
            detail="account_not_configured: waba_id is missing. Please configure the WhatsApp Business Account ID in the account settings."
        )
    
    try:
        # Récupérer tous les templates avec pagination
        all_templates = []
        after = None
        limit = 100
        
        while True:
            templates_result = await whatsapp_api_service.list_message_templates(
                waba_id=waba_id,
                access_token=access_token,
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
        
        # Filtrer uniquement les templates UTILITY approuvés
        templates = all_templates
        
        def get_template_price(category):
            """Retourne le prix d'un template selon sa catégorie (prix Meta officiels)"""
            # Prix selon la documentation Meta WhatsApp Business API
            # https://developers.facebook.com/docs/whatsapp/pricing
            prices = {
                "UTILITY": {"usd": 0.0248, "eur": 0.0248},  # 0,0248 €
                "MARKETING": {"usd": 0.1186, "eur": 0.1186},  # 0,1186 €
                "AUTHENTICATION": {"usd": 0.0248, "eur": 0.0248},  # 0,0248 €
            }
            # Normaliser la catégorie en majuscules pour la recherche
            category_upper = (category or "").upper()
            return prices.get(category_upper, {"usd": 0.0248, "eur": 0.0248})
        
        approved_templates = []
        for t in templates:
            # Comparaison insensible à la casse pour le statut et la catégorie
            status = (t.get("status") or "").upper()
            category = (t.get("category") or "").upper()
            template_name = (t.get("name") or "").lower()
            
            # Exclure le template hello_world / hello-world
            if template_name in ["hello_world", "hello-world"]:
                continue
            
            # Filtrer les templates approuvés en catégorie UTILITY, MARKETING ou AUTHENTICATION
            if status == "APPROVED" and category in ["UTILITY", "MARKETING", "AUTHENTICATION"]:
                price = get_template_price(category)
                
                # Détecter si le template a un HEADER avec média (IMAGE, VIDEO, DOCUMENT)
                template_components = t.get("components", [])
                header_component = next(
                    (c for c in template_components if c.get("type") == "HEADER"),
                    None
                )
                
                header_media_url = None
                header_media_type = None
                
                if header_component:
                    header_format = header_component.get("format")
                    if header_format in ["IMAGE", "VIDEO", "DOCUMENT"]:
                        # Extraire l'URL de l'image depuis example.header_handle
                        example = header_component.get("example", {})
                        header_handle = example.get("header_handle", [])
                        example_url = header_handle[0] if isinstance(header_handle, list) and len(header_handle) > 0 else None
                        
                        # Vérifier si l'image existe déjà en base
                        try:
                            from app.services.storage_service import get_template_media_url, download_and_store_template_media
                            header_media_url = await get_template_media_url(
                                template_name=t.get("name"),
                                template_language=t.get("language", "fr"),
                                account_id=account["id"],
                                media_type=header_format
                            )
                            
                            # Si l'image n'existe pas encore mais qu'on a une URL d'exemple, la télécharger automatiquement
                            if not header_media_url and example_url:
                                try:
                                    logger.info(f"  📥 Téléchargement automatique de l'image pour template {t.get('name')}")
                                    # Détecter le content-type depuis l'URL
                                    import httpx
                                    async with httpx.AsyncClient(timeout=10.0) as client:
                                        head_response = await client.head(example_url)
                                        content_type = head_response.headers.get("content-type", "image/jpeg")
                                    
                                    # Télécharger et stocker le média
                                    header_media_url = await download_and_store_template_media(
                                        template_name=t.get("name"),
                                        template_language=t.get("language", "fr"),
                                        account_id=account["id"],
                                        media_url=example_url,
                                        media_type=header_format,
                                        content_type=content_type
                                    )
                                    if header_media_url:
                                        logger.info(f"  ✅ Image téléchargée et stockée pour template {t.get('name')}: {header_media_url}")
                                except Exception as download_error:
                                    logger.warning(f"  ⚠️  Erreur lors du téléchargement de l'image pour template {t.get('name')}: {download_error}")
                                    # Utiliser l'URL d'exemple directement en fallback
                                    header_media_url = example_url
                            
                            # Si toujours pas d'URL mais qu'on a une URL d'exemple, l'utiliser directement
                            if not header_media_url and example_url:
                                header_media_url = example_url
                                logger.info(f"  📷 Utilisation de l'URL d'exemple pour template {t.get('name')}")
                            
                            header_media_type = header_format
                        except Exception as media_error:
                            # Si la table n'existe pas encore ou autre erreur, utiliser l'URL d'exemple si disponible
                            logger.warning(f"  ⚠️  Erreur lors de la récupération du média pour template {t.get('name')}: {media_error}")
                            if example_url:
                                header_media_url = example_url
                                header_media_type = header_format
                            else:
                                header_media_url = None
                                header_media_type = None
                
                template_data = {
                    "name": t.get("name"),
                    "status": t.get("status"),
                    "category": t.get("category"),
                    "language": t.get("language"),
                    "components": template_components,
                    "price_usd": price["usd"],
                    "price_eur": price["eur"]
                }
                
                # Ajouter l'URL du média si disponible
                if header_media_url:
                    template_data["header_media_url"] = header_media_url
                    template_data["header_media_type"] = header_media_type
                
                approved_templates.append(template_data)
        
        return {
            "templates": approved_templates
        }
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error fetching templates: {error_msg}", exc_info=True)
        # Retourner un message d'erreur plus détaillé
        raise HTTPException(
            status_code=400, 
            detail=f"Error fetching templates: {error_msg}. Check backend logs for details."
        )


@router.post("/templates/{conversation_id}/download-media")
async def download_template_media(
    conversation_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Télécharge et stocke l'image d'un template depuis une URL.
    
    Payload:
    {
        "template_name": "nom_du_template",
        "template_language": "fr",
        "media_url": "https://example.com/image.jpg",
        "media_type": "IMAGE"  # ou "VIDEO", "DOCUMENT"
    }
    """
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    
    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])
    
    account = await get_account_by_id(conversation["account_id"])
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    template_name = payload.get("template_name")
    template_language = payload.get("template_language", "fr")
    media_url = payload.get("media_url")
    media_type = payload.get("media_type", "IMAGE")
    
    if not template_name or not media_url:
        raise HTTPException(status_code=400, detail="template_name and media_url are required")
    
    if media_type not in ["IMAGE", "VIDEO", "DOCUMENT"]:
        raise HTTPException(status_code=400, detail="media_type must be IMAGE, VIDEO, or DOCUMENT")
    
    try:
        from app.services.storage_service import download_and_store_template_media
        import httpx
        
        # Détecter le content-type depuis l'URL
        async with httpx.AsyncClient(timeout=10.0) as client:
            head_response = await client.head(media_url)
            content_type = head_response.headers.get("content-type", "image/jpeg")
        
        # Télécharger et stocker le média
        storage_url = await download_and_store_template_media(
            template_name=template_name,
            template_language=template_language,
            account_id=account["id"],
            media_url=media_url,
            media_type=media_type,
            content_type=content_type
        )
        
        if not storage_url:
            raise HTTPException(status_code=500, detail="Failed to download and store template media")
        
        return {
            "status": "success",
            "storage_url": storage_url,
            "template_name": template_name,
            "template_language": template_language,
            "media_type": media_type
        }
    except Exception as e:
        logger.error(f"Error downloading template media: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/send-template/{conversation_id}")
async def send_template_message_api(
    conversation_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Envoie un message via template pour une conversation.
    
    Payload:
    {
        "template_name": "nom_du_template",
        "components": [{"type": "BODY", "text": "votre texte"}]
    }
    """
    # Logs au tout début pour être sûr qu'on arrive ici
    import sys
    print("=" * 80, file=sys.stderr)
    print(f"🚀🚀🚀 [TEMPLATE SEND] FONCTION APPELÉE - conversation_id={conversation_id}", file=sys.stderr)
    print(f"🚀🚀🚀 [TEMPLATE SEND] payload={payload}", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    sys.stderr.flush()
    
    print(f"🚀 [TEMPLATE SEND] Début - conversation_id={conversation_id}, payload={payload}")
    logger.info(f"🚀 [TEMPLATE SEND] Début - conversation_id={conversation_id}, payload={payload}")
    
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        print(f"❌ [TEMPLATE SEND] Conversation non trouvée: {conversation_id}")
        raise HTTPException(status_code=404, detail="conversation_not_found")
    
    print(f"✅ [TEMPLATE SEND] Conversation trouvée: {conversation.get('id')}")
    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])
    
    template_name = payload.get("template_name")
    components = payload.get("components")  # Optionnel, peut être None
    language_code = payload.get("language_code", "fr")  # Par défaut "fr", mais peut être spécifié
    
    print(f"📋 [TEMPLATE SEND] Template name: {template_name}, language: {language_code}")
    
    if not template_name:
        print(f"❌ [TEMPLATE SEND] template_name manquant")
        raise HTTPException(status_code=400, detail="template_name_required")
    
    account = await get_account_by_id(conversation["account_id"])
    if not account:
        print(f"❌ [TEMPLATE SEND] Account non trouvé: {conversation['account_id']}")
        raise HTTPException(status_code=404, detail="account_not_found")
    
    phone_id = account.get("phone_number_id")
    token = account.get("access_token")
    to_number = conversation["client_number"]
    
    print(f"📱 [TEMPLATE SEND] Account: {account.get('name')}, phone_id: {phone_id}, to: {to_number}")
    
    if not phone_id or not token:
        print(f"❌ [TEMPLATE SEND] WhatsApp non configuré - phone_id: {phone_id}, token: {'présent' if token else 'absent'}")
        raise HTTPException(status_code=400, detail="whatsapp_not_configured")
    
    try:
        print(f"🔍 [TEMPLATE SEND] Début de la récupération des détails du template...")
        # Récupérer les détails du template pour vérifier s'il a un header avec format
        waba_id = account.get("waba_id")
        template_details = None
        if waba_id:
            try:
                # Récupérer tous les templates avec pagination pour être sûr de trouver le bon
                all_templates = []
                after = None
                limit = 100
                
                while True:
                    templates_result = await whatsapp_api_service.list_message_templates(
                        waba_id=waba_id,
                        access_token=token,
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
                
                # Chercher le template par nom (la langue peut varier, on cherche d'abord avec la langue exacte, puis sans)
                template_details = next(
                    (t for t in all_templates if t.get("name") == template_name and t.get("language") == language_code),
                    None
                )
                
                # Si pas trouvé avec la langue exacte, chercher juste par nom
                if not template_details:
                    template_details = next(
                        (t for t in all_templates if t.get("name") == template_name),
                        None
                    )
                    if template_details:
                        logger.info(f"  Template trouvé avec une langue différente: {template_details.get('language')} au lieu de {language_code}")
                
                if template_details:
                    logger.info(f"  ✅ Template trouvé: {template_details.get('name')}, language: {template_details.get('language')}")
                else:
                    logger.warning(f"  ⚠️ Template {template_name} non trouvé dans {len(all_templates)} templates")
            except Exception as e:
                logger.warning(f"Could not fetch template details: {e}", exc_info=True)
        
        # Log pour déboguer
        logger.info(f"📤 Envoi template: name={template_name}, to={to_number}, components={components}")
        if template_details:
            logger.info(f"  Template details: {template_details.get('components', [])}")
        
        # Construire les composants nécessaires
        final_components = []
        template_header_image_url = None  # Pour sauvegarder l'URL de l'image du template
        
        # Si le template a un header avec un format (IMAGE, VIDEO, DOCUMENT, etc.), 
        # il faut envoyer un composant HEADER même vide
        if template_details:
            template_components = template_details.get("components", [])
            header_component = next(
                (c for c in template_components if c.get("type") == "HEADER"),
                None
            )
            
            if header_component:
                header_format = header_component.get("format")
                if header_format in ["IMAGE", "VIDEO", "DOCUMENT"]:
                    # Pour les templates avec média dans le header, il faut uploader le média et obtenir un media_id
                    example = header_component.get("example", {})
                    header_handle = example.get("header_handle", [])
                    example_url = header_handle[0] if isinstance(header_handle, list) and len(header_handle) > 0 else None
                    
                    if example_url:
                        # Sauvegarder l'URL pour l'afficher dans le chat
                        template_header_image_url = example_url
                        
                        try:
                            # Télécharger l'image depuis l'URL
                            import httpx
                            from app.core.http_client import get_http_client_for_media
                            
                            logger.info(f"  📥 Téléchargement de l'image pour le header: {example_url[:100]}...")
                            client = await get_http_client_for_media()
                            media_response = await client.get(example_url)
                            media_response.raise_for_status()
                            
                            # Détecter le content-type
                            content_type = media_response.headers.get("content-type", "image/jpeg")
                            media_data = media_response.content
                            
                            # Déterminer le nom de fichier selon le type
                            extension_map = {
                                "image/jpeg": ".jpg",
                                "image/png": ".png",
                                "image/gif": ".gif",
                                "image/webp": ".webp",
                                "video/mp4": ".mp4",
                                "application/pdf": ".pdf"
                            }
                            extension = extension_map.get(content_type, ".jpg")
                            filename = f"template_{template_name}_{header_format.lower()}{extension}"
                            
                            # Upload vers WhatsApp pour obtenir un media_id
                            from app.services.whatsapp_api_service import upload_media_from_bytes
                            logger.info(f"  📤 Upload de l'image vers WhatsApp...")
                            upload_result = await upload_media_from_bytes(
                                phone_number_id=phone_id,
                                access_token=token,
                                file_content=media_data,
                                filename=filename,
                                mime_type=content_type
                            )
                            
                            media_id = upload_result.get("id")
                            if media_id:
                                logger.info(f"  ✅ Media uploadé avec succès, media_id: {media_id}")
                                # Ajouter le composant HEADER avec le media_id
                                final_components.append({
                                    "type": "HEADER",
                                    "parameters": [{
                                        "type": header_format.lower(),  # "image", "video", "document"
                                        header_format.lower(): {
                                            "id": media_id
                                        }
                                    }]
                                })
                            else:
                                logger.warning(f"  ⚠️ Upload réussi mais pas de media_id dans la réponse: {upload_result}")
                                # Fallback : header vide (peut échouer mais on essaie)
                                final_components.append({
                                    "type": "HEADER",
                                    "parameters": []
                                })
                        except Exception as media_error:
                            logger.error(f"  ❌ Erreur lors de l'upload du média pour le header: {media_error}", exc_info=True)
                            # Fallback : header vide (peut échouer mais on essaie)
                            final_components.append({
                                "type": "HEADER",
                                "parameters": []
                            })
                    else:
                        # Pas d'URL d'exemple, header vide
                        logger.warning(f"  ⚠️ Pas d'URL d'exemple pour le header {header_format}")
                        final_components.append({
                            "type": "HEADER",
                            "parameters": []
                        })
        
        # Ajouter les composants fournis par l'utilisateur s'ils sont valides
        if components and len(components) > 0:
            # Vérifier si les composants contiennent des paramètres valides
            has_valid_parameters = any(
                comp.get("parameters") and isinstance(comp.get("parameters"), list) and len(comp.get("parameters", [])) > 0
                for comp in components
            )
            if has_valid_parameters:
                final_components.extend(components)
        
        # Si pas de composants nécessaires, envoyer None
        if len(final_components) == 0:
            final_components = None
        
        logger.info(f"  Final components: {final_components}")
        
        response = await whatsapp_api_service.send_template_message(
            phone_number_id=phone_id,
            access_token=token,
            to=to_number,
            template_name=template_name,
            language_code=language_code,
            components=final_components
        )
        
        message_id = response.get("messages", [{}])[0].get("id")
        timestamp_iso = datetime.now(timezone.utc).isoformat()
        
        # Récupérer le texte du template depuis les détails (BODY + FOOTER)
        # Et extraire les boutons si présents
        template_text = ""
        template_buttons = []
        template_variables_dict = {}
        
        # Extraire les variables depuis les components envoyés
        if components:
            import re
            for comp in components:
                if comp.get("type") in ["BODY", "HEADER", "FOOTER"] and comp.get("parameters"):
                    # Les paramètres sont dans l'ordre des variables {{1}}, {{2}}, etc.
                    parameters = comp.get("parameters", [])
                    for idx, param in enumerate(parameters, start=1):
                        if param.get("type") == "text":
                            template_variables_dict[str(idx)] = param.get("text", "")
        
        if template_details:
            # Extraire le texte du BODY et du FOOTER du template
            template_components = template_details.get("components", [])
            logger.info(f"  Template components: {template_components}")
            body_component = next(
                (c for c in template_components if c.get("type") == "BODY"),
                None
            )
            header_component = next(
                (c for c in template_components if c.get("type") == "HEADER"),
                None
            )
            footer_component = next(
                (c for c in template_components if c.get("type") == "FOOTER"),
                None
            )
            buttons_component = next(
                (c for c in template_components if c.get("type") == "BUTTONS"),
                None
            )
            
            # Extraire les boutons si présents
            if buttons_component and buttons_component.get("buttons"):
                template_buttons = buttons_component.get("buttons", [])
                logger.info(f"  Template buttons found: {len(template_buttons)} buttons")
            
            # Construire le texte avec les variables remplacées
            import re
            
            def replace_variables(text, variables):
                """Remplace les variables {{1}}, {{2}}, etc. par leurs valeurs"""
                if not text or not variables:
                    return text
                result = text
                # Remplacer dans l'ordre décroissant pour éviter les conflits ({{10}} avant {{1}})
                for var_num in sorted(variables.keys(), key=lambda x: int(x), reverse=True):
                    var_value = variables[var_num]
                    # Remplacer {{var_num}} par la valeur
                    # Pattern: {{1}}, {{2}}, etc.
                    pattern = r'\{\{' + str(var_num) + r'\}\}'
                    result = re.sub(pattern, var_value, result)
                return result
            
            # Header
            if header_component and header_component.get("text"):
                header_text = header_component.get("text", "")
                header_text = replace_variables(header_text, template_variables_dict)
                if header_text:
                    template_text = header_text + "\n\n"
            
            # Body
            if body_component:
                body_text = body_component.get("text", "")
                body_text = replace_variables(body_text, template_variables_dict)
                template_text += body_text
                logger.info(f"  Template text from BODY (with variables): {body_text}")
            
            # Footer
            if footer_component:
                footer_text = footer_component.get("text", "")
                footer_text = replace_variables(footer_text, template_variables_dict)
                if footer_text:
                    if template_text:
                        template_text = f"{template_text}\n\n{footer_text}"
                    else:
                        template_text = footer_text
                    logger.info(f"  Template text with footer: {template_text}")
            
            if not template_text:
                logger.warning(f"  No BODY or FOOTER component found in template {template_name}")
        else:
            logger.warning(f"  Template details not found for {template_name}, language {language_code}")
        
        # Si pas de texte trouvé, utiliser le nom du template comme fallback
        if not template_text:
            template_text = f"[Template: {template_name}]"
            logger.info(f"  Using fallback template text: {template_text}")
        
        logger.info(f"  Final template text to save (with variables replaced): {template_text}")
        logger.info(f"  Template variables: {template_variables_dict}")
        print(f"💾 [TEMPLATE SEND] Texte final à sauvegarder: {template_text}")
        print(f"💾 [TEMPLATE SEND] Variables: {template_variables_dict}")
        
        # Sauvegarder le message de manière synchrone pour éviter qu'il soit écrasé par le webhook
        from app.core.db import supabase_execute, supabase
        from app.services.message_service import _update_conversation_timestamp
        
        # Déterminer le message_type : si le template a une image, utiliser "image" pour l'affichage
        message_type = "template"
        if template_header_image_url:
            # Si le template a une image dans le header, utiliser "image" comme type pour l'affichage
            message_type = "image"
        
        message_payload = {
            "conversation_id": conversation_id,
            "direction": "outbound",
            "content_text": template_text,  # Texte avec variables remplacées
            "timestamp": timestamp_iso,
            "wa_message_id": message_id,
            "message_type": message_type,
            "status": "sent",
            "template_name": template_name,
            "template_language": language_code,
        }
        
        # Sauvegarder les variables dans template_variables si présentes
        if template_variables_dict:
            import json
            message_payload["template_variables"] = json.dumps(template_variables_dict)
            logger.info(f"  ✅ Variables sauvegardées: {template_variables_dict}")
        
        # Sauvegarder les boutons dans interactive_data si présents
        if template_buttons:
            import json
            interactive_data = {
                "type": "button",
                "buttons": [
                    {
                        "type": btn.get("type", "QUICK_REPLY"),
                        "text": btn.get("text", ""),
                        "url": btn.get("url", ""),
                        "phone_number": btn.get("phone_number", "")
                    }
                    for btn in template_buttons[:5]  # Sécurité: max 5 boutons (normalement max 3)
                ]
            }
            message_payload["interactive_data"] = json.dumps(interactive_data)
            logger.info(f"  ✅ Boutons sauvegardés dans interactive_data: {len(template_buttons)} boutons")
        
        # Si le template a une image, sauvegarder l'URL pour l'affichage
        if template_header_image_url:
            # Télécharger et stocker l'image dans Supabase Storage
            try:
                from app.services.storage_service import download_and_store_template_media
                import httpx
                
                # Détecter le content-type depuis l'URL
                async with httpx.AsyncClient(timeout=10.0) as client:
                    head_response = await client.head(template_header_image_url)
                    content_type = head_response.headers.get("content-type", "image/jpeg")
                
                # Télécharger et stocker le média
                storage_url = await download_and_store_template_media(
                    template_name=template_name,
                    template_language=language_code,
                    account_id=account["id"],
                    media_url=template_header_image_url,
                    media_type="IMAGE",
                    content_type=content_type
                )
                
                if storage_url:
                    message_payload["storage_url"] = storage_url
                    logger.info(f"  ✅ Image du template stockée: {storage_url}")
                else:
                    # Fallback : utiliser l'URL WhatsApp directement
                    message_payload["storage_url"] = template_header_image_url
                    logger.info(f"  ⚠️ Stockage échoué, utilisation de l'URL WhatsApp directement")
            except Exception as storage_error:
                logger.warning(f"  ⚠️ Erreur lors du stockage de l'image du template: {storage_error}")
                # Fallback : utiliser l'URL WhatsApp directement
                message_payload["storage_url"] = template_header_image_url
        
        print(f"💾 [TEMPLATE SEND] Message payload: {message_payload}")
        
        try:
            # Vérifier si le message existe déjà (créé par le webhook)
            print(f"🔍 [TEMPLATE SEND] Vérification si le message existe déjà avec wa_message_id: {message_id}")
            existing = await supabase_execute(
                supabase.table("messages")
                .select("id, content_text")
                .eq("wa_message_id", message_id)
                .limit(1)
            )
            
            print(f"🔍 [TEMPLATE SEND] Résultat de la vérification: {existing.data}")
            
            if existing.data:
                # Le message existe déjà, mettre à jour seulement si content_text est vide
                existing_record = existing.data[0]
                print(f"📝 [TEMPLATE SEND] Message existe déjà - ID: {existing_record.get('id')}, content_text actuel: '{existing_record.get('content_text')}'")
                update_data = {
                    "status": "sent",
                    "timestamp": timestamp_iso,
                }
                # Ne mettre à jour le content_text que s'il est vide ou null
                if not existing_record.get("content_text"):
                    update_data["content_text"] = template_text
                    logger.info(f"  📝 Mise à jour du content_text vide avec: {template_text[:50]}...")
                    print(f"📝 [TEMPLATE SEND] Mise à jour du content_text vide avec: {template_text[:50]}...")
                else:
                    logger.info(f"  ℹ️  Le message a déjà un content_text, on ne l'écrase pas")
                    print(f"ℹ️  [TEMPLATE SEND] Le message a déjà un content_text: '{existing_record.get('content_text')}', on ne l'écrase pas")
                
                print(f"💾 [TEMPLATE SEND] Données de mise à jour: {update_data}")
                await supabase_execute(
                    supabase.table("messages")
                    .update(update_data)
                    .eq("id", existing_record["id"])
                )
                print(f"✅ [TEMPLATE SEND] Message mis à jour avec succès")
            else:
                # Le message n'existe pas encore, créer avec tous les champs
                print(f"🆕 [TEMPLATE SEND] Création d'un nouveau message avec tous les champs")
                result = await supabase_execute(
                    supabase.table("messages").insert(message_payload)
                )
                print(f"✅ [TEMPLATE SEND] Nouveau message créé: {result.data if result.data else 'pas de données retournées'}")
                logger.info(f"  ✅ Nouveau message template créé avec texte: {template_text[:50]}...")
            
            await _update_conversation_timestamp(conversation_id, timestamp_iso)
            print(f"✅ [TEMPLATE SEND] Timestamp de conversation mis à jour")
        except Exception as e:
            logger.error("Error saving template message to database: %s", e, exc_info=True)
            print(f"❌ [TEMPLATE SEND] Erreur lors de la sauvegarde: {e}")
            import traceback
            print(f"❌ [TEMPLATE SEND] Traceback: {traceback.format_exc()}")
        
        price_info = await calculate_message_price(conversation_id, use_template=True)
        
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
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/send-media")
async def send_media_api_message(payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    """
    Envoie un message média (image, audio, vidéo, document)
    
    Payload:
    {
      "conversation_id": "uuid",
      "media_type": "image|audio|video|document",
      "media_id": "whatsapp_media_id",
      "caption": "optional caption"
    }
    """
    conversation_id = payload.get("conversation_id")
    media_type = payload.get("media_type")
    media_id = payload.get("media_id")
    caption = payload.get("caption")
    
    if not conversation_id or not media_type or not media_id:
        raise HTTPException(status_code=400, detail="conversation_id, media_type, and media_id are required")
    
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    
    # Vérifier que l'utilisateur a accès en écriture (pas 'aucun' ni 'lecture')
    access_level = current_user.permissions.account_access_levels.get(conversation["account_id"])
    if access_level == "aucun":
        raise HTTPException(status_code=403, detail="account_access_denied")
    if access_level == "lecture":
        raise HTTPException(status_code=403, detail="write_access_denied")
    
    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])
    
    return await send_media_message_with_storage(
        conversation_id=conversation_id,
        media_type=media_type,
        media_id=media_id,
        caption=caption
    )


@router.post("/test-storage/{message_id}")
async def test_storage_for_message(
    message_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Endpoint de test pour forcer le téléchargement et stockage d'un média existant
    Utile pour déboguer et stocker rétroactivement des médias
    """
    message = await get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message_not_found")
    
    conversation = await get_conversation_by_id(message["conversation_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    
    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])
    
    account = await get_account_by_id(conversation["account_id"])
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    media_id = message.get("media_id")
    if not media_id:
        raise HTTPException(status_code=400, detail="message_has_no_media_id")
    
    message_type = message.get("message_type", "").lower()
    if message_type not in ("image", "video", "audio", "document", "sticker"):
        raise HTTPException(status_code=400, detail="message_is_not_a_media_type")
    
    # Importer la fonction depuis message_service
    from app.services.message_service import _download_and_store_media_async
    
    # Forcer le téléchargement et stockage
    await _download_and_store_media_async(
        message_db_id=message_id,
        media_id=media_id,
        account=account,
        mime_type=message.get("media_mime_type"),
        filename=message.get("media_filename")
    )
    
    return {"status": "processing", "message": "Media download and storage started in background"}


@router.post("/send-interactive")
async def send_interactive_api_message(payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    """
    Envoie un message interactif (boutons ou liste)
    
    Payload pour boutons:
    {
      "conversation_id": "uuid",
      "interactive_type": "button",
      "body_text": "Texte principal",
      "buttons": [{"id": "btn1", "title": "Bouton 1"}],
      "header_text": "En-tête (optionnel)",
      "footer_text": "Pied de page (optionnel)"
    }
    
    Payload pour liste:
    {
      "conversation_id": "uuid",
      "interactive_type": "list",
      "body_text": "Texte principal",
      "button_text": "Voir les options",
      "sections": [{"title": "Section 1", "rows": [{"id": "row1", "title": "Option 1"}]}],
      "header_text": "En-tête (optionnel)",
      "footer_text": "Pied de page (optionnel)"
    }
    """
    conversation_id = payload.get("conversation_id")
    interactive_type = payload.get("interactive_type")
    body_text = payload.get("body_text")
    header_text = payload.get("header_text")
    footer_text = payload.get("footer_text")
    
    if not conversation_id or not interactive_type or not body_text:
        raise HTTPException(status_code=400, detail="conversation_id, interactive_type, and body_text are required")
    
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    
    # Vérifier que l'utilisateur a accès en écriture (pas 'aucun' ni 'lecture')
    access_level = current_user.permissions.account_access_levels.get(conversation["account_id"])
    if access_level == "aucun":
        raise HTTPException(status_code=403, detail="account_access_denied")
    if access_level == "lecture":
        raise HTTPException(status_code=403, detail="write_access_denied")
    
    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])
    
    # Construire le payload d'action selon le type
    if interactive_type == "button":
        buttons = payload.get("buttons", [])
        if not buttons:
            raise HTTPException(status_code=400, detail="buttons are required for button type")
        
        interactive_payload = {
            "buttons": [
                {"type": "reply", "reply": {"id": btn["id"], "title": btn["title"]}}
                for btn in buttons
            ]
        }
    elif interactive_type == "list":
        sections = payload.get("sections", [])
        button_text = payload.get("button_text", "Voir les options")
        if not sections:
            raise HTTPException(status_code=400, detail="sections are required for list type")
        
        interactive_payload = {
            "button": button_text,
            "sections": sections
        }
    else:
        raise HTTPException(status_code=400, detail="invalid interactive_type")
    
    return await send_interactive_message_with_storage(
        conversation_id=conversation_id,
        interactive_type=interactive_type,
        body_text=body_text,
        interactive_payload=interactive_payload,
        header_text=header_text,
        footer_text=footer_text
    )


@router.patch("/{message_id}")
async def edit_message(
    message_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Édite un message texte (édition locale uniquement).
    """
    new_content = (payload.get("content_text") or "").strip()
    if not new_content:
        raise HTTPException(status_code=400, detail="content_text_required")

    message = await get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message_not_found")

    conversation = await get_conversation_by_id(message["conversation_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])

    # CurrentUser stocke l'identifiant dans `id` (pas `user_id`)
    result = await update_message_content(message_id, new_content, current_user.id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result["message"]


@router.post("/{message_id}/delete")
async def delete_message(
    message_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Supprime un message localement.
    scope=me : masque pour l'utilisateur courant.
    scope=all : marque comme supprimé pour tous (pas de suppression réseau WhatsApp).
    """
    scope = payload.get("scope", "me")
    if scope not in ("me", "all"):
        raise HTTPException(status_code=400, detail="invalid_scope")

    message = await get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message_not_found")

    conversation = await get_conversation_by_id(message["conversation_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])

    result = await delete_message_scope(message_id, scope, current_user.id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result["message"]


@router.delete("/{message_id}")
async def permanently_delete_message(
    message_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Supprime définitivement un message de la base de données.
    Utilisé pour supprimer les messages échoués avant de les renvoyer.
    """
    from app.core.db import supabase_execute, supabase
    
    message = await get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message_not_found")

    conversation = await get_conversation_by_id(message["conversation_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])

    # Supprimer définitivement le message
    await supabase_execute(
        supabase.table("messages").delete().eq("id", message_id)
    )
    
    return {"status": "deleted", "message_id": message_id}


@router.post("/reactions/add")
async def add_message_reaction(
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Ajoute une réaction à un message.
    
    Payload:
    {
      "message_id": "uuid",
      "emoji": "👍",
      "from_number": "33783788348"  # Optionnel, utilise le numéro de l'account si non fourni
    }
    """
    message_id = payload.get("message_id")
    emoji = payload.get("emoji")
    
    if not message_id or not emoji:
        raise HTTPException(status_code=400, detail="message_id and emoji are required")
    
    # Récupérer le message pour vérifier les permissions
    message = await get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message_not_found")
    
    conversation = await get_conversation_by_id(message["conversation_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    
    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])
    
    # Utiliser le numéro de l'account comme from_number si non fourni
    account = await get_account_by_id(conversation["account_id"])
    from_number = payload.get("from_number") or account.get("phone_number") or account.get("phone_number_id")
    
    if not from_number:
        raise HTTPException(status_code=400, detail="from_number is required")
    
    # Ajouter la réaction en base
    result = await add_reaction(message_id, emoji, from_number)
    
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    
    # Envoyer la réaction via WhatsApp si le message a un wa_message_id
    if message.get("wa_message_id"):
        wa_result = await send_reaction_to_whatsapp(
            conversation["id"],
            message["wa_message_id"],
            emoji,
        )
        if wa_result.get("error"):
            logger.warning("Failed to send reaction to WhatsApp: %s", wa_result)
    
    return result


@router.post("/reactions/remove")
async def remove_message_reaction(
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Supprime une réaction d'un message.
    
    Payload:
    {
      "message_id": "uuid",
      "emoji": "👍",
      "from_number": "33783788348"  # Optionnel
    }
    """
    message_id = payload.get("message_id")
    emoji = payload.get("emoji")
    
    if not message_id or not emoji:
        raise HTTPException(status_code=400, detail="message_id and emoji are required")
    
    # Récupérer le message pour vérifier les permissions
    message = await get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message_not_found")
    
    conversation = await get_conversation_by_id(message["conversation_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    
    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])
    
    # Utiliser le numéro de l'account comme from_number si non fourni
    account = await get_account_by_id(conversation["account_id"])
    from_number = payload.get("from_number") or account.get("phone_number") or account.get("phone_number_id")
    
    if not from_number:
        raise HTTPException(status_code=400, detail="from_number is required")
    
    # Supprimer la réaction en base
    result = await remove_reaction(message_id, emoji, from_number)
    
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    
    # Envoyer la suppression de réaction via WhatsApp (emoji vide)
    if message.get("wa_message_id"):
        wa_result = await send_reaction_to_whatsapp(
            conversation["id"],
            message["wa_message_id"],
            "",  # Emoji vide = suppression
        )
        if wa_result.get("error"):
            logger.warning("Failed to remove reaction on WhatsApp: %s", wa_result)
    
    return result


@router.post("/check-whatsapp")
async def check_phone_has_whatsapp(
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Vérifie si un numéro de téléphone a un compte WhatsApp actif.
    
    Payload:
    {
      "phone_number": "+33612345678" ou "33612345678",
      "account_id": "uuid"  # Optionnel, utilise le premier compte si non fourni
    }
    
    Returns:
    {
      "has_whatsapp": true/false/null,
      "name": "Nom du contact" ou null,
      "profile_picture_url": "url" ou null,
      "phone_number": "33612345678",
      "error": "message d'erreur" ou null
    }
    """
    phone_number = payload.get("phone_number")
    account_id = payload.get("account_id")
    
    if not phone_number:
        raise HTTPException(status_code=400, detail="phone_number is required")
    
    # Récupérer le compte
    if account_id:
        account = await get_account_by_id(account_id)
        if not account:
            raise HTTPException(status_code=404, detail="account_not_found")
        # Vérifier les permissions
        current_user.require(PermissionCodes.MESSAGES_VIEW, account_id)
    else:
        # Utiliser le premier compte disponible pour l'utilisateur
        from app.services.account_service import get_all_accounts
        all_accounts = await get_all_accounts()
        if not all_accounts:
            raise HTTPException(status_code=404, detail="no_accounts_found")
        
        # Trouver le premier compte auquel l'utilisateur a accès
        account = None
        for acc in all_accounts:
            try:
                current_user.require(PermissionCodes.MESSAGES_VIEW, acc["id"])
                account = acc
                break
            except:
                continue
        
        if not account:
            raise HTTPException(status_code=403, detail="no_account_access")
    
    phone_number_id = account.get("phone_number_id")
    access_token = account.get("access_token")
    
    if not phone_number_id or not access_token:
        raise HTTPException(status_code=400, detail="whatsapp_not_configured")
    
    # Vérifier si le numéro a WhatsApp
    result = await check_phone_number_has_whatsapp(
        phone_number_id=phone_number_id,
        access_token=access_token,
        phone_number=phone_number
    )
    
    return result