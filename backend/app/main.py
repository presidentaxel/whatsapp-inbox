from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_webhook import router as webhook_router
from app.api.routes_conversations import router as conversations_router
from app.api.routes_messages import router as messages_router
from app.api.routes_accounts import router as accounts_router
from app.api.routes_contacts import router as contacts_router
from app.api.routes_auth import router as auth_router
from app.api.routes_admin import router as admin_router

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

@app.get("/")
def root():
    return {"status": "ok", "message": "WhatsApp Inbox API running"}