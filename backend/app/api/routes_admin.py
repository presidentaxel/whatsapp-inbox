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
from app.services.account_service import expose_accounts_public

router = APIRouter()


@router.get("/permissions")
async def fetch_permissions(current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.ROLES_MANAGE)
    return admin_service.list_permissions()


@router.get("/roles")
async def fetch_roles(current_user: CurrentUser = Depends(get_current_user)):
    # Permettre à Admin et DEV de voir les rôles (pour l'affichage dans PermissionsTable)
    # Seul Admin peut modifier les rôles via create/update/delete
    if not current_user.permissions.has(PermissionCodes.PERMISSIONS_VIEW):
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
    # Seul Admin peut modifier les rôles (via permissions.manage ou roles.manage)
    # permissions.manage inclut la gestion des rôles car c'est un aspect de la gestion des permissions
    if not (current_user.permissions.has(PermissionCodes.PERMISSIONS_MANAGE) or 
            current_user.permissions.has(PermissionCodes.ROLES_MANAGE)):
        raise HTTPException(status_code=403, detail="permission_denied")
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
    return admin_service.list_users_with_access()


@router.put("/users/{user_id}/accounts/{account_id}/access")
async def update_user_account_access(
    user_id: str,
    account_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Met à jour l'accès d'un utilisateur à un compte WhatsApp"""
    # Seul Admin peut modifier (permissions.manage)
    # Note: cette permission n'est PAS bloquée par access_level = 'aucun' car elle permet
    # à l'admin de gérer les permissions même s'il a mis "aucun" pour lui-même
    current_user.require(PermissionCodes.PERMISSIONS_MANAGE)
    
    access_level = payload.get("access_level")
    if not access_level:
        raise HTTPException(status_code=400, detail="access_level_required")
    admin_service.set_user_account_access(user_id, account_id, access_level)
    return {"status": "ok", "user_id": user_id, "account_id": account_id, "access_level": access_level}


