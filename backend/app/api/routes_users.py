from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.core.db import supabase, supabase_execute
from starlette.concurrency import run_in_threadpool
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Supprime un utilisateur (admin uniquement)
    """
    current_user.require(PermissionCodes.USERS_MANAGE)
    
    # Ne pas permettre de se supprimer soi-même
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="cannot_delete_self")
    
    try:
        # Supprimer les rôles et overrides
        await supabase_execute(
            supabase.table("app_user_roles").delete().eq("user_id", user_id)
        )
        await supabase_execute(
            supabase.table("app_user_overrides").delete().eq("user_id", user_id)
        )
        
        # Supprimer l'utilisateur de app_users
        await supabase_execute(
            supabase.table("app_users").delete().eq("user_id", user_id)
        )
        
        # Supprimer l'utilisateur de Supabase Auth (nécessite admin API)
        def _delete_auth_user():
            return supabase.auth.admin.delete_user(user_id)
        
        await run_in_threadpool(_delete_auth_user)
        
        return {"success": True, "message": "user_deleted"}
    except Exception as e:
        logger.error(f"Error deleting user: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"delete_error: {str(e)}")

