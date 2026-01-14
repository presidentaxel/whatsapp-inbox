"""
Routes pour l'authentification Google Drive OAuth2
"""
import logging
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.core.config import settings
from app.core.db import supabase, supabase_execute
from app.services.account_service import get_account_by_id
from app.services.message_service import backfill_media_to_google_drive

# Import pour invalider le cache
from app.services.account_service import invalidate_account_cache

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Google Drive"])

try:
    from google_auth_oauthlib.flow import Flow
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request as GoogleAuthRequest
    GOOGLE_OAUTH_AVAILABLE = True
except ImportError:
    GOOGLE_OAUTH_AVAILABLE = False
    logger.warning("⚠️ Google OAuth libraries not installed")


def _get_google_drive_service_from_account(account: dict):
    """Crée un service Google Drive à partir des tokens stockés dans le compte"""
    if not GOOGLE_OAUTH_AVAILABLE:
        raise ImportError("Google OAuth libraries not installed")
    
    access_token = account.get("google_drive_access_token")
    refresh_token = account.get("google_drive_refresh_token")
    token_expiry_str = account.get("google_drive_token_expiry")
    
    if not access_token or not refresh_token:
        raise ValueError("Google Drive tokens not configured")
    
    from datetime import datetime
    token_expiry = None
    if token_expiry_str:
        try:
            if isinstance(token_expiry_str, str):
                token_expiry = datetime.fromisoformat(token_expiry_str.replace('Z', '+00:00'))
            elif isinstance(token_expiry_str, datetime):
                token_expiry = token_expiry_str
        except Exception:
            pass
    
    credentials = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_DRIVE_CLIENT_ID,
        client_secret=settings.GOOGLE_DRIVE_CLIENT_SECRET,
        scopes=['https://www.googleapis.com/auth/drive']
    )
    
    if token_expiry:
        credentials.expiry = token_expiry
    
    # Rafraîchir le token si nécessaire
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(GoogleAuthRequest())
        # Mettre à jour dans la base de données (optionnel, pour optimiser)
    
    return build('drive', 'v3', credentials=credentials)


@router.get("/auth/google-drive/init")
async def init_google_drive_auth(
    request: Request,
    account_id: str = Query(..., description="ID du compte WhatsApp"),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Initie le flow OAuth2 pour Google Drive
    Retourne l'URL d'autorisation Google
    """
    try:
        if not GOOGLE_OAUTH_AVAILABLE:
            logger.error("❌ Google OAuth libraries not installed")
            raise HTTPException(status_code=500, detail="Google OAuth libraries not installed")
        
        current_user.require(PermissionCodes.ACCOUNTS_MANAGE)
        
        account = await get_account_by_id(account_id)
        if not account:
            logger.error(f"❌ Account not found: {account_id}")
            raise HTTPException(status_code=404, detail="account_not_found")
        
        # Vérifier la configuration avec des logs détaillés
        has_client_id = bool(settings.GOOGLE_DRIVE_CLIENT_ID)
        has_client_secret = bool(settings.GOOGLE_DRIVE_CLIENT_SECRET)
        redirect_uri = settings.GOOGLE_DRIVE_REDIRECT_URI
        
        # Auto-détecter l'URL de redirection depuis la requête si elle n'est pas configurée ou est localhost
        if not redirect_uri or redirect_uri.startswith("http://localhost"):
            try:
                base_url = str(request.base_url).rstrip('/')
                redirect_uri = f"{base_url}/api/auth/google-drive/callback"
                logger.info(f"🔍 Auto-detected redirect URI from request: {redirect_uri}")
            except Exception as e:
                logger.warning(f"⚠️ Could not auto-detect redirect URI: {e}")
        
        logger.info(f"🔍 [GOOGLE DRIVE INIT] Account: {account_id}, has_client_id: {has_client_id}, has_client_secret: {has_client_secret}, redirect_uri: {redirect_uri}")
        
        if not has_client_id or not has_client_secret:
            missing_vars = []
            if not has_client_id:
                missing_vars.append("GOOGLE_DRIVE_CLIENT_ID")
            if not has_client_secret:
                missing_vars.append("GOOGLE_DRIVE_CLIENT_SECRET")
            
            error_msg = f"Google Drive OAuth2 not configured. Missing environment variables: {', '.join(missing_vars)}. "
            error_msg += "Please set these variables in your Render dashboard (Environment tab) for the whatsapp-inbox-backend service."
            logger.error(f"❌ {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
        
        if not redirect_uri:
            logger.error("❌ Redirect URI not configured and could not be auto-detected")
            raise HTTPException(status_code=500, detail="GOOGLE_DRIVE_REDIRECT_URI not configured. Please set it in environment variables.")
        
        # Créer le flow OAuth2
        client_config = {
            "web": {
                "client_id": settings.GOOGLE_DRIVE_CLIENT_ID,
                "client_secret": settings.GOOGLE_DRIVE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri]
            }
        }
        
        flow = Flow.from_client_config(
            client_config,
            scopes=['https://www.googleapis.com/auth/drive'],
            redirect_uri=redirect_uri
        )
        
        # Créer l'URL d'autorisation avec state pour identifier le compte
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'  # Demander le consentement pour obtenir le refresh_token
        )
        
        # Encoder l'account_id dans le state
        import base64
        state_with_account = base64.urlsafe_b64encode(f"{state}:{account_id}".encode()).decode()
        
        # Ajouter le state modifié à l'URL
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        parsed = urlparse(authorization_url)
        params = parse_qs(parsed.query)
        params['state'] = [state_with_account]
        new_query = urlencode(params, doseq=True)
        final_url = urlunparse(parsed._replace(query=new_query))
        
        logger.info(f"✅ Google Drive OAuth URL generated for account {account_id}")
        return {"authorization_url": final_url}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error initializing Google Drive auth: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error initializing Google Drive auth: {str(e)}")


@router.get("/auth/google-drive/callback")
async def google_drive_callback(
    code: str = Query(..., description="Code d'autorisation OAuth2"),
    state: str = Query(..., description="State avec account_id"),
    error: str = Query(None, description="Erreur éventuelle")
):
    """
    Callback OAuth2 Google Drive
    Reçoit le code d'autorisation et stocke les tokens
    """
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    
    if not GOOGLE_OAUTH_AVAILABLE:
        raise HTTPException(status_code=500, detail="Google OAuth libraries not installed")
    
    try:
        # Décoder le state pour obtenir l'account_id
        import base64
        decoded_state = base64.urlsafe_b64decode(state.encode()).decode()
        original_state, account_id = decoded_state.split(':', 1)
    except Exception as e:
        logger.error(f"❌ Error decoding state: {e}")
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    if not settings.GOOGLE_DRIVE_CLIENT_ID or not settings.GOOGLE_DRIVE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google Drive OAuth2 not configured")
    
    # Créer le flow OAuth2
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_DRIVE_CLIENT_ID,
            "client_secret": settings.GOOGLE_DRIVE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.GOOGLE_DRIVE_REDIRECT_URI]
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=['https://www.googleapis.com/auth/drive'],
        redirect_uri=settings.GOOGLE_DRIVE_REDIRECT_URI
    )
    
    # Échanger le code contre les tokens
    flow.fetch_token(code=code)
    credentials = flow.credentials
    
    # Stocker les tokens dans la base de données
    await supabase_execute(
        supabase.table("whatsapp_accounts")
        .update({
            "google_drive_access_token": credentials.token,
            "google_drive_refresh_token": credentials.refresh_token,
            "google_drive_token_expiry": credentials.expiry.isoformat() if credentials.expiry else None,
            "google_drive_enabled": True
        })
        .eq("id", account_id)
    )
    
    logger.info(f"✅ Google Drive OAuth2 tokens stored for account {account_id}")
    
    # Invalider le cache du compte pour forcer le rechargement avec les nouveaux tokens
    invalidate_account_cache(account_id)
    logger.info(f"🔄 Account cache invalidated for account {account_id}")
    
    # Rediriger vers le frontend avec un message de succès
    frontend_url = settings.GOOGLE_DRIVE_REDIRECT_URI.replace("/api/auth/google-drive/callback", "")
    return RedirectResponse(url=f"{frontend_url}/settings?account={account_id}&google_drive_connected=true")


@router.get("/accounts/{account_id}/google-drive/folders")
async def list_google_drive_folders(
    account_id: str,
    parent_id: str = Query("root", description="ID du dossier parent (par défaut 'root')"),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Liste les dossiers Google Drive disponibles pour sélection
    """
    if not GOOGLE_OAUTH_AVAILABLE:
        raise HTTPException(status_code=500, detail="Google OAuth libraries not installed")
    
    current_user.require(PermissionCodes.ACCOUNTS_MANAGE)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    if not account.get("google_drive_access_token"):
        raise HTTPException(status_code=400, detail="Google Drive not connected for this account")
    
    try:
        service = _get_google_drive_service_from_account(account)
        
        # Liste uniquement les dossiers
        query = "mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id and parent_id != "root":
            query += f" and '{parent_id}' in parents"
        else:
            query += " and 'root' in parents"
        
        def list_folders():
            results = service.files().list(
                q=query,
                fields="files(id, name, parents)",
                spaces='drive',
                orderBy='name'
            ).execute()
            return results.get('files', [])
        
        folders = await run_in_threadpool(list_folders)
        
        # Ajouter "Racine" comme option
        folders_list = [{"id": "root", "name": "Racine du Drive"}]
        folders_list.extend([{"id": f["id"], "name": f["name"]} for f in folders])
        
        return {"folders": folders_list}
        
    except Exception as e:
        logger.error(f"❌ Error listing Google Drive folders: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error listing folders: {str(e)}")


@router.delete("/accounts/{account_id}/google-drive/disconnect")
async def disconnect_google_drive(
    account_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Déconnecte Google Drive d'un compte WhatsApp (supprime les tokens)
    """
    current_user.require(PermissionCodes.ACCOUNTS_MANAGE)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    # Supprimer les tokens
    await supabase_execute(
        supabase.table("whatsapp_accounts")
        .update({
            "google_drive_access_token": None,
            "google_drive_refresh_token": None,
            "google_drive_token_expiry": None,
            "google_drive_enabled": False
        })
        .eq("id", account_id)
    )
    
    # Invalider le cache du compte
    invalidate_account_cache(account_id)
    
    return {"status": "disconnected", "account_id": account_id}


@router.post("/accounts/{account_id}/google-drive/backfill")
async def backfill_google_drive(
    account_id: str,
    limit: int = Query(100, ge=1, le=500, description="Nombre maximum de médias à traiter"),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Upload les médias existants vers Google Drive pour un compte donné.
    Ne télécharge que les médias qui n'ont pas encore été uploadés.
    """
    current_user.require(PermissionCodes.ACCOUNTS_MANAGE)
    
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    # Vérifier la configuration Google Drive avec des logs détaillés
    google_drive_enabled = account.get("google_drive_enabled", False)
    has_access_token = bool(account.get("google_drive_access_token"))
    has_refresh_token = bool(account.get("google_drive_refresh_token"))
    # google_drive_connected peut ne pas être dans le record brut, on le calcule
    google_drive_connected = has_access_token and has_refresh_token
    
    logger.info(f"🔍 [BACKFILL CHECK] Account {account_id}: enabled={google_drive_enabled}, has_access_token={has_access_token}, has_refresh_token={has_refresh_token}, calculated_connected={google_drive_connected}")
    logger.info(f"🔍 [BACKFILL CHECK] Account keys: {list(account.keys())}")
    
    if not google_drive_enabled:
        raise HTTPException(status_code=400, detail="Google Drive is not enabled for this account. Please enable it in settings.")
    
    if not google_drive_connected:
        raise HTTPException(status_code=400, detail="Google Drive is not connected for this account. Please connect your Google account first.")
    
    try:
        result = await backfill_media_to_google_drive(account_id, limit)
        return result
    except Exception as e:
        logger.error(f"❌ Error during Google Drive backfill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Backfill failed: {str(e)}")
