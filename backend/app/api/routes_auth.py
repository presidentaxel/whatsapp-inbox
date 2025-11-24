from fastapi import APIRouter, Depends

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser

router = APIRouter()


@router.get("/me")
async def read_profile(current_user: CurrentUser = Depends(get_current_user)):
    permissions = current_user.permissions
    return {
        "id": current_user.id,
        "email": current_user.email,
        "profile": current_user.app_profile,
        "permissions": {
            "global": sorted(list(permissions.global_permissions)),
            "accounts": {
                acc_id: sorted(list(perms))
                for acc_id, perms in permissions.account_permissions.items()
            },
        },
        "roles": current_user.role_assignments,
        "overrides": current_user.overrides,
    }


