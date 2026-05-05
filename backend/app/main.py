import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

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
from app.api.routes_axelia import router as axelia_router

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
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.services.profile_picture_service import periodic_profile_picture_update
from app.services.media_background_service import periodic_media_backfill
from app.services.pinned_notification_service import periodic_pin_notification_check
from app.services.pending_template_service import resume_pending_templates_on_startup, periodic_template_check
from app.services.flow_runtime_service import periodic_playground_flow_delays
from app.services.broadcast_service import periodic_scheduled_broadcasts
from app.services.playground_flow_service import periodic_playground_scheduled_launches
from app.services.webhook_event_service import periodic_process_webhook_events

# ─── Boot checks ──────────────────────────────────────────────────────────────
# En production, certaines variables sont structurellement nécessaires (file
# durable webhook events, fallback in-memory dégradé). On préfère un crash
# explicite à un comportement silencieusement dégradé.
if settings.is_production and not settings.DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL est requis en production : la file durable de webhooks "
        "(`webhook_events`) en dépend. Configure DATABASE_URL avant de démarrer."
    )


# ─── Lifespan ────────────────────────────────────────────────────────────────
# Remplace les anciens `@app.on_event("startup")` / `"shutdown"` (dépréciés
# depuis FastAPI 0.93). Le `lifespan` est l'API officielle pour gérer le cycle
# de vie : init du pool PG, lancement des tâches périodiques, puis cleanup.
@asynccontextmanager
async def lifespan(app: FastAPI):
    periodic_tasks: list[asyncio.Task] = []

    await init_pool()

    try:
        await resume_pending_templates_on_startup()
    except Exception as e:
        logger.error("Erreur lors de la reprise des templates au démarrage: %s", e, exc_info=True)

    background_jobs = (
        ("profile picture update", periodic_profile_picture_update),
        ("media background backfill", periodic_media_backfill),
        ("pin notification check", periodic_pin_notification_check),
        ("pending templates check", periodic_template_check),
        ("playground flow delays", periodic_playground_flow_delays),
        ("scheduled broadcasts", periodic_scheduled_broadcasts),
        ("playground scheduled launches", periodic_playground_scheduled_launches),
        ("webhook events queue worker", periodic_process_webhook_events),
    )
    for name, coro in background_jobs:
        task = asyncio.create_task(coro(), name=name)
        periodic_tasks.append(task)
        logger.info("Tâche périodique démarrée: %s", name)

    app.state.periodic_tasks = periodic_tasks

    try:
        yield
    finally:
        logger.info("Shutdown : annulation des tâches périodiques…")
        for task in periodic_tasks:
            if not task.done():
                task.cancel()
        for task in periodic_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning("Erreur en fermant la tâche %s: %s", task.get_name(), e)

        await close_http_client()
        await close_pool()
        logger.info("Shutdown complete")


app = FastAPI(
    title="WhatsApp Inbox API",
    description="API complète pour gérer votre inbox WhatsApp Business avec toutes les fonctionnalités de l'API Cloud",
    version="2.0.0",
    lifespan=lifespan,
)

# ─── Rate limiting (SlowAPI) ──────────────────────────────────────────────────
# Le limiter est exposé sur `app.state.limiter` pour permettre l'usage de
# `@limiter.limit("…")` sur n'importe quelle route.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ─── CORS ────────────────────────────────────────────────────────────────────
# Liste calculée selon `APP_ENV` (cf. config.py → cors_origins).
# - production : utilise CORS_ORIGINS_PROD (ou CORS_ORIGINS si override)
# - sinon       : utilise CORS_ORIGINS_DEV
_cors_origins = settings.cors_origins
if not _cors_origins:
    if settings.is_production:
        # En prod, une liste CORS vide rend l'API silencieusement injoignable
        # (le navigateur bloque tout). On préfère un crash explicite au boot
        # pour que l'erreur de config soit visible immédiatement.
        raise RuntimeError(
            "CORS_ORIGINS_PROD (ou CORS_ORIGINS) est vide alors que APP_ENV=production. "
            "Configure au moins une origine autorisée avant de démarrer l'API."
        )
    logger.warning(
        "Aucune origine CORS configurée - fallback sur localhost dev. "
        "Définis CORS_ORIGINS_DEV pour personnaliser."
    )
    _cors_origins = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ]

logger.info(
    "CORS configuré (APP_ENV=%s) : %d origine(s)",
    settings.APP_ENV,
    len(_cors_origins),
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
app.include_router(axelia_router)

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

    # Si METRICS_AUTH_TOKEN est défini, on protège /metrics par un middleware
    # léger qui exige `Authorization: Bearer <token>`. Sans token, on suppose
    # que la restriction se fait au niveau du reverse proxy (allowlist IP).
    if settings.METRICS_AUTH_TOKEN:
        _metrics_path = settings.PROMETHEUS_METRICS_PATH
        _expected = f"Bearer {settings.METRICS_AUTH_TOKEN}"

        @app.middleware("http")
        async def _protect_metrics(request: Request, call_next):
            if request.url.path == _metrics_path:
                auth = request.headers.get("authorization") or ""
                if auth != _expected:
                    from fastapi.responses import JSONResponse
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={"detail": "unauthorized"},
                    )
            return await call_next(request)

        logger.info("Endpoint %s protégé par Bearer token", _metrics_path)


@app.get("/")
def root():
    return {"status": "ok", "message": "WhatsApp Inbox API running"}