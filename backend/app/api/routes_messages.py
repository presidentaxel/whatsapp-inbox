from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.account_service import get_account_by_id
from app.services.conversation_service import get_conversation_by_id
from app.services.message_service import (
    fetch_message_media_content,
    get_message_by_id,
    get_messages,
    send_message,
)

router = APIRouter()


@router.get("/{conversation_id}")
async def fetch_messages(
    conversation_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])
    return await get_messages(conversation_id)


@router.get("/media/{message_id}")
async def fetch_message_media(
    message_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    message = await get_message_by_id(message_id)
    if not message or not message.get("media_id"):
        raise HTTPException(status_code=404, detail="media_not_found")

    conversation = await get_conversation_by_id(message["conversation_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])
    account = get_account_by_id(conversation["account_id"])
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")

    try:
        content, mime_type, filename = await fetch_message_media_content(message, account)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

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