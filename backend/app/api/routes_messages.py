import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.auth import get_current_user

logger = logging.getLogger(__name__)
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.account_service import get_account_by_id
from app.services.conversation_service import get_conversation_by_id
from app.services.message_service import (
    add_reaction,
    fetch_message_media_content,
    get_message_by_id,
    get_messages,
    remove_reaction,
    send_message,
    send_media_message_with_storage,
    send_interactive_message_with_storage,
    send_reaction_to_whatsapp,
)

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
    conversation_id = payload.get("conversation_id")
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id_required")
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])
    return await send_message(payload)


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
    
    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])
    
    return await send_media_message_with_storage(
        conversation_id=conversation_id,
        media_type=media_type,
        media_id=media_id,
        caption=caption
    )


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