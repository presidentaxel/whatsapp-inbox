from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta
import logging
import os

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser
from app.core.db import supabase, supabase_execute
from app.core.config import settings
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

router = APIRouter()


class InviteUserRequest(BaseModel):
    email: EmailStr
    display_name: Optional[str] = None


class ResendInviteRequest(BaseModel):
    email: EmailStr


@router.post("/invite")
async def invite_user(
    request: InviteUserRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Invite un nouvel utilisateur par email
    L'utilisateur recevra un email avec un lien d'invitation
    """
    # Vérifier que l'utilisateur a les permissions nécessaires
    # Pour l'instant, on permet à tous les utilisateurs authentifiés d'inviter
    # Vous pouvez ajouter une vérification de permission ici si nécessaire
    
    try:
        # Vérifier si l'utilisateur existe déjà
        def _check_user():
            result = supabase.auth.admin.list_users()
            # La réponse peut être une liste ou un objet avec un attribut users
            if isinstance(result, list):
                return result
            elif hasattr(result, 'users'):
                return result.users
            elif hasattr(result, 'data'):
                return result.data
            return []
        
        users_list = await run_in_threadpool(_check_user)
        existing_user = next(
            (u for u in users_list if hasattr(u, 'email') and u.email == request.email),
            None
        )
        
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail="user_already_exists"
            )
        
        # Préparer les données utilisateur
        user_data = {
            "email": request.email,
            "email_confirm": False,  # L'utilisateur devra confirmer via le lien d'invitation
        }
        
        if request.display_name:
            user_data["user_metadata"] = {
                "full_name": request.display_name
            }
        
        # Envoyer l'invitation via Supabase Admin API
        def _invite_user():
            return supabase.auth.admin.invite_user_by_email(
                request.email,
                {
                    "data": user_data.get("user_metadata", {}),
                    "redirect_to": f"{settings.SUPABASE_URL.replace('/rest/v1', '')}/auth/v1/callback?invite_token="
                }
            )
        
        invite_result = await run_in_threadpool(_invite_user)
        
        if invite_result.user:
            # Créer l'entrée dans app_users si nécessaire
            # Elle sera créée automatiquement lors de la première connexion
            logger.info(f"✅ User invitation sent to {request.email}")
            
            return {
                "success": True,
                "message": "invitation_sent",
                "email": request.email
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="invitation_failed"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error inviting user: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"invitation_error: {str(e)}"
        )


@router.post("/resend-invite")
async def resend_invite(
    request: ResendInviteRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Renvoie une invitation à un utilisateur
    """
    try:
        # Vérifier si l'utilisateur existe
        def _check_user():
            result = supabase.auth.admin.list_users()
            # La réponse peut être une liste ou un objet avec un attribut users
            if isinstance(result, list):
                return result
            elif hasattr(result, 'users'):
                return result.users
            elif hasattr(result, 'data'):
                return result.data
            return []
        
        users_list = await run_in_threadpool(_check_user)
        user = next(
            (u for u in users_list if hasattr(u, 'email') and u.email == request.email),
            None
        )
        
        if not user:
            raise HTTPException(
                status_code=404,
                detail="user_not_found"
            )
        
        # Vérifier si l'utilisateur est déjà confirmé
        if user.email_confirmed_at:
            raise HTTPException(
                status_code=400,
                detail="user_already_confirmed"
            )
        
        # Construire l'URL de redirection
        frontend_url = os.getenv("FRONTEND_URL") or "http://localhost:5173"
        redirect_url = f"{frontend_url}/register"
        
        # Régénérer et renvoyer l'invitation
        def _resend_invite():
            return supabase.auth.admin.invite_user_by_email(
                request.email,
                {
                    "data": user.user_metadata or {},
                    "redirect_to": redirect_url
                }
            )
        
        invite_result = await run_in_threadpool(_resend_invite)
        
        if invite_result.user:
            logger.info(f"✅ Invitation resent to {request.email}")
            return {
                "success": True,
                "message": "invitation_resent",
                "email": request.email
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="resend_failed"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resending invitation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"resend_error: {str(e)}"
        )


@router.get("/pending-invites")
async def get_pending_invites(
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Liste les invitations en attente
    """
    try:
        def _list_users():
            result = supabase.auth.admin.list_users()
            # La réponse peut être une liste ou un objet avec un attribut users
            if isinstance(result, list):
                return result
            elif hasattr(result, 'users'):
                return result.users
            elif hasattr(result, 'data'):
                return result.data
            return []
        
        users_list = await run_in_threadpool(_list_users)
        
        pending_invites = [
            {
                "email": getattr(user, 'email', None),
                "created_at": getattr(user, 'created_at', None),
                "invited_at": getattr(user, 'invited_at', None),
                "user_metadata": getattr(user, 'user_metadata', {})
            }
            for user in users_list
            if hasattr(user, 'email') and not getattr(user, 'email_confirmed_at', None) and getattr(user, 'invited_at', None)
        ]
        
        return {
            "success": True,
            "invites": pending_invites
        }
        
    except Exception as e:
        logger.error(f"Error listing pending invites: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"list_error: {str(e)}"
        )

