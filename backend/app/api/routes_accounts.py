from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.account_service import (
    create_account,
    delete_account,
    expose_accounts_limited,
    get_account_by_id,
)
from app.schemas.accounts import AccountCreate

router = APIRouter()


@router.get("")
async def list_accounts(current_user: CurrentUser = Depends(get_current_user)):
    allowed_scope = current_user.accounts_for(PermissionCodes.ACCOUNTS_VIEW)
    if allowed_scope is None:
        current_user.require(PermissionCodes.ACCOUNTS_VIEW)
    elif not allowed_scope:
        raise HTTPException(status_code=403, detail="no_account_access")
    return expose_accounts_limited(allowed_scope)


@router.post("")
async def create_account_api(
    payload: AccountCreate, current_user: CurrentUser = Depends(get_current_user)
):
    current_user.require(PermissionCodes.ACCOUNTS_MANAGE)
    return create_account(payload.dict())


@router.delete("/{account_id}")
async def delete_account_api(account_id: str, current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.ACCOUNTS_MANAGE)
    account = get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    delete_account(account_id)
    return {"status": "deleted", "account_id": account_id}

