"""
Routes API pour l'envoi de messages WhatsApp (tous types)
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import Optional

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.account_service import get_account_by_id, invalidate_account_cache
from app.services import whatsapp_api_service
from app.schemas.whatsapp import (
    SendTextMessageRequest,
    SendMediaMessageRequest,
    SendTemplateMessageRequest,
    SendInteractiveButtonsRequest,
    SendInteractiveListRequest,
)

router = APIRouter(prefix="/whatsapp/messages", tags=["WhatsApp Messages"])


@router.post("/text/{account_id}")
async def send_text_message(
    account_id: str,
    request: SendTextMessageRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Envoie un message texte WhatsApp
    """
    current_user.require(PermissionCodes.MESSAGES_SEND, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    phone_number_id = account.get("phone_number_id")
    access_token = account.get("access_token")
    
    if not phone_number_id or not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        # Valider et normaliser le numéro
        to_number = whatsapp_api_service.validate_phone_number(request.to)
        
        result = await whatsapp_api_service.send_text_message(
            phone_number_id=phone_number_id,
            access_token=access_token,
            to=to_number,
            text=request.text,
            preview_url=request.preview_url
        )
        return {"success": True, "data": result}
    except Exception as e:
        error_str = str(e).lower()
        # Si erreur de token expiré, invalider le cache et réessayer une fois
        if "401" in error_str or "unauthorized" in error_str or "expired" in error_str or "session has expired" in error_str:
            invalidate_account_cache(account_id)
            # Réessayer avec le compte rechargé depuis la DB
            account = await get_account_by_id(account_id)
            if account:
                access_token = account.get("access_token")
                if access_token:
                    try:
                        result = await whatsapp_api_service.send_text_message(
                            phone_number_id=phone_number_id,
                            access_token=access_token,
                            to=to_number,
                            text=request.text,
                            preview_url=request.preview_url
                        )
                        return {"success": True, "data": result}
                    except Exception as retry_error:
                        raise HTTPException(status_code=400, detail=str(retry_error))
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/media/{account_id}")
async def send_media_message(
    account_id: str,
    request: SendMediaMessageRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Envoie un message avec média (image, audio, vidéo, document)
    """
    current_user.require(PermissionCodes.MESSAGES_SEND, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    phone_number_id = account.get("phone_number_id")
    access_token = account.get("access_token")
    
    if not phone_number_id or not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    if not request.media_id and not request.media_link:
        raise HTTPException(status_code=400, detail="media_id or media_link required")
    
    try:
        to_number = whatsapp_api_service.validate_phone_number(request.to)
        
        result = await whatsapp_api_service.send_media_message(
            phone_number_id=phone_number_id,
            access_token=access_token,
            to=to_number,
            media_type=request.media_type,
            media_id=request.media_id,
            media_link=request.media_link,
            caption=request.caption,
            filename=request.filename
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/template/{account_id}")
async def send_template_message(
    account_id: str,
    request: SendTemplateMessageRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Envoie un message template WhatsApp
    """
    current_user.require(PermissionCodes.MESSAGES_SEND, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    phone_number_id = account.get("phone_number_id")
    access_token = account.get("access_token")
    
    if not phone_number_id or not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        to_number = whatsapp_api_service.validate_phone_number(request.to)
        
        result = await whatsapp_api_service.send_template_message(
            phone_number_id=phone_number_id,
            access_token=access_token,
            to=to_number,
            template_name=request.template_name,
            language_code=request.language_code,
            components=request.components
        )
        return {"success": True, "data": result}
    except Exception as e:
        error_str = str(e).lower()
        # Si erreur de token expiré, invalider le cache et réessayer une fois
        if "401" in error_str or "unauthorized" in error_str or "expired" in error_str or "session has expired" in error_str:
            invalidate_account_cache(account_id)
            # Réessayer avec le compte rechargé depuis la DB
            account = await get_account_by_id(account_id)
            if account:
                access_token = account.get("access_token")
                if access_token:
                    try:
                        result = await whatsapp_api_service.send_template_message(
                            phone_number_id=phone_number_id,
                            access_token=access_token,
                            to=to_number,
                            template_name=request.template_name,
                            language_code=request.language_code,
                            components=request.components
                        )
                        return {"success": True, "data": result}
                    except Exception as retry_error:
                        raise HTTPException(status_code=400, detail=str(retry_error))
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/interactive/buttons/{account_id}")
async def send_interactive_buttons(
    account_id: str,
    request: SendInteractiveButtonsRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Envoie un message interactif avec boutons
    """
    current_user.require(PermissionCodes.MESSAGES_SEND, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    phone_number_id = account.get("phone_number_id")
    access_token = account.get("access_token")
    
    if not phone_number_id or not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        to_number = whatsapp_api_service.validate_phone_number(request.to)
        
        buttons = [{"id": btn.id, "title": btn.title} for btn in request.buttons]
        
        result = await whatsapp_api_service.send_interactive_buttons(
            phone_number_id=phone_number_id,
            access_token=access_token,
            to=to_number,
            body_text=request.body_text,
            buttons=buttons,
            header_text=request.header_text,
            footer_text=request.footer_text
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/interactive/list/{account_id}")
async def send_interactive_list(
    account_id: str,
    request: SendInteractiveListRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Envoie un message interactif avec liste déroulante
    """
    current_user.require(PermissionCodes.MESSAGES_SEND, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    phone_number_id = account.get("phone_number_id")
    access_token = account.get("access_token")
    
    if not phone_number_id or not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        to_number = whatsapp_api_service.validate_phone_number(request.to)
        
        # Convertir les sections en dict
        sections = [
            {
                "title": section.title,
                "rows": [
                    {
                        "id": row.id,
                        "title": row.title,
                        "description": row.description
                    }
                    for row in section.rows
                ]
            }
            for section in request.sections
        ]
        
        result = await whatsapp_api_service.send_interactive_list(
            phone_number_id=phone_number_id,
            access_token=access_token,
            to=to_number,
            body_text=request.body_text,
            button_text=request.button_text,
            sections=sections,
            header_text=request.header_text,
            footer_text=request.footer_text
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

