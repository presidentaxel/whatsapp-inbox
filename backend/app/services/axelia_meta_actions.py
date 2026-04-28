"""Actions CRM sensibles pour Axelia (après confirmation explicite dans l'UI)."""
from __future__ import annotations

from typing import Any, Dict

from app.core.db import supabase, supabase_execute
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.account_service import get_account_by_id
from app.services.whatsapp_api_service import normalize_whatsapp_user_id


async def execute_meta_block_approved(
    args: Dict[str, Any],
    *,
    account: Dict[str, Any],
    user: CurrentUser,
) -> Dict[str, Any]:
    """
    Bloque un contact pour ce compte **dans l'app uniquement** (sans Meta).
    """
    account_id = str(account.get("id") or "")
    if not account_id:
        return {"error": "Compte WABA manquant."}

    user.require(PermissionCodes.MESSAGES_SEND, account_id)
    access = user.permissions.account_access_levels.get(account_id)
    if access in ("aucun", "lecture"):
        return {
            "error": (
                "Ton accès sur ce compte n’autorise pas le blocage "
                "(lecture seule ou aucun accès)."
            )
        }

    contact_id = str((args.get("contact_id") or "")).strip()
    if not contact_id:
        return {"error": "contact_id requis dans les paramètres d’approbation."}

    contact_res = await supabase_execute(
        supabase.table("contacts")
        .select("id, whatsapp_number")
        .eq("id", contact_id)
        .limit(1)
    )
    if not contact_res.data:
        return {"error": "Contact introuvable."}
    wa_num = contact_res.data[0].get("whatsapp_number")
    if not wa_num:
        return {"error": "Ce contact n’a pas de numéro WhatsApp."}

    acc = await get_account_by_id(account_id)
    if not acc:
        return {"error": "Compte introuvable."}

    norm = normalize_whatsapp_user_id(str(wa_num))
    from app.services.internal_block_service import InternalBlocksTableNotMigrated, upsert_internal_block

    try:
        await upsert_internal_block(contact_id, account_id)
    except InternalBlocksTableNotMigrated:
        return {
            "error": (
                "Migration base manquante : appliquer supabase/migrations/050_internal_contact_blocks.sql "
                "(table internal_contact_blocks)."
            )
        }

    return {
        "success": True,
        "blocked": True,
        "whatsapp_number": norm,
        "contact_id": contact_id,
    }
