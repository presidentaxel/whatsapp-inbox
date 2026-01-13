"""
Service pour gérer le stockage d'images dans Supabase Storage
"""
import logging
from typing import Optional
from io import BytesIO
from datetime import datetime, timedelta, timezone
from starlette.concurrency import run_in_threadpool

from app.core.db import supabase
from app.core.config import settings

logger = logging.getLogger(__name__)

# Nom du bucket pour les images de profil
PROFILE_PICTURES_BUCKET = "profile-pictures"
# Nom du bucket pour les médias de messages (images, vidéos, documents)
MESSAGE_MEDIA_BUCKET = "message-media"
# Nom du bucket pour les images de templates
TEMPLATE_MEDIA_BUCKET = "template-media"


async def upload_profile_picture(
    contact_id: str,
    image_data: bytes,
    content_type: str = "image/jpeg"
) -> Optional[str]:
    """
    Upload une image de profil dans Supabase Storage
    
    Args:
        contact_id: ID du contact (utilisé comme nom de fichier)
        image_data: Données binaires de l'image
        content_type: Type MIME de l'image (défaut: image/jpeg)
    
    Returns:
        URL publique de l'image ou None en cas d'erreur
    """
    try:
        # Nom du fichier : contact_id.jpg
        file_name = f"{contact_id}.jpg"
        file_path = f"{file_name}"
        
        # Upload dans Supabase Storage
        def _upload():
            return supabase.storage.from_(PROFILE_PICTURES_BUCKET).upload(
                path=file_path,
                file=image_data,
                file_options={
                    "content-type": content_type,
                    "upsert": "true"  # Remplacer si existe déjà
                }
            )
        
        result = await run_in_threadpool(_upload)
        
        if result:
            # Récupérer l'URL publique
            # L'URL publique est : {SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}
            public_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/{PROFILE_PICTURES_BUCKET}/{file_path}"
            
            logger.info(f"✅ Profile picture uploaded to Supabase Storage: {public_url}")
            return public_url
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Error uploading profile picture to Supabase Storage: {e}", exc_info=True)
        return None


async def download_and_store_profile_picture(
    contact_id: str,
    image_url: str
) -> Optional[str]:
    """
    Télécharge une image depuis une URL et la stocke dans Supabase Storage
    
    Args:
        contact_id: ID du contact
        image_url: URL de l'image à télécharger
    
    Returns:
        URL publique Supabase de l'image ou None en cas d'erreur
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
            
            # Upload dans Supabase Storage
            return await upload_profile_picture(
                contact_id=contact_id,
                image_data=image_data,
                content_type=content_type
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
        logger.info(f"📤 Uploading to bucket '{MESSAGE_MEDIA_BUCKET}': path={file_path}, size={len(media_data)} bytes")
        
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
                # Messages d'erreur plus explicites
                if "bucket" in error_str.lower() or "not found" in error_str.lower():
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
        logger.error(f"❌ Error uploading message media to Supabase Storage: message_id={message_id}, error={e}", exc_info=True)
        return None


async def download_and_store_message_media(
    message_id: str,
    media_url: str,
    content_type: str,
    filename: Optional[str] = None,
    access_token: Optional[str] = None
) -> Optional[str]:
    """
    Télécharge un média depuis une URL (WhatsApp) et le stocke dans Supabase Storage
    
    Args:
        message_id: ID du message
        media_url: URL du média à télécharger (WhatsApp Graph API)
        content_type: Type MIME du média
        filename: Nom de fichier original (optionnel)
        access_token: Token d'accès WhatsApp (requis pour télécharger depuis WhatsApp)
    
    Returns:
        URL publique Supabase du média ou None en cas d'erreur
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
        
        logger.info(f"✅ Media downloaded: message_id={message_id}, size={len(media_data)} bytes, content_type={detected_content_type}")
        
        # Upload dans Supabase Storage
        logger.info(f"📤 Uploading to Supabase Storage: message_id={message_id}, bucket={MESSAGE_MEDIA_BUCKET}")
        result = await upload_message_media(
            message_id=message_id,
            media_data=media_data,
            content_type=detected_content_type,
            filename=filename
        )
        
        if result:
            logger.info(f"✅ Media uploaded successfully: message_id={message_id}, storage_url={result}")
        else:
            logger.warning(f"❌ Media upload failed: message_id={message_id}")
        
        return result
        
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
        from app.core.db import supabase_execute
        
        # Calculer la date limite
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_iso = cutoff_date.isoformat()
        
        # Trouver tous les messages avec storage_url et timestamp < cutoff
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
                # Mettre à jour le message pour retirer storage_url
                await supabase_execute(
                    supabase.table("messages")
                    .update({"storage_url": None})
                    .eq("id", msg["id"])
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
        from app.core.db import supabase_execute
        
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

