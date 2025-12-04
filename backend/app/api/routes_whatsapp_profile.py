"""
Routes API pour la gestion du profil business WhatsApp
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.core.cache import invalidate_cache_pattern
from app.services.account_service import get_account_by_id
from app.services import whatsapp_api_service
from app.schemas.whatsapp import UpdateBusinessProfileRequest

router = APIRouter(prefix="/whatsapp/profile", tags=["WhatsApp Business Profile"])


@router.get("/{account_id}")
async def get_business_profile(
    account_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Récupère le profil business WhatsApp
    GET /{PHONE_NUMBER_ID}/whatsapp_business_profile
    
    Retourne les informations du profil:
    - about: Description courte
    - address: Adresse physique
    - description: Description longue
    - email: Email de contact
    - profile_picture_url: URL de l'image de profil
    - websites: Liste des sites web
    - vertical: Secteur d'activité
    """
    current_user.require(PermissionCodes.MESSAGES_VIEW, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    phone_number_id = account.get("phone_number_id")
    access_token = account.get("access_token")
    
    if not phone_number_id or not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    try:
        result = await whatsapp_api_service.get_business_profile(
            phone_number_id=phone_number_id,
            access_token=access_token
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{account_id}")
async def update_business_profile(
    account_id: str,
    request: UpdateBusinessProfileRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Met à jour le profil business WhatsApp
    POST /{PHONE_NUMBER_ID}/whatsapp_business_profile
    
    Champs modifiables:
    - about: Description courte (max 139 caractères)
    - address: Adresse physique
    - description: Description longue (max 512 caractères)
    - email: Email de contact
    - websites: Liste des sites web
    - vertical: Secteur d'activité (ex: "EDUCATION", "ENTERTAINMENT", "RETAIL")
    - profile_picture_handle: Media ID d'une image uploadée (pour changer la photo de profil)
    
    Secteurs disponibles:
    - AUTOMOTIVE, BEAUTY, APPAREL, EDU, ENTERTAINMENT, EVENT_PLANNING,
    - FINANCE, GROCERY, GOVT, HOTEL, HEALTH, NONPROFIT, PROF_SERVICES,
    - RETAIL, TRAVEL, RESTAURANT, NOT_A_BIZ, OTHER
    """
    current_user.require(PermissionCodes.ACCOUNTS_MANAGE, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    phone_number_id = account.get("phone_number_id")
    access_token = account.get("access_token")
    
    if not phone_number_id or not access_token:
        raise HTTPException(status_code=400, detail="account_not_configured")
    
    # Construire le payload en excluant les valeurs None (optimisé avec dict comprehension)
    profile_data = {
        k: v for k, v in {
            "about": request.about,
            "address": request.address,
            "description": request.description,
            "email": request.email,
            "websites": request.websites,
            "vertical": request.vertical,
            "profile_picture_handle": request.profile_picture_handle,
        }.items() if v is not None
    }
    
    if not profile_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    try:
        result = await whatsapp_api_service.update_business_profile(
            phone_number_id=phone_number_id,
            access_token=access_token,
            profile_data=profile_data
        )
        # Invalider le cache pour forcer le rechargement du profil
        await invalidate_cache_pattern(f"whatsapp_business_profile:{phone_number_id}")
        return {"success": True, "data": result}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"WhatsApp API error: {e.response.text}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="WhatsApp API timeout")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

