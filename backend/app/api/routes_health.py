"""
Endpoint de health check pour monitorer l'état de l'application et ses dépendances.
"""
import asyncio
import logging
from datetime import datetime

import httpx
from fastapi import APIRouter

from app.core.config import settings
from app.core.db import supabase, supabase_execute
from app.core.circuit_breaker import get_all_circuit_breakers

router = APIRouter()
logger = logging.getLogger(__name__)


async def check_supabase() -> dict:
    """Vérifie la connexion à Supabase."""
    try:
        await asyncio.wait_for(
            supabase_execute(supabase.table("accounts").select("id").limit(1)),
            timeout=2.0
        )
        return {"status": "ok", "latency_ms": None}
    except asyncio.TimeoutError:
        return {"status": "timeout", "error": "Query took more than 2s"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def check_whatsapp_api() -> dict:
    """Vérifie la disponibilité de l'API WhatsApp."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            start = datetime.now()
            resp = await client.get("https://graph.facebook.com/v19.0/")
            latency = (datetime.now() - start).total_seconds() * 1000
            
            if resp.is_success or resp.status_code == 400:  # 400 est OK (pas de token fourni)
                return {"status": "ok", "latency_ms": round(latency, 2)}
            else:
                return {
                    "status": "error",
                    "error": f"HTTP {resp.status_code}",
                    "latency_ms": round(latency, 2)
                }
    except httpx.TimeoutException:
        return {"status": "timeout", "error": "Request took more than 2s"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def check_gemini_api() -> dict:
    """Vérifie la disponibilité de l'API Gemini."""
    if not settings.GEMINI_API_KEY:
        return {"status": "not_configured", "error": "GEMINI_API_KEY not set"}
    
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            start = datetime.now()
            resp = await client.get(
                f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}",
                params={"key": settings.GEMINI_API_KEY}
            )
            latency = (datetime.now() - start).total_seconds() * 1000
            
            if resp.is_success:
                return {"status": "ok", "latency_ms": round(latency, 2)}
            else:
                return {
                    "status": "error",
                    "error": f"HTTP {resp.status_code}",
                    "latency_ms": round(latency, 2)
                }
    except httpx.TimeoutException:
        return {"status": "timeout", "error": "Request took more than 2s"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/health")
async def health_check():
    """
    Vérifie l'état de santé de l'application et de ses dépendances.
    
    Returns:
        {
            "status": "ok" | "degraded" | "error",
            "timestamp": "ISO timestamp",
            "dependencies": {
                "supabase": {...},
                "whatsapp": {...},
                "gemini": {...}
            },
            "circuit_breakers": {...}
        }
    """
    # Exécuter tous les checks en parallèle
    supabase_status, whatsapp_status, gemini_status = await asyncio.gather(
        check_supabase(),
        check_whatsapp_api(),
        check_gemini_api(),
        return_exceptions=True
    )
    
    # Gestion des exceptions
    if isinstance(supabase_status, Exception):
        supabase_status = {"status": "error", "error": str(supabase_status)}
    if isinstance(whatsapp_status, Exception):
        whatsapp_status = {"status": "error", "error": str(whatsapp_status)}
    if isinstance(gemini_status, Exception):
        gemini_status = {"status": "error", "error": str(gemini_status)}
    
    dependencies = {
        "supabase": supabase_status,
        "whatsapp": whatsapp_status,
        "gemini": gemini_status,
    }
    
    # Déterminer le statut global
    all_ok = all(
        dep.get("status") in ["ok", "not_configured"]
        for dep in dependencies.values()
    )
    any_error = any(
        dep.get("status") == "error"
        for dep in dependencies.values()
    )
    
    if all_ok:
        overall_status = "ok"
    elif any_error:
        overall_status = "error"
    else:
        overall_status = "degraded"
    
    return {
        "status": overall_status,
        "timestamp": datetime.now().isoformat(),
        "dependencies": dependencies,
        "circuit_breakers": get_all_circuit_breakers(),
    }


@router.get("/health/live")
async def liveness_probe():
    """
    Liveness probe pour Kubernetes/Docker.
    Retourne 200 si l'application est démarrée.
    """
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness_probe():
    """
    Readiness probe pour Kubernetes/Docker.
    Retourne 200 si l'application est prête à recevoir du trafic.
    """
    # Vérifier uniquement Supabase (critique)
    supabase_status = await check_supabase()
    
    if supabase_status["status"] == "ok":
        return {"status": "ready"}
    else:
        return {"status": "not_ready", "reason": supabase_status}, 503

