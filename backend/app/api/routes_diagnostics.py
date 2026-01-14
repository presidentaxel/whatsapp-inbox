"""
Routes de diagnostic pour voir l'état du système et les erreurs récentes
Utile quand on n'a pas accès aux logs Render directement
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.db import supabase, supabase_execute
from app.services.account_service import get_all_accounts

router = APIRouter(tags=["Diagnostics"])
logger = logging.getLogger(__name__)

# Stocker les dernières erreurs en mémoire (simple, pour diagnostic)
_recent_errors: List[Dict] = []
_max_errors = 100


def log_error_to_memory(error_type: str, message: str, details: Optional[Dict] = None):
    """Enregistre une erreur en mémoire pour diagnostic"""
    error_entry = {
        "timestamp": datetime.now().isoformat(),
        "type": error_type,
        "message": message,
        "details": details or {}
    }
    _recent_errors.append(error_entry)
    # Garder seulement les N dernières erreurs
    if len(_recent_errors) > _max_errors:
        _recent_errors.pop(0)


@router.get("/diagnostics/webhook-status")
async def webhook_status():
    """
    Retourne l'état des webhooks et des messages récents
    """
    try:
        # Vérifier les messages récents (50 derniers)
        messages_result = await supabase_execute(
            supabase.table("messages")
            .select("id, direction, content_text, timestamp, wa_message_id, message_type, conversation_id")
            .order("timestamp", desc=True)
            .limit(50)
        )
        
        messages = messages_result.data if messages_result.data else []
        
        # Séparer entrants et sortants
        incoming = [m for m in messages if m.get("direction") == "inbound"]
        outgoing = [m for m in messages if m.get("direction") == "outbound"]
        
        # Messages des dernières 24h
        yesterday = datetime.now() - timedelta(days=1)
        recent_result = await supabase_execute(
            supabase.table("messages")
            .select("id", count="exact")
            .gte("timestamp", yesterday.isoformat())
        )
        recent_count = recent_result.count if hasattr(recent_result, 'count') else len(recent_result.data) if recent_result.data else 0
        
        # Messages entrants de la dernière heure (CRITIQUE pour le diagnostic)
        one_hour_ago = datetime.now() - timedelta(hours=1)
        incoming_last_hour_result = await supabase_execute(
            supabase.table("messages")
            .select("id, timestamp, content_text, wa_message_id")
            .eq("direction", "inbound")
            .gte("timestamp", one_hour_ago.isoformat())
            .order("timestamp", desc=True)
        )
        incoming_last_hour = incoming_last_hour_result.data if incoming_last_hour_result.data else []
        
        # Messages entrants des dernières 24h
        incoming_last_24h_result = await supabase_execute(
            supabase.table("messages")
            .select("id", count="exact")
            .eq("direction", "inbound")
            .gte("timestamp", yesterday.isoformat())
        )
        incoming_last_24h_count = incoming_last_24h_result.count if hasattr(incoming_last_24h_result, 'count') else len(incoming_last_24h_result.data) if incoming_last_24h_result.data else 0
        
        # Vérifier les comptes
        accounts = await get_all_accounts()
        
        # Dernier message entrant (toutes périodes confondues)
        last_incoming = incoming[0] if incoming else None
        
        return {
            "status": "ok",
            "messages": {
                "total_recent": len(messages),
                "incoming_recent": len(incoming),
                "outgoing_recent": len(outgoing),
                "last_24h": recent_count,
                "incoming_last_24h": incoming_last_24h_count,
                "incoming_last_hour": len(incoming_last_hour),
                "incoming_last_hour_list": [
                    {
                        "id": m.get("id"),
                        "timestamp": m.get("timestamp"),
                        "content_preview": (m.get("content_text") or "")[:50]
                    }
                    for m in incoming_last_hour[:10]
                ],
                "last_incoming_message": {
                    "id": last_incoming.get("id"),
                    "timestamp": last_incoming.get("timestamp"),
                    "content_preview": (last_incoming.get("content_text") or "")[:50] if last_incoming else None
                } if last_incoming else None,
                "latest_incoming": incoming[:5] if incoming else [],
                "latest_outgoing": outgoing[:5] if outgoing else []
            },
            "accounts": {
                "total": len(accounts),
                "active": len([a for a in accounts if a.get("is_active")]),
                "list": [
                    {
                        "name": acc.get("name"),
                        "phone_number_id": acc.get("phone_number_id"),
                        "is_active": acc.get("is_active")
                    }
                    for acc in accounts
                ]
            },
            "webhook_endpoint": "/webhook/whatsapp",
            "diagnosis": {
                "has_recent_incoming": len(incoming_last_hour) > 0,
                "last_incoming_age_minutes": (
                    (datetime.now() - datetime.fromisoformat(last_incoming.get("timestamp").replace("Z", "+00:00")))
                    .total_seconds() / 60
                    if last_incoming and last_incoming.get("timestamp") else None
                ),
                "warning": "Aucun message entrant dans la dernière heure" if len(incoming_last_hour) == 0 else None
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in webhook_status: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e)
        }


@router.get("/diagnostics/recent-errors")
async def recent_errors():
    """
    Retourne les dernières erreurs enregistrées en mémoire
    """
    return {
        "status": "ok",
        "errors": _recent_errors[-50:],  # Dernières 50 erreurs
        "total_errors": len(_recent_errors),
        "timestamp": datetime.now().isoformat()
    }


@router.get("/diagnostics/test-webhook")
async def test_webhook_info():
    """
    Retourne les informations pour tester un webhook
    """
    try:
        accounts = await get_all_accounts()
        if not accounts:
            return {
                "status": "error",
                "message": "Aucun compte configuré"
            }
        
        account = accounts[0]
        phone_number_id = account.get("phone_number_id")
        
        # Exemple de payload pour test
        example_payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": phone_number_id,
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "16505551111",
                                    "phone_number_id": phone_number_id
                                },
                                "contacts": [
                                    {
                                        "profile": {
                                            "name": "Test User"
                                        },
                                        "wa_id": "16315551181"
                                    }
                                ],
                                "messages": [
                                    {
                                        "from": "16315551181",
                                        "id": "TEST_" + str(int(datetime.now().timestamp())),
                                        "timestamp": "1504902988",
                                        "type": "text",
                                        "text": {
                                            "body": "Test message from diagnostics endpoint"
                                        }
                                    }
                                ]
                            },
                            "field": "messages"
                        }
                    ]
                }
            ]
        }
        
        return {
            "status": "ok",
            "account": {
                "name": account.get("name"),
                "phone_number_id": phone_number_id
            },
            "webhook_url": "/webhook/whatsapp",
            "example_payload": example_payload,
            "curl_command": f"""curl -X POST https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp \\
  -H "Content-Type: application/json" \\
  -d '{json.dumps(example_payload, indent=2)}'""",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in test_webhook_info: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e)
        }


@router.get("/diagnostics/database-connection")
async def database_connection():
    """
    Teste la connexion à la base de données
    """
    try:
        # Test simple
        result = await supabase_execute(
            supabase.table("whatsapp_accounts")
            .select("id")
            .limit(1)
        )
        
        return {
            "status": "ok",
            "database": "connected",
            "test_query": "success",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Database connection error: {e}", exc_info=True)
        log_error_to_memory("database_connection", str(e))
        return {
            "status": "error",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/diagnostics/full")
async def full_diagnostics():
    """
    Retourne un diagnostic complet du système
    """
    try:
        webhook_status_data = await webhook_status()
        db_status = await database_connection()
        errors = await recent_errors()
        
        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "webhook_status": webhook_status_data,
            "database": db_status,
            "recent_errors": errors,
            "system": {
                "python_version": "3.11",
                "endpoints": {
                    "webhook": "/webhook/whatsapp",
                    "webhook_debug": "/webhook/whatsapp/debug",
                    "health": "/healthz",
                    "diagnostics": "/diagnostics/full"
                }
            }
        }
    except Exception as e:
        logger.error(f"Error in full_diagnostics: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }

