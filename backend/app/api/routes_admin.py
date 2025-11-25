from fastapi import APIRouter, Depends, HTTPException

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

router = APIRouter()


@router.get("/permissions")
async def fetch_permissions(current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.ROLES_MANAGE)
    return admin_service.list_permissions()


@router.get("/roles")
async def fetch_roles(current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.ROLES_MANAGE)
    return admin_service.list_roles()


@router.post("/roles")
async def create_role(payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.ROLES_MANAGE)
    return admin_service.create_role(payload)


@router.put("/roles/{role_id}")
async def update_role(role_id: str, payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.ROLES_MANAGE)
    return admin_service.update_role(role_id, payload)


@router.delete("/roles/{role_id}")
async def remove_role(role_id: str, current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.ROLES_MANAGE)
    admin_service.delete_role(role_id)
    return {"status": "deleted", "role_id": role_id}


@router.get("/users")
async def fetch_users(current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.USERS_MANAGE)
    current_user.require(PermissionCodes.ROLES_MANAGE)
    return admin_service.list_app_users()


@router.post("/users/{user_id}/status")
async def update_user_status(user_id: str, payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.USERS_MANAGE)
    is_active = payload.get("is_active")
    if is_active is None:
        raise HTTPException(status_code=400, detail="is_active_required")
    admin_service.set_user_status(user_id, bool(is_active))
    return {"status": "ok", "user_id": user_id, "is_active": bool(is_active)}


@router.put("/users/{user_id}/roles")
async def update_user_roles(user_id: str, payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.ROLES_MANAGE)
    assignments = payload.get("assignments", [])
    admin_service.set_user_roles(user_id, assignments)
    return {"status": "ok"}


@router.put("/users/{user_id}/overrides")
async def update_user_overrides(user_id: str, payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.ROLES_MANAGE)
    overrides = payload.get("overrides", [])
    admin_service.set_user_overrides(user_id, overrides)
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


