import os
from pathlib import Path

from dotenv import load_dotenv

BASE_PATH = Path(__file__).resolve()
dotenv_candidates = [
    BASE_PATH.parents[3] / ".env",          # repo root
    BASE_PATH.parents[2] / ".env",          # backend/.env
    BASE_PATH.parents[2] / "env" / ".env",  # backend/env/.env
]
loaded_any = False
for candidate in dotenv_candidates:
    if candidate.exists():
        load_dotenv(candidate, override=False)
        loaded_any = True

if not loaded_any:
    load_dotenv()

class Settings:
    # Supabase
    SUPABASE_URL: str | None = os.getenv("SUPABASE_URL")
    SUPABASE_KEY: str | None = os.getenv("SUPABASE_KEY")
    
    # WhatsApp (configuration de base)
    WHATSAPP_TOKEN: str | None = os.getenv("WHATSAPP_TOKEN")
    WHATSAPP_PHONE_ID: str | None = os.getenv("WHATSAPP_PHONE_ID")
    WHATSAPP_VERIFY_TOKEN: str | None = os.getenv("WHATSAPP_VERIFY_TOKEN")
    WHATSAPP_PHONE_NUMBER: str | None = os.getenv("WHATSAPP_PHONE_NUMBER")
    WHATSAPP_BUSINESS_ACCOUNT_ID: str | None = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")  # WABA ID
    
    # Meta App (pour les fonctionnalités avancées de l'API)
    META_APP_ID: str | None = os.getenv("META_APP_ID")
    META_APP_SECRET: str | None = os.getenv("META_APP_SECRET")
    META_BUSINESS_ID: str | None = os.getenv("META_BUSINESS_ID")  # Business Manager ID
    
    # Gemini Bot
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    HUMAN_BACKUP_NUMBER: str | None = os.getenv("HUMAN_BACKUP_NUMBER")

    # Prometheus
    PROMETHEUS_ENABLED: bool = os.getenv("PROMETHEUS_ENABLED", "true").lower() == "true"
    PROMETHEUS_METRICS_PATH: str = os.getenv("PROMETHEUS_METRICS_PATH", "/metrics")
    PROMETHEUS_APP_LABEL: str = os.getenv("PROMETHEUS_APP_LABEL", "whatsapp_inbox_api")
    
    # Template Header Strategy (pour les templates avec HEADER IMAGE)
    # Valeurs possibles: "none", "empty_header", "omit_header"
    # - "none": Envoyer components=None (ne fonctionne pas pour HEADER IMAGE avec exemple fixe)
    # - "empty_header": Inclure un header avec l'URL de l'exemple fixe comme parameter (FONCTIONNE)
    # - "omit_header": Omettre complètement le header (ne devrait pas fonctionner)
    # NOTE: empty_header fonctionne mais les URLs WhatsApp peuvent expirer - pour une solution robuste,
    # il faudrait uploader l'image via l'API et utiliser media_id
    TEMPLATE_HEADER_STRATEGY: str = os.getenv("TEMPLATE_HEADER_STRATEGY", "empty_header")
    
    # Google Drive OAuth2 (optionnel)
    GOOGLE_DRIVE_CLIENT_ID: str | None = os.getenv("GOOGLE_DRIVE_CLIENT_ID")
    GOOGLE_DRIVE_CLIENT_SECRET: str | None = os.getenv("GOOGLE_DRIVE_CLIENT_SECRET")
    GOOGLE_DRIVE_REDIRECT_URI: str = os.getenv("GOOGLE_DRIVE_REDIRECT_URI", "http://localhost:5174/api/auth/google-drive/callback")
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")

settings = Settings()