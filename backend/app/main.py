from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.routes_webhook import router as webhook_router
from app.api.routes_conversations import router as conversations_router
from app.api.routes_messages import router as messages_router
from app.api.routes_accounts import router as accounts_router
from app.api.routes_contacts import router as contacts_router
from app.api.routes_auth import router as auth_router
from app.api.routes_admin import router as admin_router
from app.api.routes_bot import router as bot_router
from app.api.routes_health import router as health_router
from app.core.config import settings
from app.core.http_client import close_http_client

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tu pourras restreindre plus tard
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router, prefix="/webhook", tags=["webhook"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(conversations_router, prefix="/conversations", tags=["conversations"])
app.include_router(messages_router, prefix="/messages", tags=["messages"])
app.include_router(accounts_router, prefix="/accounts", tags=["accounts"])
app.include_router(contacts_router, prefix="/contacts", tags=["contacts"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(bot_router, prefix="/bot", tags=["bot"])
app.include_router(health_router, tags=["health"])

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


@app.on_event("shutdown")
async def shutdown_event():
    """Nettoyage propre lors de l'arrêt de l'application."""
    await close_http_client()


@app.get("/")
def root():
    return {"status": "ok", "message": "WhatsApp Inbox API running"}