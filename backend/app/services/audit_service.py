"""
Service d'audit pour la traçabilité des actions (messages envoyés/édités/supprimés, etc.).
"""
import json
import logging
from typing import Any, Dict, Optional

from app.core.db import supabase, supabase_execute
from app.core.pg import execute as pg_execute, get_pool

logger = logging.getLogger(__name__)


async def log_action(
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    user_id: Optional[str] = None,
    account_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Enregistre une action dans le journal d'audit.
    Ne lève pas d'exception pour ne pas impacter le flux métier.
    """
    try:
        payload = {
            "action": action,
            "resource_type": resource_type,
            "details": details or {},
        }
        if resource_id is not None:
            payload["resource_id"] = str(resource_id)
        if user_id is not None:
            payload["user_id"] = user_id
        if account_id is not None:
            payload["account_id"] = account_id

        if get_pool():
            details_val = payload.get("details") or {}
            details_json = json.dumps(details_val) if isinstance(details_val, dict) else details_val
            await pg_execute(
                """
                INSERT INTO audit_log (action, resource_type, resource_id, user_id, account_id, details)
                VALUES ($1, $2, $3, $4::uuid, $5::uuid, $6::jsonb)
                """,
                payload["action"],
                payload["resource_type"],
                payload.get("resource_id"),
                payload.get("user_id"),
                payload.get("account_id"),
                details_json,
            )
        else:
            await supabase_execute(supabase.table("audit_log").insert(payload))
    except Exception as e:
        logger.warning("Audit log write failed (non-fatal): %s", e)
