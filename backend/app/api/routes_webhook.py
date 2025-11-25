from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.services.account_service import get_account_by_verify_token
from app.services.message_service import handle_incoming_message

router = APIRouter()

@router.get("/whatsapp")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge", "")

    if mode == "subscribe":
        if settings.WHATSAPP_VERIFY_TOKEN and token == settings.WHATSAPP_VERIFY_TOKEN:
            return PlainTextResponse(challenge, media_type="text/plain")

        account = await get_account_by_verify_token(token)
        if account:
            return PlainTextResponse(challenge, media_type="text/plain")

    raise HTTPException(status_code=403, detail="Webhook verification failed")

@router.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    data = await request.json()
    await handle_incoming_message(data)
    return {"status": "received"}