from fastapi import APIRouter, Depends

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.contact_service import list_contacts

router = APIRouter()


@router.get("")
async def fetch_contacts(current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.CONTACTS_VIEW)
    return await list_contacts()

