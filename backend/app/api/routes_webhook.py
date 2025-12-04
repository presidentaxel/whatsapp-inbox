"""
Routes de webhooks WhatsApp
Gère la vérification et la réception des événements WhatsApp
"""
import json
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.services.account_service import get_account_by_verify_token, get_all_accounts
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
        f"🔍 Webhook verification request: mode={mode}, token={'***' + token[:5] + '...' if token else 'None'}, "
        f"challenge={'present' if challenge else 'missing'}, "
        f"expected_token={'***' + settings.WHATSAPP_VERIFY_TOKEN[:5] + '...' if settings.WHATSAPP_VERIFY_TOKEN else 'None'}"
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
        # Log immédiat pour voir que la requête arrive
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"📥 POST /webhook/whatsapp received from {client_ip}")
        
        data = await request.json()
        
        # Log détaillé pour debug - inclure la structure complète si nécessaire
        entries = data.get("entry", [])
        logger.info(
            f"📥 POST /whatsapp webhook received: object={data.get('object')}, "
            f"entries={len(entries)}"
        )
        
        # Log détaillé de la structure pour debug
        for entry_idx, entry in enumerate(entries):
            entry_id = entry.get("id")
            changes = entry.get("changes", [])
            logger.info(
                f"   Entry {entry_idx + 1}: id={entry_id}, changes={len(changes)}"
            )
            for change_idx, change in enumerate(changes):
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                phone_number_id = metadata.get("phone_number_id")
                logger.info(
                    f"      Change {change_idx + 1}: field={change.get('field')}, "
                    f"phone_number_id={phone_number_id}, "
                    f"has_messages={bool(value.get('messages'))}, "
                    f"has_statuses={bool(value.get('statuses'))}"
                )
        
        # Compter les messages et statuts
        total_messages = 0
        total_statuses = 0
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                statuses = value.get("statuses", [])
                total_messages += len(messages)
                total_statuses += len(statuses)
                
                # Log détaillé pour chaque change
                if messages:
                    logger.info(f"📨 Change contains {len(messages)} message(s)")
                    for msg in messages:
                        logger.info(f"   - Message type: {msg.get('type')}, from: {msg.get('from')}")
                if statuses:
                    logger.info(f"📊 Change contains {len(statuses)} status(es)")
        
        if total_messages > 0 or total_statuses > 0:
            logger.info(f"📨 Webhook contains {total_messages} message(s) and {total_statuses} status(es)")
        else:
            logger.warning("⚠️ Webhook received but no messages or statuses found")
        
        # Log complet du webhook pour debug (sans les données sensibles)
        logger.debug(f"📋 Full webhook payload: {json.dumps(data, indent=2)}")
        
        await handle_incoming_message(data)
        
        # WhatsApp attend une réponse 200 rapide
        return {"status": "received"}
    
    except Exception as e:
        logger.error(f"❌ Error processing webhook: {e}", exc_info=True)
        # Enregistrer l'erreur pour diagnostic
        try:
            from app.api.routes_diagnostics import log_error_to_memory
            log_error_to_memory(
                "webhook_processing",
                str(e),
                {
                    "client_ip": request.client.host if request.client else "unknown",
                    "data_keys": list(data.keys()) if 'data' in locals() else []
                }
            )
        except:
            pass  # Ne pas faire échouer si le diagnostic échoue
        # On retourne quand même 200 pour ne pas que Meta réessaye indéfiniment
        return {"status": "error", "message": str(e)}


@router.post("/whatsapp/debug")
async def whatsapp_webhook_debug(request: Request):
    """
    Endpoint de debug pour capturer et afficher les webhooks reçus
    Utile pour voir exactement ce qui arrive de Meta
    """
    try:
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"🔍 DEBUG: POST /webhook/whatsapp/debug received from {client_ip}")
        
        data = await request.json()
        
        # Afficher la structure complète
        logger.info("=" * 80)
        logger.info("🔍 WEBHOOK DEBUG - STRUCTURE COMPLÈTE")
        logger.info("=" * 80)
        logger.info(json.dumps(data, indent=2))
        logger.info("=" * 80)
        
        # Analyser la structure
        entries = data.get("entry", [])
        logger.info(f"📊 Analyse: {len(entries)} entry/entries")
        
        all_accounts = await get_all_accounts()
        logger.info(f"📋 Comptes disponibles en base: {len(all_accounts)}")
        for acc in all_accounts:
            logger.info(f"   - {acc.get('name')}: phone_number_id={acc.get('phone_number_id')}")
        
        for entry_idx, entry in enumerate(entries):
            entry_id = entry.get("id")
            logger.info(f"\n📦 Entry {entry_idx + 1}: id={entry_id}")
            
            changes = entry.get("changes", [])
            for change_idx, change in enumerate(changes):
                field = change.get("field")
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                phone_number_id = metadata.get("phone_number_id")
                
                logger.info(f"   🔄 Change {change_idx + 1}: field={field}")
                logger.info(f"      phone_number_id dans metadata: {phone_number_id}")
                logger.info(f"      metadata complet: {json.dumps(metadata, indent=6)}")
                
                # Chercher le compte
                if phone_number_id:
                    from app.services.account_service import get_account_by_phone_number_id
                    account = await get_account_by_phone_number_id(phone_number_id)
                    if account:
                        logger.info(f"      ✅ Compte trouvé: {account.get('name')} (id: {account.get('id')})")
                    else:
                        logger.error(f"      ❌ AUCUN COMPTE TROUVÉ pour phone_number_id={phone_number_id}")
                else:
                    logger.warning(f"      ⚠️ Pas de phone_number_id dans metadata!")
                
                # Vérifier les messages
                messages = value.get("messages", [])
                statuses = value.get("statuses", [])
                logger.info(f"      Messages: {len(messages)}, Statuses: {len(statuses)}")
        
        return {
            "status": "debug_received",
            "entries_count": len(entries),
            "message": "Check server logs for full webhook structure"
        }
    
    except Exception as e:
        logger.error(f"❌ Error in debug endpoint: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}