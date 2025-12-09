from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.conversation_service import (
    get_all_conversations,
    get_conversation_by_id,
    mark_conversation_read,
    set_conversation_bot_mode,
    set_conversation_favorite,
)

router = APIRouter()


@router.get("")
async def list_conversations(
    account_id: str = Query(..., description="WhatsApp account ID"),
    limit: int = Query(50, ge=1, le=200, description="Nombre max de conversations"),
    cursor: str | None = Query(
        None, description="ISO timestamp cursor: retourne les conversations avant cette date"
    ),
    current_user: CurrentUser = Depends(get_current_user),
):
    # Vérifier que l'utilisateur a accès au compte (pas en 'aucun')
    if current_user.permissions.account_access_levels.get(account_id) == "aucun":
        raise HTTPException(status_code=403, detail="account_access_denied")
    
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, account_id)
    conversations = await get_all_conversations(account_id, limit=limit, cursor=cursor)
    if conversations is None:
        raise HTTPException(status_code=404, detail="account_not_found")
    return conversations


@router.post("/{conversation_id}/read")
async def mark_read(conversation_id: str, current_user: CurrentUser = Depends(get_current_user)):
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, conversation["account_id"])
    await mark_conversation_read(conversation_id)
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
    updated = await set_conversation_bot_mode(conversation_id, enabled)
    if not updated:
        raise HTTPException(status_code=500, detail="bot_toggle_failed")
    return {"status": "ok", "conversation": updated}