from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.schemas.bot import BotProfileUpdate
from app.services.account_service import get_account_by_id
from app.services.bot_service import get_bot_profile, upsert_bot_profile

router = APIRouter()


@router.get("/profile/{account_id}")
async def fetch_bot_profile(
    account_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    # DEV et Manager peuvent voir le profil du bot s'ils ont accès au compte (pas "aucun")
    # On vérifie qu'ils ont au moins la permission de voir les conversations
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, account_id)
    return await get_bot_profile(account_id)


@router.put("/profile/{account_id}")
async def update_bot_profile(
    account_id: str,
    payload: BotProfileUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    current_user.require(PermissionCodes.SETTINGS_MANAGE, account_id)
    return await upsert_bot_profile(account_id, payload.dict())

