import os
from pathlib import Path

from dotenv import load_dotenv

DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(DOTENV_PATH, override=False)

class Settings:
    SUPABASE_URL: str | None = os.getenv("SUPABASE_URL")
    SUPABASE_KEY: str | None = os.getenv("SUPABASE_KEY")
    WHATSAPP_TOKEN: str | None = os.getenv("WHATSAPP_TOKEN")
    WHATSAPP_PHONE_ID: str | None = os.getenv("WHATSAPP_PHONE_ID")
    WHATSAPP_VERIFY_TOKEN: str | None = os.getenv("WHATSAPP_VERIFY_TOKEN")
    WHATSAPP_PHONE_NUMBER: str | None = os.getenv("WHATSAPP_PHONE_NUMBER")

settings = Settings()