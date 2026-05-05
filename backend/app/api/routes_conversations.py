import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_user
from app.core.datetime_parse import parse_optional_iso_datetime

logger = logging.getLogger(__name__)
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.conversation_service import (
    get_all_conversations,
    get_conversation_by_id,
    mark_conversation_read,
    mark_conversation_unread,
    set_conversation_bot_mode,
    set_conversation_favorite,
    set_conversation_playground_flow,
    find_or_create_conversation,
)
from app.services.playground_flow_service import get_flow_by_id

router = APIRouter()


@router.get("")
async def list_conversations(
    account_id: str = Query(..., description="WhatsApp account ID"),
    limit: int = Query(200, ge=1, le=200, description="Nombre max de conversations"),
    cursor: str | None = Query(
        None,
        description="ISO timestamp cursor: retourne les conversations avant cette date",
    ),
    updated_since: str | None = Query(
        None,
        description="ISO timestamp: retourne uniquement les conversations mises à jour après cette date (delta refresh)",
    ),
    current_user: CurrentUser = Depends(get_current_user),
):
    if current_user.permissions.account_access_levels.get(account_id) == "aucun":
        raise HTTPException(status_code=403, detail="account_access_denied")
    
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, account_id)
    cursor_dt = parse_optional_iso_datetime(cursor, param_name="cursor")
    updated_since_dt = parse_optional_iso_datetime(updated_since, param_name="updated_since")
    conversations = await get_all_conversations(
        account_id, limit=limit, cursor=cursor_dt, updated_since=updated_since_dt
    )
    if conversations is None:
        raise HTTPException(status_code=404, detail="account_not_found")
    return conversations


@router.post("/{conversation_id}/read")
async def mark_read(conversation_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """
    Marque une conversation comme lue.
    Gère les erreurs gracieusement pour éviter les ECONNRESET.
    """
    try:
        conversation = await get_conversation_by_id(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="conversation_not_found")
        current_user.require(PermissionCodes.CONVERSATIONS_VIEW, conversation["account_id"])
        success = await mark_conversation_read(conversation_id)
        if not success:
            # Si l'opération a échoué, on retourne quand même un succès pour éviter ECONNRESET
            # Le frontend pourra réessayer si nécessaire
            logger.warning(f"Failed to mark conversation {conversation_id} as read, but returning success to avoid connection reset")
        return {"status": "ok"}
    except HTTPException:
        # Re-raise les HTTPException (404, 403, etc.)
        raise
    except Exception as e:
        logger.error(f"Unexpected error marking conversation {conversation_id} as read: {e}", exc_info=True)
        return {"status": "ok"}  # Retourner ok même en cas d'erreur pour éviter ECONNRESET


@router.post("/{conversation_id}/unread")
async def mark_unread(conversation_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """
    Marque une conversation comme non lue (unread_count = 1).
    Permet à l'utilisateur de marquer manuellement une conversation pour y revenir plus tard.
    """
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, conversation["account_id"])
    await mark_conversation_unread(conversation_id)
    return {"status": "ok"}


@router.post("/{conversation_id}/favorite")
async def toggle_favorite(
    conversation_id: str, payload: dict, current_user: CurrentUser = Depends(get_current_user)
):
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, conversation["account_id"])
    favorite = bool(payload.get("favorite"))
    await set_conversation_favorite(conversation_id, favorite)
    return {"status": "ok", "favorite": favorite}


@router.post("/{conversation_id}/bot")
async def toggle_bot(
    conversation_id: str, payload: dict, current_user: CurrentUser = Depends(get_current_user)
):
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])
    enabled = bool(payload.get("enabled"))
    reply_mode = payload.get("reply_mode")
    if reply_mode is not None and reply_mode not in ("gemini", "playground"):
        raise HTTPException(status_code=400, detail="invalid_reply_mode")
    updated = await set_conversation_bot_mode(conversation_id, enabled, reply_mode)
    if not updated:
        raise HTTPException(status_code=500, detail="bot_toggle_failed")
    return {"status": "ok", "conversation": updated}


@router.post("/{conversation_id}/playground-flow")
async def set_conversation_playground_flow_route(
    conversation_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])
    raw_id = payload.get("playground_flow_id")
    if raw_id:
        flow = await get_flow_by_id(str(raw_id))
        if not flow or str(flow.get("account_id")) != str(conversation["account_id"]):
            raise HTTPException(status_code=400, detail="invalid_playground_flow")
        fid = str(raw_id)
    else:
        fid = None
    updated = await set_conversation_playground_flow(conversation_id, fid)
    if not updated:
        raise HTTPException(status_code=500, detail="update_failed")
    return {"status": "ok", "conversation": updated}


@router.post("/find-or-create")
async def find_or_create(
    payload: dict, current_user: CurrentUser = Depends(get_current_user)
):
    """
    Trouve ou crée une conversation avec un numéro de téléphone.
    
    Payload:
    {
        "account_id": "uuid",
        "phone_number": "+33612345678" ou "06 12 34 56 78" (format libre)
    }
    """
    import logging
    logger = logging.getLogger(__name__)
    
    account_id = payload.get("account_id")
    phone_number = payload.get("phone_number")
    
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id is required")
    if not phone_number:
        raise HTTPException(status_code=400, detail="phone_number is required")
    
    # Vérifier que l'utilisateur a accès au compte
    if current_user.permissions.account_access_levels.get(account_id) == "aucun":
        raise HTTPException(status_code=403, detail="account_access_denied")
    
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, account_id)
    
    try:
        logger.info(f"Creating/finding conversation: account_id={account_id}, phone={phone_number}")
        conversation = await find_or_create_conversation(account_id, phone_number)
        
        if not conversation:
            logger.error(f"Failed to create conversation: account_id={account_id}, phone={phone_number}")
            raise HTTPException(
                status_code=400, 
                detail="Failed to create conversation. Please check the phone number format (e.g., +33612345678 or 0612345678) and ensure the account exists."
            )
        
        logger.info(f"Successfully created/found conversation: {conversation.get('id')}")
        return conversation
    except ValueError as ve:
        # Erreur de validation du numéro de téléphone
        logger.warning(f"Phone number validation error: {ve}")
        raise HTTPException(
            status_code=400,
            detail=str(ve) or "Invalid phone number format. Please use format like +33612345678 or 0612345678"
        )
    except HTTPException as he:
        # Re-raise HTTPException avec le message original
        raise
    except Exception as e:
        logger.error(f"Unexpected error in find_or_create: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while creating the conversation. Please try again or contact support if the issue persists."
        )