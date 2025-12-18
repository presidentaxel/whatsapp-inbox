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
    Utilise un message conversationnel normal (pas de template) si hors fenêtre.
    
    Returns:
    {
        "is_free": true/false,
        "price_usd": 0.02,
        "price_eur": 0.018,
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
    Retourne uniquement les templates UTILITY approuvés.
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
    
    if not waba_id or not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        templates_result = await whatsapp_api_service.list_message_templates(
            waba_id=waba_id,
            access_token=access_token,
            limit=100
        )
        
        # Filtrer uniquement les templates UTILITY approuvés
        templates = templates_result.get("data", [])
        
        def get_template_price(category):
            """Retourne le prix d'un template selon sa catégorie (prix Meta officiels)"""
            # Prix selon la documentation Meta WhatsApp Business API
            # https://developers.facebook.com/docs/whatsapp/pricing
            prices = {
                "UTILITY": {"usd": 0.008, "eur": 0.007},  # ~0.005-0.01 USD
                "MARKETING": {"usd": 0.02, "eur": 0.018},  # ~0.015-0.03 USD
                "AUTHENTICATION": {"usd": 0.005, "eur": 0.004},  # Généralement moins cher
            }
            return prices.get(category, {"usd": 0.008, "eur": 0.007})
        
        approved_utility_templates = []
        for t in templates:
            if t.get("status") == "APPROVED" and t.get("category") == "UTILITY":
                price = get_template_price(t.get("category"))
                approved_utility_templates.append({
                    "name": t.get("name"),
                    "status": t.get("status"),
                    "category": t.get("category"),
                    "language": t.get("language"),
                    "components": t.get("components", []),
                    "price_usd": price["usd"],
                    "price_eur": price["eur"]
                })
        
        return {
            "templates": approved_utility_templates
        }
    except Exception as e:
        logger.error(f"Error fetching templates: {e}", exc_info=True)
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
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    
    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])
    
    template_name = payload.get("template_name")
    components = payload.get("components", [])
    
    if not template_name:
        raise HTTPException(status_code=400, detail="template_name_required")
    
    account = await get_account_by_id(conversation["account_id"])
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    phone_id = account.get("phone_number_id")
    token = account.get("access_token")
    to_number = conversation["client_number"]
    
    if not phone_id or not token:
        raise HTTPException(status_code=400, detail="whatsapp_not_configured")
    
    try:
        response = await whatsapp_api_service.send_template_message(
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
        import asyncio
        from app.core.db import supabase_execute, supabase
        from app.services.message_service import _update_conversation_timestamp
        
        message_payload = {
            "conversation_id": conversation_id,
            "direction": "outbound",
            "content_text": components[0].get("text", "") if components else "",
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
                    _update_conversation_timestamp(conversation_id, timestamp_iso)
                )
            except Exception as e:
                logger.error("Error saving template message to database: %s", e, exc_info=True)
        
        asyncio.create_task(_save_message_async())
        
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