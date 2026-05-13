from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_user
from app.core.cache import get_cache
from app.core.circuit_breaker import (
    get_all_circuit_breakers,
    gemini_circuit_breaker,
    whatsapp_circuit_breaker,
    supabase_circuit_breaker,
)
from app.core.permissions import CurrentUser, PermissionCodes
from app.services import admin_service
from app.services.account_service import expose_accounts_public
from app.services.message_service import handle_incoming_message
from app.services.webhook_event_service import (
    get_webhook_event_detail,
    get_webhook_event_stats,
    list_webhook_events,
    retry_webhook_event,
)

router = APIRouter()


@router.get("/permissions")
async def fetch_permissions(current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.ROLES_MANAGE)
    return await admin_service.list_permissions()


@router.get("/roles")
async def fetch_roles(current_user: CurrentUser = Depends(get_current_user)):
    if not current_user.permissions.has(PermissionCodes.PERMISSIONS_VIEW):
        current_user.require(PermissionCodes.ROLES_MANAGE)
    return await admin_service.list_roles()


@router.post("/roles")
async def create_role(payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.ROLES_MANAGE)
    return await admin_service.create_role(payload)


@router.put("/roles/{role_id}")
async def update_role(role_id: str, payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.ROLES_MANAGE)
    return await admin_service.update_role(role_id, payload)


@router.delete("/roles/{role_id}")
async def remove_role(role_id: str, current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.ROLES_MANAGE)
    await admin_service.delete_role(role_id)
    return {"status": "deleted", "role_id": role_id}


@router.get("/users")
async def fetch_users(current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.USERS_MANAGE)
    current_user.require(PermissionCodes.ROLES_MANAGE)
    return await admin_service.list_app_users()


@router.post("/users/{user_id}/status")
async def update_user_status(user_id: str, payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.USERS_MANAGE)
    is_active = payload.get("is_active")
    if is_active is None:
        raise HTTPException(status_code=400, detail="is_active_required")
    await admin_service.set_user_status(user_id, bool(is_active))
    return {"status": "ok", "user_id": user_id, "is_active": bool(is_active)}


@router.put("/users/{user_id}/roles")
async def update_user_roles(user_id: str, payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    if not (current_user.permissions.has(PermissionCodes.PERMISSIONS_MANAGE) or 
            current_user.permissions.has(PermissionCodes.ROLES_MANAGE)):
        raise HTTPException(status_code=403, detail="permission_denied")
    assignments = payload.get("assignments", [])
    await admin_service.set_user_roles(user_id, assignments)
    return {"status": "ok"}


@router.put("/users/{user_id}/overrides")
async def update_user_overrides(user_id: str, payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.ROLES_MANAGE)
    overrides = payload.get("overrides", [])
    await admin_service.set_user_overrides(user_id, overrides)
    return {"status": "ok"}


# === Endpoints de monitoring (Phase 3) ===

@router.get("/circuit-breakers")
async def get_circuit_breakers_status(current_user: CurrentUser = Depends(get_current_user)):
    """
    Retourne l'état de tous les circuit breakers.
    Utile pour monitorer les dépendances externes.
    """
    current_user.require(PermissionCodes.ROLES_MANAGE)
    return get_all_circuit_breakers()


@router.post("/circuit-breakers/{name}/reset")
async def reset_circuit_breaker(name: str, current_user: CurrentUser = Depends(get_current_user)):
    """
    Reset manuel d'un circuit breaker.
    Utile après avoir résolu un problème sur une dépendance externe.
    """
    current_user.require(PermissionCodes.ROLES_MANAGE)
    
    breakers = {
        "gemini": gemini_circuit_breaker,
        "whatsapp": whatsapp_circuit_breaker,
        "supabase": supabase_circuit_breaker,
    }
    
    breaker = breakers.get(name)
    if not breaker:
        raise HTTPException(status_code=404, detail=f"Circuit breaker '{name}' not found")
    
    breaker.reset()
    return {"status": "reset", "name": name}


@router.get("/cache/stats")
async def get_cache_stats(current_user: CurrentUser = Depends(get_current_user)):
    """
    Retourne des statistiques sur le cache.
    """
    current_user.require(PermissionCodes.ROLES_MANAGE)
    cache = await get_cache()
    return cache.get_stats()


@router.post("/cache/clear")
async def clear_cache(current_user: CurrentUser = Depends(get_current_user)):
    """
    Vide tout le cache.
    Utile après une mise à jour de données critiques.
    """
    current_user.require(PermissionCodes.ROLES_MANAGE)
    cache = await get_cache()
    await cache.clear()
    return {"status": "cleared"}


@router.post("/webhook/replay")
async def replay_whatsapp_webhook(payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    """
    Rejoue un corps JSON identique au webhook Meta (POST /webhook/whatsapp).
    Utile pour réinjecter des événements après un bug de persistance : coller le JSON
    depuis les logs ou l’outil de test Meta. Les messages existants sont mis à jour (upsert sur wa_message_id).
    """
    current_user.require(PermissionCodes.SETTINGS_MANAGE)
    await handle_incoming_message(payload, propagate_errors=True)
    return {"status": "ok"}


@router.get("/accounts/all")
async def fetch_all_accounts_for_permissions(current_user: CurrentUser = Depends(get_current_user)):
    """Retourne TOUS les comptes WhatsApp pour la gestion des permissions"""
    # Seuls Admin et DEV peuvent voir cette liste (pour la table des permissions)
    # Cette liste ne filtre PAS selon access_level = 'aucun' car elle sert à gérer les permissions
    if not current_user.permissions.has(PermissionCodes.PERMISSIONS_VIEW):
        raise HTTPException(status_code=403, detail="permission_denied")
    # Retourner tous les comptes sans filtre
    return await expose_accounts_public()


@router.get("/users/with-access")
async def fetch_users_with_access(current_user: CurrentUser = Depends(get_current_user)):
    """Liste tous les utilisateurs avec leurs rôles et accès par compte"""
    # Admin et DEV peuvent voir, seul Admin peut modifier
    # Utiliser les permissions plutôt que le rôle pour plus de flexibilité
    # permissions.view = DEV peut voir, permissions.manage = Admin peut modifier
    if not current_user.permissions.has(PermissionCodes.PERMISSIONS_VIEW):
        raise HTTPException(status_code=403, detail="permission_denied")
    return await admin_service.list_users_with_access()


@router.put("/users/{user_id}/accounts/{account_id}/access")
async def update_user_account_access(
    user_id: str,
    account_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Met à jour l'accès d'un utilisateur à un compte WhatsApp"""
    current_user.require(PermissionCodes.PERMISSIONS_MANAGE)
    
    access_level = payload.get("access_level")
    if not access_level:
        raise HTTPException(status_code=400, detail="access_level_required")
    await admin_service.set_user_account_access(user_id, account_id, access_level)
    return {"status": "ok", "user_id": user_id, "account_id": account_id, "access_level": access_level}


@router.put("/users/{user_id}/axelia-access")
async def update_user_axelia_access(
    user_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Autoriser ou révoquer l'accès à Axelia (/axelia) pour un utilisateur."""
    current_user.require(PermissionCodes.PERMISSIONS_MANAGE)
    if "allowed" not in payload:
        raise HTTPException(status_code=400, detail="allowed_required")
    await admin_service.set_user_axelia_access(user_id, bool(payload["allowed"]))
    return {"status": "ok", "user_id": user_id}


@router.put("/users/{user_id}/playground-access")
async def update_user_playground_access(
    user_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Autoriser ou révoquer l'accès au Playground (/playground) pour un utilisateur."""
    current_user.require(PermissionCodes.PERMISSIONS_MANAGE)
    if "allowed" not in payload:
        raise HTTPException(status_code=400, detail="allowed_required")
    await admin_service.set_user_playground_access(user_id, bool(payload["allowed"]))
    return {"status": "ok", "user_id": user_id}


@router.put("/users/{user_id}/agent-studio-access")
async def update_user_agent_studio_access(
    user_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Autoriser ou révoquer l'accès à Agent Studio (/agent-studio) pour un utilisateur."""
    current_user.require(PermissionCodes.PERMISSIONS_MANAGE)
    if "allowed" not in payload:
        raise HTTPException(status_code=400, detail="allowed_required")
    await admin_service.set_user_agent_studio_access(user_id, bool(payload["allowed"]))
    return {"status": "ok", "user_id": user_id}


# === Observabilité de la file durable webhook_events ========================
#
# Pourquoi : la table `webhook_events` est notre filet de sécurité contre la
# perte d'évènements Meta. Un endpoint d'observation évite d'avoir à se
# connecter à la DB pour comprendre l'état de la file.
#
# Permissions : SETTINGS_MANAGE (cohérent avec /admin/webhook/replay au-dessus
# qui sert le même besoin de débogage opérationnel).
# ===========================================================================


@router.get("/webhook-events/stats")
async def webhook_events_stats(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Snapshot rapide : compteurs par status + plus vieil évènement non drainé.
    Utile pour vérifier en un coup d'œil que la file ne s'accumule pas.
    """
    current_user.require(PermissionCodes.SETTINGS_MANAGE)
    return await get_webhook_event_stats()


@router.get("/webhook-events")
async def webhook_events_list(
    status: str | None = Query(
        None,
        description="Filtre: pending | processing | done | failed",
        pattern="^(pending|processing|done|failed)$",
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Liste paginée des évènements (sans le champ `payload` pour rester léger).
    """
    current_user.require(PermissionCodes.SETTINGS_MANAGE)
    return {
        "items": await list_webhook_events(status=status, limit=limit, offset=offset),
        "limit": limit,
        "offset": offset,
        "status_filter": status,
    }


@router.get("/webhook-events/{event_id}")
async def webhook_events_detail(
    event_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Détail complet (incluant `payload` JSONB). Utile pour rejouer / debug forensic."""
    current_user.require(PermissionCodes.SETTINGS_MANAGE)
    detail = await get_webhook_event_detail(event_id)
    if not detail:
        raise HTTPException(status_code=404, detail="webhook_event_not_found")
    return detail


@router.post("/webhook-events/{event_id}/retry")
async def webhook_events_retry(
    event_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Force le retry d'un évènement échoué.
    Met la ligne en `pending` avec `attempts = max_attempts - 1` pour laisser
    une dernière chance avant l'arrêt définitif.
    """
    current_user.require(PermissionCodes.SETTINGS_MANAGE)
    ok = await retry_webhook_event(event_id)
    if not ok:
        raise HTTPException(status_code=404, detail="webhook_event_not_found")
    return {"status": "queued_for_retry", "event_id": event_id}


