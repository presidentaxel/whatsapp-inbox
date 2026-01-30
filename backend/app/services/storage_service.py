"""
Service pour gérer le stockage d'images dans Supabase Storage
"""
import asyncio
import logging
from typing import Optional, Dict, Any
from io import BytesIO
from datetime import datetime, timedelta, timezone
from starlette.concurrency import run_in_threadpool

from app.core.db import supabase, supabase_execute
from app.core.config import settings
from app.core.pg import execute as pg_execute, fetch_all, fetch_one, get_pool

logger = logging.getLogger(__name__)

# Nom du bucket pour les images de profil
PROFILE_PICTURES_BUCKET = "profile-pictures"
# Nom du bucket pour les médias de messages (images, vidéos, documents)
MESSAGE_MEDIA_BUCKET = "message-media"
# Nom du bucket pour les images de templates
TEMPLATE_MEDIA_BUCKET = "template-media"


async def _upload_profile_picture_task(
    contact_id: str,
    image_data: bytes,
    content_type: str = "image/jpeg"
) -> Optional[str]:
    """
    Tâche asynchrone pour uploader une image de profil sans bloquer le processus principal.
    """
    try:
        # Nom du fichier : contact_id.jpg
        file_name = f"{contact_id}.jpg"
        file_path = f"{file_name}"
        
        # Vérifier la taille du fichier
        file_size = len(image_data)
        max_size = settings.MAX_MEDIA_UPLOAD_SIZE
        
        if file_size > max_size:
            size_mb = file_size / (1024 * 1024)
            max_size_mb = max_size / (1024 * 1024)
            logger.warning(
                f"⚠️ Profile picture too large: contact_id={contact_id}, "
                f"size={size_mb:.2f}MB, max={max_size_mb:.2f}MB. Skipping upload."
            )
            return None
        
        # Upload dans Supabase Storage
        def _upload():
            try:
                return supabase.storage.from_(PROFILE_PICTURES_BUCKET).upload(
                    path=file_path,
                    file=image_data,
                    file_options={
                        "content-type": content_type,
                        "upsert": "true"  # Remplacer si existe déjà
                    }
                )
            except Exception as upload_error:
                error_str = str(upload_error)
                if "413" in error_str or "payload too large" in error_str.lower():
                    logger.warning(f"⚠️ Profile picture too large for Supabase: contact_id={contact_id}")
                    return None
                raise
        
        result = await run_in_threadpool(_upload)
        
        if result:
            # Récupérer l'URL publique
            public_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/{PROFILE_PICTURES_BUCKET}/{file_path}"
            
            logger.info(f"✅ Profile picture uploaded to Supabase Storage: {public_url}")
            return public_url
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Error uploading profile picture to Supabase Storage: {e}", exc_info=True)
        return None


async def upload_profile_picture(
    contact_id: str,
    image_data: bytes,
    content_type: str = "image/jpeg",
    async_upload: bool = True
) -> Optional[str]:
    """
    Upload une image de profil dans Supabase Storage.
    Par défaut, l'upload est fait de manière asynchrone et non-bloquante.
    
    Args:
        contact_id: ID du contact (utilisé comme nom de fichier)
        image_data: Données binaires de l'image
        content_type: Type MIME de l'image (défaut: image/jpeg)
        async_upload: Si True, l'upload se fait en arrière-plan (défaut: True)
    
    Returns:
        URL publique de l'image ou None en cas d'erreur
        Si async_upload=True, retourne None immédiatement et l'upload se fait en arrière-plan
    """
    if async_upload:
        # Lancer l'upload dans une tâche asynchrone séparée
        logger.info(f"🚀 [ASYNC UPLOAD] Creating async profile picture upload task: contact_id={contact_id}")
        asyncio.create_task(_upload_profile_picture_task(
            contact_id=contact_id,
            image_data=image_data,
            content_type=content_type
        ))
        return None  # Retourner None car l'upload est asynchrone
    else:
        # Upload synchrone (pour compatibilité)
        return await _upload_profile_picture_task(contact_id, image_data, content_type)


async def download_and_store_profile_picture(
    contact_id: str,
    image_url: str,
    async_upload: bool = True
) -> Optional[str]:
    """
    Télécharge une image depuis une URL et la stocke dans Supabase Storage.
    Par défaut, l'upload est fait de manière asynchrone et non-bloquante.
    
    Args:
        contact_id: ID du contact
        image_url: URL de l'image à télécharger
        async_upload: Si True, l'upload se fait en arrière-plan (défaut: True)
    
    Returns:
        URL publique Supabase de l'image ou None en cas d'erreur
        Si async_upload=True, retourne None immédiatement et l'upload se fait en arrière-plan
    """
    try:
        import httpx
        
        # Télécharger l'image
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(image_url)
            response.raise_for_status()
            
            # Détecter le content-type
            content_type = response.headers.get("content-type", "image/jpeg")
            image_data = response.content
            
            # Upload dans Supabase Storage (asynchrone par défaut)
            return await upload_profile_picture(
                contact_id=contact_id,
                image_data=image_data,
                content_type=content_type,
                async_upload=async_upload
            )
            
    except Exception as e:
        logger.error(f"❌ Error downloading and storing profile picture: {e}", exc_info=True)
        return None


async def delete_profile_picture(contact_id: str) -> bool:
    """
    Supprime une image de profil de Supabase Storage
    
    Args:
        contact_id: ID du contact
    
    Returns:
        True si supprimé avec succès, False sinon
    """
    try:
        file_path = f"{contact_id}.jpg"
        
        def _delete():
            return supabase.storage.from_(PROFILE_PICTURES_BUCKET).remove([file_path])
        
        result = await run_in_threadpool(_delete)
        logger.info(f"✅ Profile picture deleted: {file_path}")
        return True
        
    except Exception as e:
        logger.warning(f"⚠️ Error deleting profile picture: {e}")
        return False


# ============================================================================
# MESSAGE MEDIA STORAGE
# ============================================================================

async def upload_message_media(
    message_id: str,
    media_data: bytes,
    content_type: str,
    filename: Optional[str] = None
) -> Optional[str]:
    """
    Upload un média de message dans Supabase Storage
    
    Args:
        message_id: ID du message (utilisé comme nom de fichier)
        media_data: Données binaires du média
        content_type: Type MIME du média
        filename: Nom de fichier original (optionnel)
    
    Returns:
        URL publique du média ou None en cas d'erreur
    """
    try:
        # Vérifier la taille du fichier avant l'upload
        file_size = len(media_data)
        max_size = settings.MAX_MEDIA_UPLOAD_SIZE
        
        if file_size > max_size:
            size_mb = file_size / (1024 * 1024)
            max_size_mb = max_size / (1024 * 1024)
            logger.warning(
                f"⚠️ File too large to upload: message_id={message_id}, "
                f"size={size_mb:.2f}MB, max={max_size_mb:.2f}MB. "
                f"Skipping upload to avoid 413 error."
            )
            return None
        
        # Déterminer l'extension selon le content-type
        extension_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "video/mp4": ".mp4",
            "video/quicktime": ".mov",
            "audio/mpeg": ".mp3",
            "audio/ogg": ".ogg",
            "audio/wav": ".wav",
            "application/pdf": ".pdf",
            "application/msword": ".doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        }
        
        extension = extension_map.get(content_type, "")
        if filename:
            # Extraire l'extension du nom de fichier si disponible
            if "." in filename:
                extension = "." + filename.rsplit(".", 1)[1]
        
        # Nom du fichier : message_id + extension
        file_name = f"{message_id}{extension}"
        file_path = file_name
        
        # Upload dans Supabase Storage
        size_mb = file_size / (1024 * 1024)
        logger.info(f"📤 Uploading to bucket '{MESSAGE_MEDIA_BUCKET}': path={file_path}, size={size_mb:.2f}MB")
        
        def _upload():
            try:
                # Vérifier d'abord que le bucket existe
                try:
                    buckets = supabase.storage.list_buckets()
                    bucket_names = [b.name if hasattr(b, 'name') else (b.get("name") if isinstance(b, dict) else str(b)) for b in buckets]
                    if MESSAGE_MEDIA_BUCKET not in bucket_names:
                        error_msg = f"Bucket '{MESSAGE_MEDIA_BUCKET}' does not exist! Available buckets: {bucket_names}"
                        logger.error(f"❌ {error_msg}")
                        raise ValueError(error_msg)
                except Exception as bucket_check_error:
                    logger.warning(f"⚠️ Could not verify bucket existence: {bucket_check_error}")
                    # Continue quand même, peut-être que c'est juste un problème de permissions pour lister
                
                result = supabase.storage.from_(MESSAGE_MEDIA_BUCKET).upload(
                    path=file_path,
                    file=media_data,
                    file_options={
                        "content-type": content_type,
                        "upsert": "true"  # Remplacer si existe déjà
                    }
                )
                logger.info(f"✅ Upload result: {result}")
                return result
            except Exception as upload_error:
                error_str = str(upload_error)
                # Gérer spécifiquement l'erreur 413 (Payload too large)
                if "413" in error_str or "payload too large" in error_str.lower() or "exceeded the maximum" in error_str.lower():
                    logger.error(
                        f"❌ File too large for Supabase Storage: message_id={message_id}, "
                        f"size={size_mb:.2f}MB. Supabase rejected the upload."
                    )
                    # Ne pas lever l'exception, retourner None pour gérer gracieusement
                    return None
                # Messages d'erreur plus explicites
                elif "bucket" in error_str.lower() or "not found" in error_str.lower():
                    logger.error(f"❌ Bucket error: {upload_error}")
                    logger.error(f"   Vérifiez que le bucket '{MESSAGE_MEDIA_BUCKET}' existe dans Supabase Dashboard > Storage")
                elif "permission" in error_str.lower() or "forbidden" in error_str.lower() or "401" in error_str or "403" in error_str:
                    logger.error(f"❌ Permission error: {upload_error}")
                    logger.error(f"   Vérifiez que SUPABASE_KEY est la clé 'service_role' (pas 'anon')")
                    logger.error(f"   Les uploads nécessitent la clé service_role pour bypasser RLS")
                else:
                    logger.error(f"❌ Upload error in thread: {upload_error}", exc_info=True)
                raise
        
        result = await run_in_threadpool(_upload)
        
        if result:
            # Récupérer l'URL publique
            public_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/{MESSAGE_MEDIA_BUCKET}/{file_path}"
            
            logger.info(f"✅ Message media uploaded to Supabase Storage: {public_url}")
            return public_url
        else:
            logger.warning(f"⚠️ Upload returned None or empty result")
        
        return None
        
    except Exception as e:
        error_str = str(e)
        # Gérer spécifiquement l'erreur 413 même si elle passe à travers
        if "413" in error_str or "payload too large" in error_str.lower() or "exceeded the maximum" in error_str.lower():
            logger.warning(
                f"⚠️ File too large for Supabase Storage: message_id={message_id}. "
                f"Upload skipped to avoid blocking the process."
            )
            return None
        logger.error(f"❌ Error uploading message media to Supabase Storage: message_id={message_id}, error={e}", exc_info=True)
        return None


async def _upload_media_task(
    message_id: str,
    media_data: bytes,
    content_type: str,
    filename: Optional[str] = None,
    account: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Tâche asynchrone pour uploader un média sans bloquer le processus principal.
    Cette fonction est appelée dans une tâche séparée.
    
    Args:
        message_id: ID du message
        media_data: Données binaires du média
        content_type: Type MIME du média
        filename: Nom de fichier original (optionnel)
        account: Compte WhatsApp (optionnel, pour Google Drive)
    """
    try:
        logger.info(f"🚀 [ASYNC UPLOAD] Starting async upload task: message_id={message_id}")
        result = await upload_message_media(
            message_id=message_id,
            media_data=media_data,
            content_type=content_type,
            filename=filename
        )
        
        if result:
            logger.info(f"✅ [ASYNC UPLOAD] Media uploaded successfully: message_id={message_id}, storage_url={result}")
            # Mettre à jour le message avec l'URL de stockage
            if get_pool():
                await pg_execute(
                    "UPDATE messages SET storage_url = $2 WHERE id = $1::uuid",
                    message_id, result,
                )
            else:
                await supabase_execute(
                    supabase.table("messages").update({"storage_url": result}).eq("id", message_id)
                )
            logger.info(f"✅ [ASYNC UPLOAD] Message updated with storage_url: message_id={message_id}")
            
            # Gérer Google Drive si configuré et si account est fourni
            if account:
                try:
                    import asyncio
                    from app.services.message_service import _upload_to_google_drive_async
                    
                    google_drive_enabled = account.get("google_drive_enabled")
                    google_drive_connected = account.get("google_drive_connected")
                    has_access_token = bool(account.get("google_drive_access_token"))
                    has_refresh_token = bool(account.get("google_drive_refresh_token"))
                    
                    if (google_drive_enabled and 
                        google_drive_connected and 
                        has_access_token and 
                        has_refresh_token):
                        
                        logger.info(f"✅ [GOOGLE DRIVE] All conditions met, creating upload task for message_id={message_id}")
                        # Créer une tâche asynchrone pour l'upload Google Drive (non-bloquant)
                        asyncio.create_task(_upload_to_google_drive_async(
                            message_db_id=message_id,
                            account=account,
                            storage_url=result,
                            filename=filename or f"file_{message_id}",
                            mime_type=content_type
                        ))
                        logger.info(f"🚀 [GOOGLE DRIVE] Upload task created successfully for message_id={message_id}")
                except Exception as gd_error:
                    logger.warning(f"⚠️ [GOOGLE DRIVE] Error creating Google Drive upload task: {gd_error}")
        else:
            logger.warning(f"⚠️ [ASYNC UPLOAD] Media upload failed: message_id={message_id}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ [ASYNC UPLOAD] Error in upload task: message_id={message_id}, error={e}", exc_info=True)
        return None


async def download_and_store_message_media(
    message_id: str,
    media_url: str,
    content_type: str,
    filename: Optional[str] = None,
    access_token: Optional[str] = None,
    account: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Télécharge un média depuis une URL (WhatsApp) et le stocke dans Supabase Storage.
    L'upload vers Supabase est fait de manière asynchrone et non-bloquante.
    
    Args:
        message_id: ID du message
        media_url: URL du média à télécharger (WhatsApp Graph API)
        content_type: Type MIME du média
        filename: Nom de fichier original (optionnel)
        access_token: Token d'accès WhatsApp (requis pour télécharger depuis WhatsApp)
        account: Compte WhatsApp (optionnel, pour Google Drive)
    
    Returns:
        URL publique Supabase du média ou None en cas d'erreur
        Note: L'upload se fait en arrière-plan, cette fonction retourne immédiatement
    """
    try:
        import httpx
        from app.core.http_client import get_http_client_for_media
        
        logger.info(f"📥 Downloading media from WhatsApp: message_id={message_id}, url_length={len(media_url)}")
        
        # Préparer les headers avec le token si fourni
        headers = {}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
            logger.debug(f"🔑 Using access token for media download: message_id={message_id}")
        
        # Télécharger le média avec le client HTTP configuré
        client = await get_http_client_for_media()
        response = await client.get(media_url, headers=headers)
        response.raise_for_status()
        
        # Utiliser le content-type fourni ou celui de la réponse
        detected_content_type = response.headers.get("content-type", content_type)
        media_data = response.content
        
        size_mb = len(media_data) / (1024 * 1024)
        logger.info(f"✅ Media downloaded: message_id={message_id}, size={size_mb:.2f}MB, content_type={detected_content_type}")
        
        # Lancer l'upload dans une tâche asynchrone séparée (non-bloquant)
        logger.info(f"🚀 [ASYNC UPLOAD] Creating async upload task: message_id={message_id}")
        asyncio.create_task(_upload_media_task(
            message_id=message_id,
            media_data=media_data,
            content_type=detected_content_type,
            filename=filename,
            account=account
        ))
        
        # Retourner immédiatement sans attendre l'upload
        # L'upload se fera en arrière-plan et mettra à jour le message automatiquement
        logger.info(f"✅ [ASYNC UPLOAD] Upload task created, returning immediately: message_id={message_id}")
        return None  # Retourner None car l'upload est asynchrone
        
    except Exception as e:
        logger.error(f"❌ Error downloading and storing message media: message_id={message_id}, error={e}", exc_info=True)
        return None


async def delete_message_media(message_id: str) -> bool:
    """
    Supprime un média de message de Supabase Storage
    
    Args:
        message_id: ID du message
    
    Returns:
        True si supprimé avec succès, False sinon
    """
    try:
        # Chercher tous les fichiers avec ce message_id comme préfixe
        def _list():
            return supabase.storage.from_(MESSAGE_MEDIA_BUCKET).list()
        
        files = await run_in_threadpool(_list)
        
        # Trouver le fichier correspondant
        file_to_delete = None
        if files:
            for file in files:
                if file.get("name", "").startswith(message_id):
                    file_to_delete = file.get("name")
                    break
        
        if file_to_delete:
            def _delete():
                return supabase.storage.from_(MESSAGE_MEDIA_BUCKET).remove([file_to_delete])
            
            await run_in_threadpool(_delete)
            logger.info(f"✅ Message media deleted: {file_to_delete}")
            return True
        
        return False
        
    except Exception as e:
        logger.warning(f"⚠️ Error deleting message media: {e}")
        return False


async def cleanup_old_media(days: int = 60) -> int:
    """
    Supprime les médias de plus de X jours de Supabase Storage
    
    Args:
        days: Nombre de jours de rétention (défaut: 60)
    
    Returns:
        Nombre de fichiers supprimés
    """
    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_iso = cutoff_date.isoformat()
        # S'assurer que cutoff_date est timezone-aware pour asyncpg
        if cutoff_date.tzinfo is None:
            cutoff_date = cutoff_date.replace(tzinfo=timezone.utc)
        
        if get_pool():
            messages_to_clean = await fetch_all(
                """
                SELECT id, storage_url FROM messages
                WHERE storage_url IS NOT NULL AND timestamp < $1::timestamptz
                """,
                cutoff_date,
            )
        else:
            query = (
                supabase.table("messages")
                .select("id, storage_url")
                .not_.is_("storage_url", "null")
                .lt("timestamp", cutoff_iso)
            )
            result = await supabase_execute(query)
            messages_to_clean = result.data or []
        
        deleted_count = 0
        for msg in messages_to_clean:
            if await delete_message_media(msg["id"]):
                deleted_count += 1
                if get_pool():
                    await pg_execute(
                        "UPDATE messages SET storage_url = NULL WHERE id = $1::uuid",
                        msg["id"],
                    )
                else:
                    await supabase_execute(
                        supabase.table("messages").update({"storage_url": None}).eq("id", msg["id"])
                    )
        
        logger.info(f"✅ Cleaned up {deleted_count} old media files")
        return deleted_count
        
    except Exception as e:
        logger.error(f"❌ Error cleaning up old media: {e}", exc_info=True)
        return 0


# ============================================================================
# TEMPLATE MEDIA STORAGE
# ============================================================================

async def upload_template_media(
    template_name: str,
    template_language: str,
    account_id: str,
    media_data: bytes,
    media_type: str,  # "IMAGE", "VIDEO", "DOCUMENT"
    content_type: str,
    filename: Optional[str] = None
) -> Optional[str]:
    """
    Upload un média de template dans Supabase Storage et enregistre les métadonnées
    
    Args:
        template_name: Nom du template
        template_language: Langue du template
        account_id: ID du compte WhatsApp
        media_data: Données binaires du média
        media_type: Type de média ("IMAGE", "VIDEO", "DOCUMENT")
        content_type: Type MIME du média
        filename: Nom de fichier original (optionnel)
    
    Returns:
        URL publique du média ou None en cas d'erreur
    """
    try:
        from app.core.db import supabase_execute
        
        # Déterminer l'extension selon le content-type
        extension_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "video/mp4": ".mp4",
            "video/quicktime": ".mov",
            "application/pdf": ".pdf",
        }
        
        extension = extension_map.get(content_type, "")
        if filename:
            if "." in filename:
                extension = "." + filename.rsplit(".", 1)[1]
        
        # Nom du fichier : template_name_language_type + extension
        safe_template_name = template_name.replace(" ", "_").replace("/", "_")
        file_name = f"{safe_template_name}_{template_language}_{media_type.lower()}{extension}"
        file_path = file_name
        
        # Upload dans Supabase Storage
        logger.info(f"📤 Uploading template media to bucket '{TEMPLATE_MEDIA_BUCKET}': path={file_path}, size={len(media_data)} bytes")
        
        def _upload():
            try:
                result = supabase.storage.from_(TEMPLATE_MEDIA_BUCKET).upload(
                    path=file_path,
                    file=media_data,
                    file_options={
                        "content-type": content_type,
                        "upsert": "true"  # Remplacer si existe déjà
                    }
                )
                return result
            except Exception as upload_error:
                logger.error(f"❌ Upload error in thread: {upload_error}", exc_info=True)
                raise
        
        result = await run_in_threadpool(_upload)
        
        if result:
            # Récupérer l'URL publique
            public_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/{TEMPLATE_MEDIA_BUCKET}/{file_path}"
            
            # Enregistrer les métadonnées dans la table template_media
            try:
                if get_pool():
                    await pg_execute(
                        """
                        INSERT INTO template_media (template_name, template_language, account_id, media_type, storage_url, storage_path, mime_type, file_size)
                        VALUES ($1, $2, $3::uuid, $4, $5, $6, $7, $8)
                        ON CONFLICT (template_name, template_language, account_id, media_type)
                        DO UPDATE SET storage_url = EXCLUDED.storage_url, storage_path = EXCLUDED.storage_path, mime_type = EXCLUDED.mime_type, file_size = EXCLUDED.file_size, updated_at = NOW()
                        """,
                        template_name, template_language, account_id, media_type,
                        public_url, file_path, content_type, len(media_data),
                    )
                else:
                    await supabase_execute(
                        supabase.table("template_media")
                        .upsert({
                            "template_name": template_name,
                            "template_language": template_language,
                            "account_id": account_id,
                            "media_type": media_type,
                            "storage_url": public_url,
                            "storage_path": file_path,
                            "mime_type": content_type,
                            "file_size": len(media_data)
                        }, on_conflict="template_name,template_language,account_id,media_type")
                    )
                logger.info(f"✅ Template media uploaded and metadata saved: {public_url}")
            except Exception as db_error:
                logger.warning(f"⚠️ Error saving template media metadata: {db_error}")
            
            return public_url
        else:
            logger.warning(f"⚠️ Upload returned None or empty result")
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Error uploading template media to Supabase Storage: template={template_name}, error={e}", exc_info=True)
        return None


async def get_template_media_url(
    template_name: str,
    template_language: str,
    account_id: str,
    media_type: str = "IMAGE"
) -> Optional[str]:
    """
    Récupère l'URL du média stocké pour un template
    
    Args:
        template_name: Nom du template
        template_language: Langue du template
        account_id: ID du compte WhatsApp
        media_type: Type de média ("IMAGE", "VIDEO", "DOCUMENT")
    
    Returns:
        URL publique du média ou None si non trouvé ou si la table n'existe pas
    """
    try:
        if get_pool():
            row = await fetch_one(
                """
                SELECT storage_url FROM template_media
                WHERE template_name = $1 AND template_language = $2 AND account_id = $3::uuid AND media_type = $4
                LIMIT 1
                """,
                template_name, template_language, account_id, media_type,
            )
            if row:
                return row.get("storage_url")
            return None
        result = await supabase_execute(
            supabase.table("template_media")
            .select("storage_url")
            .eq("template_name", template_name)
            .eq("template_language", template_language)
            .eq("account_id", account_id)
            .eq("media_type", media_type)
            .limit(1)
        )
        if result.data and len(result.data) > 0:
            return result.data[0].get("storage_url")
        return None
        
    except Exception as e:
        # Si la table n'existe pas encore (erreur 42P01), retourner None silencieusement
        error_str = str(e).lower()
        if "does not exist" in error_str or "42p01" in error_str:
            logger.debug(f"Table template_media does not exist yet, skipping media URL lookup")
            return None
        # Pour les autres erreurs, logger mais retourner None pour ne pas faire planter l'endpoint
        logger.warning(f"⚠️ Error getting template media URL: {e}")
        return None


async def download_and_store_template_media(
    template_name: str,
    template_language: str,
    account_id: str,
    media_url: str,
    media_type: str,  # "IMAGE", "VIDEO", "DOCUMENT"
    content_type: str,
    filename: Optional[str] = None
) -> Optional[str]:
    """
    Télécharge un média depuis une URL et le stocke pour un template
    
    Args:
        template_name: Nom du template
        template_language: Langue du template
        account_id: ID du compte WhatsApp
        media_url: URL du média à télécharger
        media_type: Type de média ("IMAGE", "VIDEO", "DOCUMENT")
        content_type: Type MIME du média
        filename: Nom de fichier original (optionnel)
    
    Returns:
        URL publique Supabase du média ou None en cas d'erreur
    """
    try:
        import httpx
        from app.core.http_client import get_http_client_for_media
        
        logger.info(f"📥 Downloading template media: template={template_name}, url_length={len(media_url)}")
        
        # Vérifier d'abord si le média existe déjà
        existing_url = await get_template_media_url(template_name, template_language, account_id, media_type)
        if existing_url:
            logger.info(f"✅ Template media already exists: {existing_url}")
            return existing_url
        
        # Télécharger le média
        client = await get_http_client_for_media()
        response = await client.get(media_url)
        response.raise_for_status()
        
        # Utiliser le content-type fourni ou celui de la réponse
        detected_content_type = response.headers.get("content-type", content_type)
        media_data = response.content
        
        logger.info(f"✅ Template media downloaded: template={template_name}, size={len(media_data)} bytes, content_type={detected_content_type}")
        
        # Upload dans Supabase Storage
        return await upload_template_media(
            template_name=template_name,
            template_language=template_language,
            account_id=account_id,
            media_data=media_data,
            media_type=media_type,
            content_type=detected_content_type,
            filename=filename
        )
        
    except Exception as e:
        logger.error(f"❌ Error downloading and storing template media: template={template_name}, error={e}", exc_info=True)
        return None

