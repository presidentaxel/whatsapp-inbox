from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
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


