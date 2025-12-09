from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
import logging

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser
from app.core.db import supabase, supabase_execute

logger = logging.getLogger(__name__)

router = APIRouter()


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    profile_picture_url: str | None = None


@router.get("/me")
async def read_profile(current_user: CurrentUser = Depends(get_current_user)):
    permissions = current_user.permissions
    app_profile = current_user.app_profile or {}
    return {
        "id": current_user.id,
        "email": current_user.email,
        "display_name": app_profile.get("display_name"),
        "profile_picture_url": app_profile.get("profile_picture_url"),
        "profile": app_profile,
        "permissions": {
            "global": sorted(list(permissions.global_permissions)),
            "accounts": {
                acc_id: sorted(list(perms))
                for acc_id, perms in permissions.account_permissions.items()
            },
            "account_access_levels": permissions.account_access_levels,  # 'full'|'lecture'|'aucun' par compte
        },
        "roles": current_user.role_assignments,
        "overrides": current_user.overrides,
    }


@router.put("/me")
async def update_profile(
    profile_update: ProfileUpdate,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Met à jour le profil utilisateur"""
    update_data = {}
    
    if profile_update.display_name is not None:
        update_data["display_name"] = profile_update.display_name
    
    if profile_update.profile_picture_url is not None:
        update_data["profile_picture_url"] = profile_update.profile_picture_url
    
    if not update_data:
        raise HTTPException(status_code=400, detail="no_fields_to_update")
    
    # Construire la requête avec select avant update
    query = supabase.table("app_users").update(update_data).eq("user_id", current_user.id)
    result = await supabase_execute(query.select())
    
    if not result.data:
        raise HTTPException(status_code=500, detail="profile_update_failed")
    
    return result.data[0]


@router.post("/me/profile-picture")
async def upload_profile_picture(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user)
):
    """Upload une photo de profil"""
    # Vérifier le type de fichier
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="file_must_be_image")
    
    # Vérifier la taille (max 5MB)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="file_too_large")
    
    try:
        from starlette.concurrency import run_in_threadpool
        import uuid
        
        # Upload vers Supabase Storage
        file_ext = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        file_path = f"{current_user.id}/{uuid.uuid4()}.{file_ext}"
        
        # Upload de manière asynchrone
        upload_result = await run_in_threadpool(
            lambda: supabase.storage.from_("profile-pictures").upload(
                file_path,
                contents,
                file_options={"content-type": file.content_type, "upsert": "true"}
            )
        )
        
        if upload_result.error:
            raise HTTPException(status_code=500, detail=f"upload_failed: {upload_result.error}")
        
        # Récupérer l'URL publique
        from app.core.config import settings
        public_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/profile-pictures/{file_path}"
        
        # Mettre à jour le profil
        query = supabase.table("app_users").update({"profile_picture_url": public_url}).eq("user_id", current_user.id)
        result = await supabase_execute(query.select())
        
        if not result.data:
            raise HTTPException(status_code=500, detail="profile_update_failed")
        
        return {
            "profile_picture_url": public_url,
            "user": result.data[0]
        }
    except Exception as e:
        logger.error(f"Error uploading profile picture: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"upload_error: {str(e)}")


