"""
Routes de webhooks WhatsApp
Gère la vérification et la réception des événements WhatsApp
"""
import hmac
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from starlette.responses import Response

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.metrics import webhook_fallback_inmemory_total
from app.core.permissions import CurrentUser
from app.core.rate_limit import limiter
from app.core.webhook_security import verify_meta_signature
from app.services.account_service import get_account_by_verify_token, get_all_accounts
from app.services.message_service import handle_incoming_message
from app.services.webhook_event_service import enqueue_webhook_event

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
        # Vérifier le token global - comparaison timing-safe pour éviter
        # toute fuite par mesure de temps sur la longueur ou le contenu.
        if (
            settings.WHATSAPP_VERIFY_TOKEN
            and token
            and hmac.compare_digest(token, settings.WHATSAPP_VERIFY_TOKEN)
        ):
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
@limiter.limit(settings.RATE_LIMIT_WEBHOOK)
async def whatsapp_webhook(request: Request, response: Response):
    """
    Endpoint de réception des événements WhatsApp
    
    OPTIMISATION: Réponse HTTP immédiate (200 OK) puis traitement en arrière-plan.
    Cela évite les timeouts WhatsApp et améliore significativement les performances.
    
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
    import asyncio
    
    try:
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"📥 POST /webhook/whatsapp received from {client_ip}")

        # 1) Vérification HMAC SHA-256 (X-Hub-Signature-256) avec META_APP_SECRET.
        #    `verify_meta_signature` consomme et renvoie le raw body - on le
        #    réutilise pour le JSON parsing (request.body() ne peut pas être
        #    lu deux fois sur un stream).
        raw_body = await verify_meta_signature(request)

        try:
            data = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError as exc:
            logger.warning("Webhook payload non-JSON: %s", exc)
            raise HTTPException(status_code=400, detail="invalid_json")
        
        # Log détaillé pour debug - inclure la structure complète si nécessaire
        entries = data.get("entry", [])
        logger.info(
            f"📥 POST /whatsapp webhook received: object={data.get('object')}, "
            f"entries={len(entries)}"
        )
        
        # Compter les messages et statuts pour le log
        total_messages = 0
        total_statuses = 0
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                total_messages += len(value.get("messages", []))
                total_statuses += len(value.get("statuses", []))
        
        if total_messages > 0 or total_statuses > 0:
            logger.info(f"📨 Webhook contains {total_messages} message(s) and {total_statuses} status(es)")
        else:
            logger.warning("⚠️ Webhook received but no messages or statuses found")

        # ── Persistance durable du webhook ───────────────────────────────────
        # On INSERT le payload dans `webhook_events` puis on répond 200 OK
        # immédiatement. Un worker périodique consomme la file (cf.
        # `webhook_event_service.periodic_process_webhook_events`).
        # Avantage : aucun évènement n'est perdu si le process redémarre
        # entre la réponse à Meta et la fin du traitement métier.
        event_id = await enqueue_webhook_event(data)

        if event_id:
            return {"status": "queued", "event_id": str(event_id)}

        # Fallback : pas de pool PostgreSQL configuré (DATABASE_URL absent).
        # On retombe sur l'ancien comportement asyncio.create_task pour ne
        # pas casser les déploiements en mode "Supabase REST only".
        # Compteur Prometheus pour qu'on voie si on dérive vers ce mode dégradé
        # en prod (où DATABASE_URL est désormais requis - cf. main.py boot check).
        webhook_fallback_inmemory_total.labels(source="whatsapp").inc()
        logger.warning(
            "webhook enqueue indisponible (pas de pool PG) - fallback in-memory async"
        )

        async def process_webhook_background():
            try:
                await handle_incoming_message(data)
            except Exception as bg_error:
                logger.error(f"❌ Error processing webhook in background: {bg_error}", exc_info=True)
                try:
                    from app.api.routes_diagnostics import log_error_to_memory
                    log_error_to_memory(
                        "webhook_processing_background",
                        str(bg_error),
                        {
                            "client_ip": client_ip,
                            "data_keys": list(data.keys()) if data else []
                        }
                    )
                except:
                    pass

        asyncio.create_task(process_webhook_background())
        return {"status": "received"}

    except HTTPException:
        # On laisse remonter les 401/400/403 (signature invalide, JSON malformé,
        # etc.) pour que Meta voie le statut réel - sinon on masquerait une
        # mauvaise configuration sous un faux 200.
        raise
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
async def whatsapp_webhook_debug(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Endpoint de debug pour capturer et afficher les webhooks reçus.

    Désactivé par défaut. Pour l'activer:
      - WEBHOOK_DEBUG_ENABLED=true
      - APP_ENV != production (refusé en prod par sécurité)
      - Authentification Bearer requise (utilisateur de l'app)
    """
    if not settings.WEBHOOK_DEBUG_ENABLED or settings.is_production:
        raise HTTPException(status_code=404, detail="not_found")

    try:
        client_ip = request.client.host if request.client else "unknown"
        logger.info(
            f"🔍 DEBUG: POST /webhook/whatsapp/debug received from {client_ip} "
            f"(user={current_user.email})"
        )
        
        data = await request.json()

        # Payload complet en DEBUG uniquement (peut contenir des données
        # personnelles : numéros de téléphone, contenu de messages).
        logger.debug("[WEBHOOK DEBUG] payload complet: %s", json.dumps(data, ensure_ascii=False))

        entries = data.get("entry", [])
        logger.info("[WEBHOOK DEBUG] %d entry/entries", len(entries))

        all_accounts = await get_all_accounts()
        logger.info("[WEBHOOK DEBUG] %d compte(s) en base", len(all_accounts))

        for entry_idx, entry in enumerate(entries):
            changes = entry.get("changes", [])
            for change_idx, change in enumerate(changes):
                field = change.get("field")
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                phone_number_id = metadata.get("phone_number_id")
                messages = value.get("messages", [])
                statuses = value.get("statuses", [])

                logger.info(
                    "[WEBHOOK DEBUG] entry=%d change=%d field=%s phone_number_id=%s messages=%d statuses=%d",
                    entry_idx + 1,
                    change_idx + 1,
                    field,
                    phone_number_id,
                    len(messages),
                    len(statuses),
                )

                if phone_number_id:
                    from app.services.account_service import get_account_by_phone_number_id
                    account = await get_account_by_phone_number_id(phone_number_id)
                    if account:
                        logger.info(
                            "[WEBHOOK DEBUG] compte trouvé id=%s name=%s",
                            account.get("id"),
                            account.get("name"),
                        )
                    else:
                        logger.error(
                            "[WEBHOOK DEBUG] AUCUN COMPTE pour phone_number_id=%s",
                            phone_number_id,
                        )
                else:
                    logger.warning("[WEBHOOK DEBUG] phone_number_id manquant dans metadata")
        
        return {
            "status": "debug_received",
            "entries_count": len(entries),
            "message": "Check server logs for full webhook structure"
        }
    
    except Exception as e:
        logger.error(f"❌ Error in debug endpoint: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}