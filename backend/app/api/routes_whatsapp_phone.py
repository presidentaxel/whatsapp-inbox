"""
Routes API pour la gestion des numéros de téléphone WhatsApp
"""
from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.account_service import get_account_by_id
from app.services import whatsapp_api_service
from app.schemas.whatsapp import (
    RegisterPhoneRequest,
    RequestVerificationCodeRequest,
    VerifyCodeRequest,
)

router = APIRouter(prefix="/whatsapp/phone", tags=["WhatsApp Phone Numbers"])


@router.get("/list/{account_id}")
async def list_phone_numbers(
    account_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Liste les numéros de téléphone d'un WABA
    GET /{WABA-ID}/phone_numbers
    
    Note: Nécessite le WABA ID qui doit être configuré dans l'account
    """
    # Permettre ACCOUNTS_VIEW (DEV) ou ACCOUNTS_MANAGE (Admin)
    if not (
        current_user.permissions.has(PermissionCodes.ACCOUNTS_VIEW, account_id)
        or current_user.permissions.has(PermissionCodes.ACCOUNTS_MANAGE, account_id)
    ):
        raise HTTPException(status_code=403, detail="permission_denied")
    
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
        result = await whatsapp_api_service.list_phone_numbers(
            waba_id=waba_id,
            access_token=access_token
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/details/{account_id}")
async def get_phone_details(
    account_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Récupère les détails du numéro de téléphone
    GET /{PHONE_NUMBER_ID}
    """
    # Permettre ACCOUNTS_VIEW (DEV) ou ACCOUNTS_MANAGE (Admin)
    if not (
        current_user.permissions.has(PermissionCodes.ACCOUNTS_VIEW, account_id)
        or current_user.permissions.has(PermissionCodes.ACCOUNTS_MANAGE, account_id)
    ):
        raise HTTPException(status_code=403, detail="permission_denied")
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    phone_number_id = account.get("phone_number_id")
    access_token = account.get("access_token")
    
    if not phone_number_id or not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        result = await whatsapp_api_service.get_phone_number_details(
            phone_number_id=phone_number_id,
            access_token=access_token
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/register/{account_id}")
async def register_phone(
    account_id: str,
    request: RegisterPhoneRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Enregistre un numéro pour l'API Cloud + définit le PIN 2FA
    POST /{PHONE_NUMBER_ID}/register
    
    ATTENTION: Cette opération est sensible et nécessite des permissions admin
    """
    current_user.require(PermissionCodes.ACCOUNTS_MANAGE, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    phone_number_id = account.get("phone_number_id")
    access_token = account.get("access_token")
    
    if not phone_number_id or not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        result = await whatsapp_api_service.register_phone_number(
            phone_number_id=phone_number_id,
            access_token=access_token,
            pin=request.pin
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/deregister/{account_id}")
async def deregister_phone(
    account_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Désenregistre un numéro (arrête d'être utilisable via l'API)
    POST /{PHONE_NUMBER_ID}/deregister
    
    ATTENTION: Cette opération est sensible et nécessite des permissions admin
    """
    current_user.require(PermissionCodes.ACCOUNTS_MANAGE, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    phone_number_id = account.get("phone_number_id")
    access_token = account.get("access_token")
    
    if not phone_number_id or not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        result = await whatsapp_api_service.deregister_phone_number(
            phone_number_id=phone_number_id,
            access_token=access_token
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/request-verification/{account_id}")
async def request_verification_code(
    account_id: str,
    request: RequestVerificationCodeRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Demande l'envoi du code de vérification sur le numéro
    POST /{PHONE_NUMBER_ID}/request_code
    """
    current_user.require(PermissionCodes.ACCOUNTS_MANAGE, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    phone_number_id = account.get("phone_number_id")
    access_token = account.get("access_token")
    
    if not phone_number_id or not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        result = await whatsapp_api_service.request_verification_code(
            phone_number_id=phone_number_id,
            access_token=access_token,
            code_method=request.code_method,
            language=request.language
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/verify/{account_id}")
async def verify_code(
    account_id: str,
    request: VerifyCodeRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Valide le code de vérification reçu (complète la procédure de registration)
    POST /{PHONE_NUMBER_ID}/verify_code
    """
    current_user.require(PermissionCodes.ACCOUNTS_MANAGE, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    phone_number_id = account.get("phone_number_id")
    access_token = account.get("access_token")
    
    if not phone_number_id or not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        result = await whatsapp_api_service.verify_code(
            phone_number_id=phone_number_id,
            access_token=access_token,
            code=request.code
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

