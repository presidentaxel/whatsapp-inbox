"""
Routes de webhooks WhatsApp
Gère la vérification et la réception des événements WhatsApp
"""
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.services.account_service import get_account_by_verify_token
from app.services.message_service import handle_incoming_message

router = APIRouter(tags=["Webhooks"])
logger = logging.getLogger(__name__)


@router.get("/whatsapp")
async def verify_webhook(request: Request):
    """
    Endpoint de vérification du webhook WhatsApp
    
    Meta appelle ce endpoint avec les paramètres suivants:
    - hub.mode=subscribe
    - hub.verify_token=<votre_token>
    - hub.challenge=<challenge_string>
    
    Vous devez:
    1. Vérifier que hub.verify_token correspond à votre token configuré
    2. Retourner hub.challenge en 200 OK
    
    Ce endpoint supporte:
    - Le verify_token global (WHATSAPP_VERIFY_TOKEN dans .env)
    - Les verify_token par account (dans la table whatsapp_accounts)
    
    Documentation Meta:
    https://developers.facebook.com/docs/graph-api/webhooks/getting-started#verification-requests
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge", "")

    logger.info(
        f"Webhook verification request: mode={mode}, token={'***' if token else 'None'}, "
        f"challenge={'present' if challenge else 'missing'}"
    )

    if mode == "subscribe":
        # Vérifier le token global
        if settings.WHATSAPP_VERIFY_TOKEN and token == settings.WHATSAPP_VERIFY_TOKEN:
            logger.info("Webhook verified with global token")
            return PlainTextResponse(challenge, media_type="text/plain")

        # Vérifier les tokens par account (multi-tenant)
        account = await get_account_by_verify_token(token)
        if account:
            logger.info(f"Webhook verified with account token: {account.get('name')}")
            return PlainTextResponse(challenge, media_type="text/plain")

    logger.warning(f"Webhook verification failed: mode={mode}, token={'***' if token else 'None'}")
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Endpoint de réception des événements WhatsApp
    
    Meta envoie des POST JSON avec les événements suivants:
    - messages: Nouveaux messages reçus
    - statuses: Mises à jour de statuts (sent, delivered, read, failed)
    - message_template_status_update: Changement de statut d'un template
    - account_update: Mise à jour du compte business
    - account_alerts: Alertes du compte
    
    Format du payload:
    {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "...",
                                "phone_number_id": "..."
                            },
                            "messages": [...],
                            "statuses": [...]
                        },
                        "field": "messages"
                    }
                ]
            }
        ]
    }
    
    Documentation Meta:
    https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components
    """
    try:
        data = await request.json()
        
        # Log basique pour debug (sans exposer les données sensibles)
        logger.info(
            f"Webhook received: object={data.get('object')}, "
            f"entries={len(data.get('entry', []))}"
        )
        
        await handle_incoming_message(data)
        
        # WhatsApp attend une réponse 200 rapide
        return {"status": "received"}
    
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        # On retourne quand même 200 pour ne pas que Meta réessaye indéfiniment
        return {"status": "error", "message": str(e)}