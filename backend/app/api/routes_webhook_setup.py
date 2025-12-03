"""
Routes pour configurer et vérifier les webhooks WhatsApp
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.core.config import settings
from app.services.account_service import get_account_by_id
from app.services import whatsapp_api_service

router = APIRouter(prefix="/webhook", tags=["Webhook Setup"])
logger = logging.getLogger(__name__)


@router.post("/setup/{account_id}")
async def setup_webhook_subscription(
    account_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Configure et active les abonnements webhook pour un compte WhatsApp
    
    Cette route:
    1. Vérifie que le compte existe
    2. S'abonne aux événements WhatsApp via l'API Meta
    3. Retourne le statut de l'abonnement
    """
    current_user.require(PermissionCodes.ACCOUNTS_MANAGE, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    waba_id = account.get("waba_id") or settings.WHATSAPP_BUSINESS_ACCOUNT_ID
    access_token = account.get("access_token") or settings.WHATSAPP_TOKEN
    
    if not waba_id:
        raise HTTPException(
            status_code=400,
            detail="waba_id not configured. Set WHATSAPP_BUSINESS_ACCOUNT_ID in .env or add waba_id to whatsapp_accounts table."
        )
    
    if not access_token:
        raise HTTPException(status_code=400, detail="access_token not configured")
    
    try:
        # S'abonner aux webhooks
        result = await whatsapp_api_service.subscribe_to_webhooks(
            waba_id=waba_id,
            access_token=access_token
        )
        
        logger.info(f"✅ Webhook subscription successful for account {account_id}, WABA {waba_id}")
        
        return {
            "success": True,
            "message": "Webhook subscription activated",
            "waba_id": waba_id,
            "account_id": account_id,
            "data": result,
            "webhook_url": f"https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp",
            "verify_token": settings.WHATSAPP_VERIFY_TOKEN[:20] + "..." if settings.WHATSAPP_VERIFY_TOKEN else None
        }
    except Exception as e:
        logger.error(f"❌ Error subscribing to webhooks: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Failed to subscribe: {str(e)}")


@router.get("/status/{account_id}")
async def get_webhook_status(
    account_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Vérifie le statut des abonnements webhook pour un compte
    """
    current_user.require(PermissionCodes.ACCOUNTS_VIEW, account_id)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    waba_id = account.get("waba_id") or settings.WHATSAPP_BUSINESS_ACCOUNT_ID
    access_token = account.get("access_token") or settings.WHATSAPP_TOKEN
    
    if not waba_id or not access_token:
        return {
            "subscribed": False,
            "message": "WABA ID or access token not configured",
            "webhook_url": f"https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp"
        }
    
    try:
        # Récupérer les abonnements
        result = await whatsapp_api_service.get_subscribed_apps(
            waba_id=waba_id,
            access_token=access_token
        )
        
        apps = result.get("data", [])
        
        # Vérifier les messages récents pour voir si les webhooks arrivent
        from datetime import datetime, timedelta
        from app.core.db import supabase_execute, supabase
        
        yesterday = datetime.utcnow() - timedelta(days=1)
        messages_result = await supabase_execute(
            supabase.table("messages")
            .select("id, timestamp")
            .eq("direction", "inbound")
            .gte("timestamp", yesterday.isoformat())
            .limit(1)
        )
        
        recent_messages = messages_result.data or []
        
        return {
            "subscribed": len(apps) > 0,
            "subscriptions": apps,
            "waba_id": waba_id,
            "webhook_url": f"https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp",
            "verify_token_configured": bool(settings.WHATSAPP_VERIFY_TOKEN),
            "recent_messages_count": len(recent_messages),
            "last_message_received": recent_messages[0].get("timestamp") if recent_messages else None,
            "webhook_receiving": len(recent_messages) > 0
        }
    except Exception as e:
        logger.error(f"Error checking webhook status: {e}", exc_info=True)
        return {
            "subscribed": False,
            "error": str(e),
            "webhook_url": f"https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp"
        }

