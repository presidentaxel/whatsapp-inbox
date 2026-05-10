"""
Configuration centralisée de l'application.

Utilise `pydantic-settings` :
- typage strict (les conversions int/bool sont vérifiées au boot)
- introspection facile pour les tests (`Settings(**overrides)`)
- les `.env` sont toujours chargés en amont via `python-dotenv` pour préserver
  la recherche multi-emplacements historique (repo root, backend/, backend/env/).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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


def _normalize_gemini_model_id(model: str) -> str:
    """
    Remplace les IDs retirés pour les nouveaux comptes / projets (API Generative Language).
    Voir https://ai.google.dev/gemini-api/docs/deprecations
    """
    m = (model or "").strip()
    if not m:
        return m
    legacy = {
        "gemini-2.0-flash": "gemini-2.5-flash",
        "gemini-2.0-flash-001": "gemini-2.5-flash",
        "gemini-2.0-flash-lite": "gemini-2.5-flash-lite",
        "gemini-2.0-flash-lite-001": "gemini-2.5-flash-lite",
    }
    return legacy.get(m.lower(), m)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=True,
        extra="ignore",
    )

    # ─── Supabase ──────────────────────────────────────────────────────────────
    SUPABASE_URL: str | None = None
    SUPABASE_KEY: str | None = None

    # PostgreSQL direct (optionnel en dev, requis en prod - cf. main.py boot check).
    # Format: postgresql://user:password@host:port/dbname
    DATABASE_URL: str | None = None
    # Limite typique du pooler Supabase *session* : ~15 clients par user → rester en dessous.
    PG_POOL_MIN_SIZE: int = Field(default=1, ge=1, le=50)
    PG_POOL_MAX_SIZE: int = Field(default=5, ge=1, le=100)

    # ─── WhatsApp ──────────────────────────────────────────────────────────────
    WHATSAPP_TOKEN: str | None = None
    WHATSAPP_PHONE_ID: str | None = None
    WHATSAPP_VERIFY_TOKEN: str | None = None
    WHATSAPP_PHONE_NUMBER: str | None = None
    WHATSAPP_BUSINESS_ACCOUNT_ID: str | None = None  # WABA ID

    # ─── Meta App ──────────────────────────────────────────────────────────────
    META_APP_ID: str | None = None
    META_APP_SECRET: str | None = None
    META_BUSINESS_ID: str | None = None  # Business Manager ID

    # ─── Gemini Bot ────────────────────────────────────────────────────────────
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-1.5-flash"
    # Vide = même modèle que GEMINI_MODEL.
    GEMINI_TRANSCRIPTION_MODEL: str = ""
    GEMINI_AUDIO_TRANSCRIPTION_ENABLED: bool = True
    GEMINI_AUDIO_TRANSCRIPTION_MAX_BYTES: int = 20 * 1024 * 1024
    HUMAN_BACKUP_NUMBER: str | None = None
    GEMINI_CONVERSATION_HISTORY_LIMIT: int = 200
    GEMINI_CONVERSATION_HISTORY_MAX_CHARS: int = 0
    GEMINI_FLOW_RECENT_CONTEXT_CHARS: int = 32000

    # ─── Agent outbound (inbox : boucle Gemini + outils noyau, séparé d’Axelia) ─
    AGENT_OUTBOUND_GEMINI_TOOLS_ENABLED: bool = False
    AGENT_OUTBOUND_GEMINI_READ_TIMEOUT_S: float = 45.0

    # ─── Axelia (hub IA) ───────────────────────────────────────────────────────
    AXELIA_FAST_MODEL: str = ""
    AXELIA_PRO_MODEL: str = "gemini-2.5-pro"
    AXELIA_DIFFICULTY_THRESHOLD: float = 0.42
    AXELIA_CLASSIFY_READ_TIMEOUT: float = 42.0
    AXELIA_CLASSIFY_FALLBACK_DIFFICULTY: float = 0.52

    # ─── Prometheus ────────────────────────────────────────────────────────────
    PROMETHEUS_ENABLED: bool = True
    PROMETHEUS_METRICS_PATH: str = "/metrics"
    PROMETHEUS_APP_LABEL: str = "whatsapp_inbox_api"
    METRICS_AUTH_TOKEN: str | None = None

    # ─── Templates ─────────────────────────────────────────────────────────────
    # Valeurs possibles: "none" | "empty_header" | "omit_header"
    TEMPLATE_HEADER_STRATEGY: str = "empty_header"

    # ─── Google Drive OAuth2 ───────────────────────────────────────────────────
    GOOGLE_DRIVE_CLIENT_ID: str | None = None
    GOOGLE_DRIVE_CLIENT_SECRET: str | None = None
    GOOGLE_DRIVE_REDIRECT_URI: str = "http://localhost:5174/api/auth/google-drive/callback"

    # ─── URLs publiques ────────────────────────────────────────────────────────
    BACKEND_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:5173"

    # ─── Médias ────────────────────────────────────────────────────────────────
    # Limite Supabase Storage : 200 MB par défaut.
    MAX_MEDIA_UPLOAD_SIZE: int = 209_715_200

    # ─── Environnement ─────────────────────────────────────────────────────────
    # "development" | "production" | "test"
    APP_ENV: str = "development"

    # ─── CORS ──────────────────────────────────────────────────────────────────
    # Listes séparées par virgules. `CORS_ORIGINS` sert d'override universel.
    CORS_ORIGINS_DEV: str | None = (
        "http://localhost:5173,http://localhost:5174,"
        "http://127.0.0.1:5173,http://127.0.0.1:5174"
    )
    CORS_ORIGINS_PROD: str | None = None
    CORS_ORIGINS: str | None = None

    # ─── Sécurité webhook Meta ─────────────────────────────────────────────────
    WEBHOOK_SIGNATURE_REQUIRED: bool = True
    WEBHOOK_DEBUG_ENABLED: bool = False

    # ─── Rate limiting (slowapi) ───────────────────────────────────────────────
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT: str = "120/minute"
    RATE_LIMIT_AUTH: str = "20/minute"
    RATE_LIMIT_WEBHOOK: str = "600/minute"
    RATE_LIMIT_AI: str = "30/minute"

    # ─── Validators ────────────────────────────────────────────────────────────
    @field_validator("APP_ENV", mode="before")
    @classmethod
    def _normalize_app_env(cls, v: str | None) -> str:
        return (v or "development").strip().lower()

    @field_validator("GEMINI_MODEL", "GEMINI_TRANSCRIPTION_MODEL", mode="after")
    @classmethod
    def _normalize_gemini(cls, v: str) -> str:
        return _normalize_gemini_model_id(v)

    @field_validator("AXELIA_FAST_MODEL", mode="after")
    @classmethod
    def _normalize_axelia_fast(cls, v: str) -> str:
        # Si AXELIA_FAST_MODEL n'est pas explicitement défini, on retombe sur
        # GEMINI_MODEL. Comme on est en "after", on n'a pas accès aux autres
        # champs ; le fallback passe donc par `os.getenv` direct (parité avec
        # l'ancien comportement).
        if v:
            return _normalize_gemini_model_id(v)
        fallback = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
        return _normalize_gemini_model_id(fallback)

    @field_validator("AXELIA_PRO_MODEL", mode="after")
    @classmethod
    def _normalize_axelia_pro(cls, v: str) -> str:
        return _normalize_gemini_model_id(v) if v else "gemini-2.5-pro"

    # ─── Properties dérivées ───────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def cors_origins(self) -> list[str]:
        """
        Liste effective d'origines CORS pour l'environnement courant.

        Précédence:
          1. `CORS_ORIGINS` (override universel) si défini
          2. `CORS_ORIGINS_PROD` si APP_ENV=production
          3. `CORS_ORIGINS_DEV` sinon
        """
        raw = self.CORS_ORIGINS
        if not raw:
            raw = self.CORS_ORIGINS_PROD if self.is_production else self.CORS_ORIGINS_DEV
        if not raw:
            return []
        return [o.strip() for o in raw.split(",") if o.strip()]


settings = Settings()
