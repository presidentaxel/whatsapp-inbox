"""
Routes API pour la gestion du WABA (WhatsApp Business Account)
"""
from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.account_service import get_account_by_id
from app.services import whatsapp_api_service

router = APIRouter(prefix="/whatsapp/waba", tags=["WhatsApp Business Account"])


@router.get("/details/{account_id}")
async def get_waba_details(
    account_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Récupère les détails d'un WABA (WhatsApp Business Account)
    GET /{WABA-ID}
    
    Retourne:
    - id: ID du WABA
    - name: Nom du WABA
    - timezone_id: Fuseau horaire
    - message_template_namespace: Namespace pour les templates
    - account_review_status: Statut de review du compte
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
        result = await whatsapp_api_service.get_waba_details(
            waba_id=waba_id,
            access_token=access_token
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/owned/{account_id}")
async def list_owned_wabas(
    account_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Liste les WABAs possédés par un Business Manager
    GET /{BUSINESS-ID}/owned_whatsapp_business_accounts
    
    Note: Nécessite le Business ID qui doit être configuré dans l'account
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
    
    business_id = account.get("business_id")
    access_token = account.get("access_token")
    
    if not business_id:
        raise HTTPException(
            status_code=400,
            detail="business_id not configured in account. Please add it to whatsapp_accounts table."
        )
    
    if not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        result = await whatsapp_api_service.list_owned_wabas(
            business_id=business_id,
            access_token=access_token
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/client/{account_id}")
async def list_client_wabas(
    account_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Liste les WABAs partagés en tant que partenaire/tech provider
    GET /{BUSINESS-ID}/client_whatsapp_business_accounts
    
    Note: Nécessite le Business ID qui doit être configuré dans l'account
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
    
    business_id = account.get("business_id")
    access_token = account.get("access_token")
    
    if not business_id:
        raise HTTPException(
            status_code=400,
            detail="business_id not configured in account. Please add it to whatsapp_accounts table."
        )
    
    if not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        result = await whatsapp_api_service.list_client_wabas(
            business_id=business_id,
            access_token=access_token
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/webhooks/subscribe/{account_id}")
async def subscribe_webhooks(
    account_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Abonne l'app aux événements WhatsApp pour ce WABA
    POST /{WABA-ID}/subscribed_apps
    
    Cette action permet de recevoir les webhooks pour:
    - Messages reçus
    - Statuts de messages
    - Changements de profil
    - etc.
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
        result = await whatsapp_api_service.subscribe_to_webhooks(
            waba_id=waba_id,
            access_token=access_token
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/webhooks/unsubscribe/{account_id}")
async def unsubscribe_webhooks(
    account_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Se désabonne des événements WhatsApp pour ce WABA
    DELETE /{WABA-ID}/subscribed_apps
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
        result = await whatsapp_api_service.unsubscribe_from_webhooks(
            waba_id=waba_id,
            access_token=access_token
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/webhooks/subscriptions/{account_id}")
async def get_webhook_subscriptions(
    account_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Récupère la liste des apps abonnées aux webhooks de ce WABA
    GET /{WABA-ID}/subscribed_apps
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
        result = await whatsapp_api_service.get_subscribed_apps(
            waba_id=waba_id,
            access_token=access_token
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

