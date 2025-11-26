"""
Routes utilitaires pour l'API WhatsApp Business
"""
from fastapi import APIRouter, Depends, HTTPException
from app.core.config import settings
from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.account_service import get_account_by_id
from app.services import whatsapp_api_service

router = APIRouter(prefix="/whatsapp/utils", tags=["WhatsApp Utilities"])


@router.get("/debug-token/{account_id}")
async def debug_access_token(
    account_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Vérifie un token d'accès (scopes, expiration, etc.)
    GET /debug_token
    
    Retourne des informations sur le token:
    - app_id: ID de l'application
    - type: Type de token (USER ou PAGE)
    - application: Nom de l'application
    - expires_at: Date d'expiration (0 = jamais)
    - is_valid: Si le token est valide
    - scopes: Liste des permissions accordées
    - user_id: ID de l'utilisateur associé
    """
    current_user.require(PermissionCodes.ACCOUNTS_MANAGE, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    access_token = account.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    # Récupérer les credentials de l'app depuis settings ou account
    app_id = account.get("app_id") or settings.META_APP_ID
    app_secret = account.get("app_secret") or settings.META_APP_SECRET
    
    if not app_id or not app_secret:
        raise HTTPException(
            status_code=400,
            detail="META_APP_ID and META_APP_SECRET must be configured"
        )
    
    try:
        result = await whatsapp_api_service.debug_token(
            access_token=access_token,
            app_id=app_id,
            app_secret=app_secret
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/generate-app-token")
async def generate_app_access_token(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Génère un app access token
    GET /oauth/access_token
    
    Nécessite META_APP_ID et META_APP_SECRET dans la configuration.
    Utilisé pour les opérations d'administration.
    """
    # Vérifier que l'utilisateur est admin global
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    app_id = settings.META_APP_ID
    app_secret = settings.META_APP_SECRET
    
    if not app_id or not app_secret:
        raise HTTPException(
            status_code=400,
            detail="META_APP_ID and META_APP_SECRET must be configured in environment"
        )
    
    try:
        result = await whatsapp_api_service.get_app_access_token(
            app_id=app_id,
            app_secret=app_secret
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/validate-phone")
async def validate_phone_number(
    phone: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Valide et normalise un numéro de téléphone WhatsApp
    
    Le numéro doit être au format international.
    Exemples:
    - +33612345678
    - 33612345678
    - +1 555 123 4567
    
    Retourne le numéro normalisé sans + ni espaces
    """
    try:
        normalized = whatsapp_api_service.validate_phone_number(phone)
        return {
            "success": True,
            "data": {
                "original": phone,
                "normalized": normalized
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

