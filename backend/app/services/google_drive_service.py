"""
Service pour gérer l'upload automatique de fichiers vers Google Drive avec OAuth2
Organise les fichiers par numéro de téléphone (un dossier par numéro)
"""
import logging
from typing import Optional, Dict, Any
from io import BytesIO
from datetime import datetime
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

# Import optionnel - on essaie d'importer Google Drive API
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    from googleapiclient.errors import HttpError
    from google.auth.transport.requests import Request as GoogleAuthRequest
    GOOGLE_DRIVE_AVAILABLE = True
except ImportError:
    GOOGLE_DRIVE_AVAILABLE = False
    logger.warning("⚠️ Google Drive API libraries not installed. Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")


def _find_or_create_folder(service, parent_folder_id: Optional[str], folder_name: str) -> Optional[str]:
    """
    Trouve un dossier dans le dossier parent (ou à la racine), ou le crée s'il n'existe pas
    
    Args:
        service: Service Google Drive
        parent_folder_id: ID du dossier parent (None pour la racine)
        folder_name: Nom du dossier à trouver/créer
    
    Returns:
        ID du dossier trouvé ou créé, ou None en cas d'erreur
    """
    try:
        # Rechercher le dossier
        if parent_folder_id:
            query = f"name='{folder_name}' and '{parent_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        else:
            query = f"name='{folder_name}' and 'root' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        
        results = service.files().list(
            q=query,
            fields="files(id, name)",
            spaces='drive'
        ).execute()
        
        folders = results.get('files', [])
        if folders:
            # Le dossier existe déjà
            return folders[0]['id']
        
        # Créer le dossier
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
        }
        if parent_folder_id:
            file_metadata['parents'] = [parent_folder_id]
        
        folder = service.files().create(
            body=file_metadata,
            fields='id'
        ).execute()
        
        logger.info(f"✅ Created Google Drive folder: {folder_name} (ID: {folder.get('id')})")
        return folder.get('id')
        
    except HttpError as error:
        logger.error(f"❌ Error finding/creating Google Drive folder '{folder_name}': {error}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error in _find_or_create_folder: {e}", exc_info=True)
        return None


def _upload_file_to_drive(
    service,
    folder_id: Optional[str],
    file_data: bytes,
    filename: str,
    mime_type: str = 'application/octet-stream'
) -> Optional[str]:
    """
    Upload un fichier dans un dossier Google Drive (ou à la racine si folder_id est None)
    
    Args:
        service: Service Google Drive
        folder_id: ID du dossier de destination (None pour la racine)
        file_data: Données binaires du fichier
        filename: Nom du fichier
        mime_type: Type MIME du fichier
    
    Returns:
        ID du fichier uploadé, ou None en cas d'erreur
    """
    try:
        file_metadata = {
            'name': filename,
        }
        if folder_id:
            file_metadata['parents'] = [folder_id]
        
        media = MediaIoBaseUpload(
            BytesIO(file_data),
            mimetype=mime_type,
            resumable=True
        )
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name'
        ).execute()
        
        logger.info(f"✅ Uploaded file to Google Drive: {filename} (ID: {file.get('id')})")
        return file.get('id')
        
    except HttpError as error:
        logger.error(f"❌ Error uploading file '{filename}' to Google Drive: {error}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error uploading file to Google Drive: {e}", exc_info=True)
        return None


async def upload_document_to_google_drive(
    account: Dict[str, Any],
    phone_number: str,
    file_data: bytes,
    filename: str,
    mime_type: str = 'application/octet-stream'
) -> Optional[str]:
    """
    Upload un document vers Google Drive, organisé par numéro de téléphone
    
    Args:
        account: Dictionnaire du compte WhatsApp avec les tokens Google Drive
        phone_number: Numéro de téléphone du contact (utilisé pour créer/trouver le dossier)
        file_data: Données binaires du fichier
        filename: Nom du fichier
        mime_type: Type MIME du fichier
    
    Returns:
        ID du fichier uploadé dans Google Drive, ou None en cas d'erreur
    """
    if not GOOGLE_DRIVE_AVAILABLE:
        logger.warning("⚠️ Google Drive API not available, skipping upload")
        return None
    
    access_token = account.get("google_drive_access_token")
    refresh_token = account.get("google_drive_refresh_token")
    token_expiry_str = account.get("google_drive_token_expiry")
    
    if not access_token or not refresh_token:
        logger.warning(f"⚠️ Google Drive tokens not configured for account {account.get('id')}")
        return None
    
    try:
        from app.core.config import settings
        
        # Parser la date d'expiration si disponible
        token_expiry = None
        if token_expiry_str:
            try:
                if isinstance(token_expiry_str, str):
                    token_expiry = datetime.fromisoformat(token_expiry_str.replace('Z', '+00:00'))
                elif isinstance(token_expiry_str, datetime):
                    token_expiry = token_expiry_str
            except Exception as e:
                logger.warning(f"⚠️ Could not parse token expiry: {e}")
        
        # Créer les credentials
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
            try:
                credentials.refresh(GoogleAuthRequest())
                # Mettre à jour les tokens dans la base de données
                from app.core.db import supabase, supabase_execute
                await supabase_execute(
                    supabase.table("whatsapp_accounts")
                    .update({
                        "google_drive_access_token": credentials.token,
                        "google_drive_token_expiry": credentials.expiry.isoformat() if credentials.expiry else None
                    })
                    .eq("id", account["id"])
                )
            except Exception as refresh_error:
                logger.error(f"❌ Error refreshing Google Drive token: {refresh_error}")
                return None
        
        # Créer le service Google Drive
        service = build('drive', 'v3', credentials=credentials)
        
        root_folder_id = account.get("google_drive_folder_id")
        
        # Nettoyer le numéro de téléphone pour créer un nom de dossier valide
        safe_phone_number = phone_number.replace('+', 'plus').replace(' ', '_').replace('-', '_')
        
        # Trouver ou créer le dossier pour ce numéro de téléphone
        folder_id = await run_in_threadpool(
            _find_or_create_folder,
            service,
            root_folder_id,
            safe_phone_number
        )
        
        if not folder_id:
            logger.error(f"❌ Failed to find/create folder for phone number: {phone_number}")
            return None
        
        # Upload le fichier dans ce dossier
        file_id = await run_in_threadpool(
            _upload_file_to_drive,
            service,
            folder_id,
            file_data,
            filename,
            mime_type
        )
        
        if file_id:
            logger.info(f"✅ Document uploaded to Google Drive: account_id={account.get('id')}, phone={phone_number}, file={filename}, drive_file_id={file_id}")
        
        return file_id
        
    except Exception as e:
        logger.error(f"❌ Error uploading document to Google Drive: account_id={account.get('id')}, phone={phone_number}, error={e}", exc_info=True)
        return None
