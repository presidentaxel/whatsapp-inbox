"""
Lectures: liste de messages, contenu média, fenêtre gratuite 24h, prix message.
"""
from ._common import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    StreamingResponse,
    datetime,
    timezone,
    CurrentUser,
    PermissionCodes,
    calculate_message_price,
    fetch_message_media_content,
    get_account_by_id,
    get_conversation_by_id,
    get_current_user,
    get_message_by_id,
    get_messages,
    is_within_free_window,
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

    storage_url = message.get("storage_url")
    if storage_url:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=storage_url, status_code=302)

    try:
        content, mime_type, filename = await fetch_message_media_content(message, account)
    except ValueError as exc:
        error_detail = str(exc)
        if error_detail in ("media_expired_or_invalid", "media_not_found"):
            raise HTTPException(status_code=410, detail=error_detail)
        raise HTTPException(status_code=400, detail=error_detail)

    headers = {}
    if filename:
        headers["Content-Disposition"] = f'inline; filename="{filename}"'

    return StreamingResponse(iter([content]), media_type=mime_type, headers=headers)


@router.get("/free-window/{conversation_id}")
async def check_free_window(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    fresh: bool = Query(False, description="Si true, ignore le cache pour une vérification à jour"),
):
    """
    Vérifie si on est dans la fenêtre gratuite de 24h pour une conversation.
    """
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])

    is_free, last_inbound_time = await is_within_free_window(conversation_id, skip_cache=fresh)

    result = {
        "is_free": is_free,
        "last_inbound_time": last_inbound_time.isoformat() if last_inbound_time else None,
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
    current_user: CurrentUser = Depends(get_current_user),
    fresh: bool = Query(False, description="Si true, ignore le cache pour une vérification à jour"),
):
    """
    Calcule le prix d'un message pour une conversation. L'assistance classique
    24h est gratuite (dans la fenêtre de 24h). Hors fenêtre, message
    conversationnel normal (0,0248 €).
    """
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])

    price_info = await calculate_message_price(conversation_id, use_conversational=True, skip_cache=fresh)
    return price_info
