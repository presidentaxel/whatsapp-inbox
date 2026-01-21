"""
Routes API pour la gestion des templates de messages WhatsApp
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.account_service import get_account_by_id
from app.services import whatsapp_api_service
from app.services.whatsapp_api_service import WhatsAppAPIError
from app.schemas.whatsapp import (
    CreateMessageTemplateRequest,
    DeleteMessageTemplateRequest,
)

router = APIRouter(prefix="/whatsapp/templates", tags=["WhatsApp Templates"])


@router.get("/list/{account_id}")
async def list_templates(
    account_id: str,
    limit: int = Query(100, ge=1, le=500),
    after: Optional[str] = Query(None, description="Pagination cursor"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Liste les templates de messages d'un WABA
    GET /{WABA-ID}/message_templates
    """
    current_user.require(PermissionCodes.MESSAGES_VIEW, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    waba_id = account.get("waba_id")
    access_token = account.get("access_token")
    
    if not waba_id:
        raise HTTPException(
            status_code=400,
            detail="waba_id not configured in account. Please add it to whatsapp_accounts table."
        )
    
    if not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        result = await whatsapp_api_service.list_message_templates(
            waba_id=waba_id,
            access_token=access_token,
            limit=limit,
            after=after
        )
        return {"success": True, "data": result}
    except WhatsAppAPIError as e:
        status_code = 401 if e.is_token_expired else 400
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lors de la récupération des templates: {str(e)}")


@router.post("/create/{account_id}")
async def create_template(
    account_id: str,
    request: CreateMessageTemplateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Crée un nouveau template de message (soumis à review Meta)
    POST /{WABA-ID}/message_templates
    
    Le template doit être approuvé par Meta avant utilisation.
    Catégories disponibles:
    - AUTHENTICATION: Pour les codes de vérification
    - MARKETING: Pour les messages promotionnels (nécessite opt-in)
    - UTILITY: Pour les notifications transactionnelles
    
    Exemple de components:
    [
        {
            "type": "HEADER",
            "format": "TEXT",
            "text": "Bonjour"
        },
        {
            "type": "BODY",
            "text": "Votre code de vérification est {{1}}. Il expire dans {{2}} minutes."
        },
        {
            "type": "FOOTER",
            "text": "Ne partagez pas ce code"
        }
    ]
    """
    current_user.require(PermissionCodes.ACCOUNTS_MANAGE, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    waba_id = account.get("waba_id")
    access_token = account.get("access_token")
    
    if not waba_id:
        raise HTTPException(
            status_code=400,
            detail="waba_id not configured in account. Please add it to whatsapp_accounts table."
        )
    
    if not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        # Convertir les components en format API
        components = []
        for comp in request.components:
            component_dict = {"type": comp.type}
            
            if comp.format:
                component_dict["format"] = comp.format
            if comp.text:
                component_dict["text"] = comp.text
            if comp.buttons:
                component_dict["buttons"] = [
                    {
                        "type": btn.type,
                        "text": btn.text,
                        **({"url": btn.url} if btn.url else {}),
                        **({"phone_number": btn.phone_number} if btn.phone_number else {})
                    }
                    for btn in comp.buttons
                ]
            
            components.append(component_dict)
        
        result = await whatsapp_api_service.create_message_template(
            waba_id=waba_id,
            access_token=access_token,
            name=request.name,
            category=request.category,
            language=request.language,
            components=components
        )
        return {"success": True, "data": result}
    except WhatsAppAPIError as e:
        status_code = 401 if e.is_token_expired else 400
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lors de la création du template: {str(e)}")


@router.delete("/delete/{account_id}")
async def delete_template(
    account_id: str,
    request: DeleteMessageTemplateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Supprime un template de message
    DELETE /{WABA-ID}/message_templates
    """
    current_user.require(PermissionCodes.ACCOUNTS_MANAGE, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    waba_id = account.get("waba_id")
    access_token = account.get("access_token")
    
    if not waba_id:
        raise HTTPException(
            status_code=400,
            detail="waba_id not configured in account. Please add it to whatsapp_accounts table."
        )
    
    if not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        result = await whatsapp_api_service.delete_message_template(
            waba_id=waba_id,
            access_token=access_token,
            name=request.name,
            hsm_id=request.hsm_id
        )
        return {"success": True, "data": result}
    except WhatsAppAPIError as e:
        status_code = 401 if e.is_token_expired else 400
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lors de la suppression du template: {str(e)}")

