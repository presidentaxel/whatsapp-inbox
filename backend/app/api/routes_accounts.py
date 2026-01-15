from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.account_service import (
    create_account,
    delete_account,
    update_account,
    expose_accounts_limited,
    get_account_by_id,
)
from app.schemas.accounts import AccountCreate, AccountGoogleDriveUpdate

router = APIRouter()


@router.get("")
async def list_accounts(current_user: CurrentUser = Depends(get_current_user)):
    # Vérifier la permission de base
    current_user.require(PermissionCodes.ACCOUNTS_VIEW)
    
    allowed_scope = current_user.accounts_for(PermissionCodes.ACCOUNTS_VIEW)
    if allowed_scope is None:
        # Permission globale : récupérer tous les comptes, puis filtrer ceux en 'aucun'
        all_accounts = await expose_accounts_limited(None)
        # Filtrer les comptes où l'utilisateur a access_level = 'aucun'
        filtered = [
            acc for acc in all_accounts
            if current_user.permissions.account_access_levels.get(acc["id"]) != "aucun"
        ]
        return filtered
    elif not allowed_scope:
        raise HTTPException(status_code=403, detail="no_account_access")
    else:
        # Permissions spécifiques : retourner seulement les comptes autorisés
        return await expose_accounts_limited(allowed_scope)


@router.post("")
async def create_account_api(
    payload: AccountCreate, current_user: CurrentUser = Depends(get_current_user)
):
    current_user.require(PermissionCodes.ACCOUNTS_MANAGE)
    return await create_account(payload.dict())


@router.patch("/{account_id}/google-drive")
async def update_account_google_drive(
    account_id: str,
    payload: AccountGoogleDriveUpdate,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Met à jour la configuration Google Drive d'un compte WhatsApp"""
    # Vérifier que l'utilisateur a au moins accès en lecture au compte
    current_user.require(PermissionCodes.ACCOUNTS_VIEW, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    updates = payload.dict(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # Si l'utilisateur essaie de modifier google_drive_enabled, il faut ACCOUNTS_MANAGE
    # Mais pour changer seulement le dossier (google_drive_folder_id), ACCOUNTS_VIEW suffit
    if "google_drive_enabled" in updates:
        current_user.require(PermissionCodes.ACCOUNTS_MANAGE, account_id)
    
    updated = await update_account(account_id, updates)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update account")
    
    return {
        "status": "updated",
        "account_id": account_id,
        "google_drive_enabled": updated.get("google_drive_enabled", False),
        "google_drive_folder_id": updated.get("google_drive_folder_id")
    }


@router.delete("/{account_id}")
async def delete_account_api(account_id: str, current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.ACCOUNTS_MANAGE)
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    await delete_account(account_id)
    return {"status": "deleted", "account_id": account_id}

