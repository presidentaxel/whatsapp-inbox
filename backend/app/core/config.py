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
    SUPABASE_URL: str | None = os.getenv("SUPABASE_URL")
    SUPABASE_KEY: str | None = os.getenv("SUPABASE_KEY")
    WHATSAPP_TOKEN: str | None = os.getenv("WHATSAPP_TOKEN")
    WHATSAPP_PHONE_ID: str | None = os.getenv("WHATSAPP_PHONE_ID")
    WHATSAPP_VERIFY_TOKEN: str | None = os.getenv("WHATSAPP_VERIFY_TOKEN")
    WHATSAPP_PHONE_NUMBER: str | None = os.getenv("WHATSAPP_PHONE_NUMBER")
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    HUMAN_BACKUP_NUMBER: str | None = os.getenv("HUMAN_BACKUP_NUMBER")

    PROMETHEUS_ENABLED: bool = os.getenv("PROMETHEUS_ENABLED", "true").lower() == "true"
    PROMETHEUS_METRICS_PATH: str = os.getenv("PROMETHEUS_METRICS_PATH", "/metrics")
    PROMETHEUS_APP_LABEL: str = os.getenv("PROMETHEUS_APP_LABEL", "whatsapp_inbox_api")

settings = Settings()