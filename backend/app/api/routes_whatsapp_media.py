"""
Routes API pour la gestion des médias WhatsApp
"""
import os
import tempfile
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.account_service import get_account_by_id
from app.services import whatsapp_api_service

router = APIRouter(prefix="/whatsapp/media", tags=["WhatsApp Media"])


@router.post("/upload/{account_id}")
async def upload_media(
    account_id: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Upload un fichier média sur WhatsApp
    POST /{PHONE_NUMBER_ID}/media
    """
    current_user.require(PermissionCodes.MESSAGES_SEND, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    phone_number_id = account.get("phone_number_id")
    access_token = account.get("access_token")
    
    if not phone_number_id or not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    # Lire le contenu du fichier
    content = await file.read()
    mime_type = file.content_type or "application/octet-stream"
    filename = file.filename or "file"
    
    try:
        result = await whatsapp_api_service.upload_media_from_bytes(
            phone_number_id=phone_number_id,
            access_token=access_token,
            file_content=content,
            filename=filename,
            mime_type=mime_type
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/info/{account_id}/{media_id}")
async def get_media_info(
    account_id: str,
    media_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Récupère les informations d'un média
    GET /{MEDIA_ID}
    """
    current_user.require(PermissionCodes.MESSAGES_VIEW, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    access_token = account.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        result = await whatsapp_api_service.get_media_url(
            media_id=media_id,
            access_token=access_token
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/download/{account_id}/{media_id}")
async def download_media(
    account_id: str,
    media_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Télécharge le contenu d'un média
    GET /{MEDIA_ID} puis télécharge depuis l'URL retournée
    """
    current_user.require(PermissionCodes.MESSAGES_VIEW, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    access_token = account.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        content = await whatsapp_api_service.download_media(
            media_id=media_id,
            access_token=access_token
        )
        
        # Retourner le contenu en streaming
        return StreamingResponse(
            iter([content]),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename=media_{media_id}"}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{account_id}/{media_id}")
async def delete_media(
    account_id: str,
    media_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Supprime un média du stockage Meta
    DELETE /{MEDIA_ID}
    """
    current_user.require(PermissionCodes.MESSAGES_SEND, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    access_token = account.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        result = await whatsapp_api_service.delete_media(
            media_id=media_id,
            access_token=access_token
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

