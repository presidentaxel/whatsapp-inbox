from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
import logging

logger = logging.getLogger(__name__)

# Routes existantes
from app.api.routes_webhook import router as webhook_router
from app.api.routes_webhook_setup import router as webhook_setup_router
from app.api.routes_conversations import router as conversations_router
from app.api.routes_messages import router as messages_router
from app.api.routes_accounts import router as accounts_router
from app.api.routes_contacts import router as contacts_router
from app.api.routes_auth import router as auth_router
from app.api.routes_admin import router as admin_router
from app.api.routes_bot import router as bot_router
from app.api.routes_qa import router as qa_router
from app.api.routes_playground_flows import router as playground_flows_router
from app.api.routes_health import router as health_router
from app.api.routes_app import router as app_router
from app.api.routes_invitations import router as invitations_router
from app.api.routes_users import router as users_router
from app.api.routes_diagnostics import router as diagnostics_router
from app.api.routes_google_drive import router as google_drive_router
from app.api.routes_broadcast import router as broadcast_router

# Nouvelles routes WhatsApp API complète
from app.api.routes_whatsapp_messages import router as whatsapp_messages_router
from app.api.routes_whatsapp_media import router as whatsapp_media_router
from app.api.routes_whatsapp_phone import router as whatsapp_phone_router
from app.api.routes_whatsapp_templates import router as whatsapp_templates_router
from app.api.routes_whatsapp_profile import router as whatsapp_profile_router
from app.api.routes_whatsapp_waba import router as whatsapp_waba_router
from app.api.routes_whatsapp_utils import router as whatsapp_utils_router

from app.core.config import settings
from app.core.http_client import close_http_client
from app.core.pg import init_pool, close_pool
from app.services.profile_picture_service import periodic_profile_picture_update
from app.services.media_background_service import periodic_media_backfill
from app.services.pinned_notification_service import periodic_pin_notification_check
from app.services.pending_template_service import resume_pending_templates_on_startup, periodic_template_check
from app.services.flow_runtime_service import periodic_playground_flow_delays
from app.services.broadcast_service import periodic_scheduled_broadcasts
from app.services.playground_flow_service import periodic_playground_scheduled_launches

app = FastAPI(
    title="WhatsApp Inbox API",
    description="API complète pour gérer votre inbox WhatsApp Business avec toutes les fonctionnalités de l'API Cloud",
    version="2.0.0",
)

_cors_origins_env = settings.CORS_ORIGINS if hasattr(settings, "CORS_ORIGINS") and settings.CORS_ORIGINS else None
# Strip whitespace so "a, b, c" matches browser Origin headers (exact match, no leading space).
_cors_origins = (
    [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
    if _cors_origins_env
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes existantes
app.include_router(webhook_router, prefix="/webhook")
app.include_router(webhook_setup_router)
app.include_router(auth_router, prefix="/auth")
app.include_router(conversations_router, prefix="/conversations")
app.include_router(messages_router, prefix="/messages")
app.include_router(accounts_router, prefix="/accounts")
app.include_router(google_drive_router)
app.include_router(contacts_router, prefix="/contacts")
app.include_router(admin_router, prefix="/admin")
app.include_router(bot_router, prefix="/bot")
app.include_router(qa_router, prefix="/bot/qa")
app.include_router(playground_flows_router, prefix="/bot/playground-flows")
app.include_router(health_router)
# Diagnostics accessible directement (pas sous /api car nginx intercepte)
# Utiliser un préfixe spécial qui n'est pas intercepté
app.include_router(diagnostics_router, prefix="/_diagnostics")
app.include_router(app_router, prefix="/app")
app.include_router(invitations_router, prefix="/invitations")
app.include_router(users_router, prefix="/admin/users")
app.include_router(broadcast_router, prefix="/broadcast")

# Nouvelles routes WhatsApp API complète
# Note: Pas de préfixe /api ici car Caddy le retire déjà avec uri strip_prefix /api
app.include_router(whatsapp_messages_router)
app.include_router(whatsapp_media_router)
app.include_router(whatsapp_phone_router)
app.include_router(whatsapp_templates_router)
app.include_router(whatsapp_profile_router)
app.include_router(whatsapp_waba_router)
app.include_router(whatsapp_utils_router)

if settings.PROMETHEUS_ENABLED:
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers={settings.PROMETHEUS_METRICS_PATH},
    )
    instrumentator.instrument(app).expose(
        app,
        include_in_schema=False,
        endpoint=settings.PROMETHEUS_METRICS_PATH,
    )


# Références aux tâches périodiques pour pouvoir les annuler proprement
_periodic_tasks = []

@app.on_event("startup")
async def startup_event():
    """Démarrage de l'application - lance les tâches périodiques."""
    import asyncio
    # Pool PostgreSQL direct (si DATABASE_URL est défini)
    await init_pool()
    
    # Reprendre les templates en attente (APPROVED ou PENDING) au démarrage
    try:
        await resume_pending_templates_on_startup()
    except Exception as e:
        logger.error(f"❌ Erreur lors de la reprise des templates au démarrage: {e}", exc_info=True)
    
    # Démarrer la tâche périodique de mise à jour des images de profil
    task1 = asyncio.create_task(periodic_profile_picture_update())
    _periodic_tasks.append(task1)
    logger.info("✅ Profile picture periodic update task started")
    
    # Démarrer la tâche périodique de téléchargement des médias manquants
    task2 = asyncio.create_task(periodic_media_backfill())
    _periodic_tasks.append(task2)
    logger.info("✅ Media background backfill task started")
    
    # Démarrer la tâche périodique de vérification des notifications d'épinglage
    task3 = asyncio.create_task(periodic_pin_notification_check())
    _periodic_tasks.append(task3)
    logger.info("✅ Pin notification periodic check task started")
    
    # Démarrer la tâche périodique de vérification des templates en attente
    task4 = asyncio.create_task(periodic_template_check())
    _periodic_tasks.append(task4)
    logger.info("✅ Pending templates periodic check task started")

    task5 = asyncio.create_task(periodic_playground_flow_delays())
    _periodic_tasks.append(task5)
    logger.info("✅ Playground flow delay wake task started")

    task6 = asyncio.create_task(periodic_scheduled_broadcasts())
    _periodic_tasks.append(task6)
    logger.info("✅ Scheduled broadcast campaigns task started")

    task7 = asyncio.create_task(periodic_playground_scheduled_launches())
    _periodic_tasks.append(task7)
    logger.info("✅ Playground scheduled flow launches task started")


@app.on_event("shutdown")
async def shutdown_event():
    """Nettoyage propre lors de l'arrêt de l'application."""
    import asyncio
    logger.info("🛑 Shutting down application, cancelling periodic tasks...")
    
    # Annuler toutes les tâches périodiques proprement
    for task in _periodic_tasks:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass  # C'est normal lors du shutdown
    
    # Fermer le client HTTP et le pool PostgreSQL
    await close_http_client()
    await close_pool()
    logger.info("✅ Shutdown complete")


@app.get("/")
def root():
    return {"status": "ok", "message": "WhatsApp Inbox API running"}