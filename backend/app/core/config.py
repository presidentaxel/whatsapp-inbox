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


class Settings:
    # Supabase
    SUPABASE_URL: str | None = os.getenv("SUPABASE_URL")
    SUPABASE_KEY: str | None = os.getenv("SUPABASE_KEY")

    # PostgreSQL direct (optionnel). Si défini, le backend utilise asyncpg au lieu de l'API Supabase pour les requêtes DB.
    # Format: postgresql://user:password@host:port/dbname (ex: Supabase Database → Connection string, mode Session ou Transaction)
    DATABASE_URL: str | None = os.getenv("DATABASE_URL")
    
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
    GEMINI_MODEL: str = _normalize_gemini_model_id(os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))
    # Transcription audio : ex. gemini-2.5-flash ou gemini-2.5-flash-lite (gemini-2.0-flash est mappé automatiquement).
    # Vide = même modèle que GEMINI_MODEL.
    GEMINI_TRANSCRIPTION_MODEL: str = _normalize_gemini_model_id(
        (os.getenv("GEMINI_TRANSCRIPTION_MODEL") or "").strip()
    )
    GEMINI_AUDIO_TRANSCRIPTION_ENABLED: bool = (
        os.getenv("GEMINI_AUDIO_TRANSCRIPTION_ENABLED", "true").lower() == "true"
    )
    GEMINI_AUDIO_TRANSCRIPTION_MAX_BYTES: int = int(
        os.getenv("GEMINI_AUDIO_TRANSCRIPTION_MAX_BYTES", str(20 * 1024 * 1024)) or str(20 * 1024 * 1024)
    )
    HUMAN_BACKUP_NUMBER: str | None = os.getenv("HUMAN_BACKUP_NUMBER")
    # Contexte conversation : messages chargés depuis la DB (bot + nœuds flow / {{flow_recent_user_text}})
    GEMINI_CONVERSATION_HISTORY_LIMIT: int = max(
        1,
        int(os.getenv("GEMINI_CONVERSATION_HISTORY_LIMIT", "200") or "200"),
    )
    # 0 = pas de troncature après assemblage du transcript (sinon coupe le début, garde la fin)
    GEMINI_CONVERSATION_HISTORY_MAX_CHARS: int = int(
        os.getenv("GEMINI_CONVERSATION_HISTORY_MAX_CHARS", "0") or "0"
    )
    # Contexte « messages récents » injecté dans generate_flow_gemini_keyword (en plus du dernier message)
    GEMINI_FLOW_RECENT_CONTEXT_CHARS: int = max(
        1200,
        int(os.getenv("GEMINI_FLOW_RECENT_CONTEXT_CHARS", "32000") or "32000"),
    )

    # Axelia (hub IA) — routage fast / pro (évaluation de difficulté avec le modèle rapide)
    AXELIA_FAST_MODEL: str = _normalize_gemini_model_id(
        (os.getenv("AXELIA_FAST_MODEL") or "").strip() or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    )
    AXELIA_PRO_MODEL: str = _normalize_gemini_model_id(
        (os.getenv("AXELIA_PRO_MODEL") or "").strip() or "gemini-2.5-pro"
    )
    AXELIA_DIFFICULTY_THRESHOLD: float = float(
        os.getenv("AXELIA_DIFFICULTY_THRESHOLD", "0.42") or "0.42"
    )
    # Classification (un seul appel, sans retry HTTP) — latence Gemini variable
    AXELIA_CLASSIFY_READ_TIMEOUT: float = float(
        os.getenv("AXELIA_CLASSIFY_READ_TIMEOUT", "42") or "42"
    )
    # Si classify échoue (timeout, etc.) : score utilisé pour le routage (>= seuil → pro)
    AXELIA_CLASSIFY_FALLBACK_DIFFICULTY: float = float(
        os.getenv("AXELIA_CLASSIFY_FALLBACK_DIFFICULTY", "0.52") or "0.52"
    )

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
    
    # Media upload limits (en bytes)
    # Limite Supabase Storage: 200MB par défaut (suffisant pour la plupart des vidéos WhatsApp)
    # Peut être configurée via la variable d'environnement MAX_MEDIA_UPLOAD_SIZE
    MAX_MEDIA_UPLOAD_SIZE: int = int(os.getenv("MAX_MEDIA_UPLOAD_SIZE", "209715200"))  # 200MB par défaut

    # CORS: comma-separated list of allowed origins. Defaults to "*" (all) if not set.
    # Whitespace around commas is trimmed. Example: "https://a.com, http://localhost:3000"
    CORS_ORIGINS: str | None = os.getenv("CORS_ORIGINS")

settings = Settings()