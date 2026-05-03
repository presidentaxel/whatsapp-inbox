"""
Media: galerie conversation/compte, vérification & téléchargement, test storage,
transcription audio à la demande.
"""
from ._common import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    datetime,
    timezone,
    logger,
    CurrentUser,
    PermissionCodes,
    SUPABASE_IN_CLAUSE_CHUNK_SIZE,
    fetch_all,
    get_account_by_id,
    get_cache,
    get_conversation_by_id,
    get_current_user,
    get_message_by_id,
    get_pool,
    process_unsaved_media_for_conversation,
    supabase,
    supabase_execute,
    transcribe_inbound_audio_on_demand_for_message,
)

router = APIRouter()


@router.post("/test-storage/{message_id}")
async def test_storage_for_message(
    message_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Force le téléchargement et le stockage d'un média existant.
    Utile pour stocker rétroactivement des médias non backfillés.
    """
    message = await get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message_not_found")

    conversation = await get_conversation_by_id(message["conversation_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])

    account = await get_account_by_id(conversation["account_id"])
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")

    media_id = message.get("media_id")
    if not media_id:
        raise HTTPException(status_code=400, detail="message_has_no_media_id")

    message_type = message.get("message_type", "").lower()
    if message_type not in ("image", "video", "audio", "voice", "document", "sticker"):
        raise HTTPException(status_code=400, detail="message_is_not_a_media_type")

    from app.services.message_service import _download_and_store_media_async

    await _download_and_store_media_async(
        message_db_id=message_id,
        media_id=media_id,
        account=account,
        mime_type=message.get("media_mime_type"),
        filename=message.get("media_filename"),
    )

    return {"status": "processing", "message": "Media download and storage started in background"}


CHECK_MEDIA_CACHE_TTL = 300  # 5 min : évite de relancer le scan dès que la conv est ré-ouverte.


@router.post("/check-media/{conversation_id}")
async def check_and_download_conversation_media(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Vérifie et télécharge les médias manquants d'une conversation, en arrière-plan.
    Cache 5 min pour éviter les relances inutiles à chaque ouverture (~75% req. en moins).
    """
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])

    cache = await get_cache()
    cache_key = f"check_media:{conversation_id}"
    if await cache.get(cache_key):
        return {
            "status": "skipped",
            "message": "Media check already in progress or recently completed (5 min cooldown)",
        }

    await cache.set(cache_key, {"started_at": datetime.now(timezone.utc).isoformat()}, CHECK_MEDIA_CACHE_TTL)

    import asyncio
    asyncio.create_task(process_unsaved_media_for_conversation(conversation_id, limit=50))

    return {
        "status": "started",
        "message": "Media check and download started in background for this conversation",
    }


@router.get("/media-gallery/{conversation_id}")
async def get_conversation_media_gallery(
    conversation_id: str,
    media_type: str = Query("image", description="Type de média: image, video, document, audio"),
    limit: int = Query(100, ge=1, le=500, description="Nombre maximum de médias à retourner"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Récupère tous les médias d'une conversation avec leur URL de stockage.
    Utilisé pour la galerie média du panneau de contact.
    """
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])

    media_types = {
        "image": ["image", "sticker"],
        "video": ["video"],
        "document": ["document"],
        "audio": ["audio", "voice"],
        "all": ["image", "video", "document", "audio", "sticker", "voice"],
    }

    types_to_fetch = media_types.get(media_type.lower(), media_types["image"])

    if get_pool():
        rows = await fetch_all(
            """
            SELECT id, message_type, storage_url, timestamp, content_text, direction
            FROM messages
            WHERE conversation_id = $1::uuid
              AND message_type = ANY($2::text[])
              AND storage_url IS NOT NULL
              AND storage_url NOT ILIKE '%template-media%'
            ORDER BY timestamp DESC
            LIMIT $3
            """,
            conversation_id,
            types_to_fetch,
            limit,
        )
        messages = rows
    else:
        query = (
            supabase.table("messages")
            .select("id, message_type, storage_url, timestamp, content_text, direction")
            .eq("conversation_id", conversation_id)
            .in_("message_type", types_to_fetch)
            .not_.is_("storage_url", "null")
            .not_.ilike("storage_url", "%template-media%")
            .order("timestamp", desc=True)
            .limit(limit)
        )
        result = await supabase_execute(query)
        messages = result.data or []

    gallery_items = []
    for msg in messages:
        storage_url = msg.get("storage_url", "")
        message_type_val = msg.get("message_type", "").lower()
        # Double sécurité : exclure tous les médias du bucket template-media
        # et les messages de type `template`.
        if "template-media" in storage_url or message_type_val == "template":
            continue
        gallery_items.append({
            "id": msg.get("id"),
            "message_id": msg.get("id"),
            "type": msg.get("message_type"),
            "url": storage_url,
            "thumbnail_url": storage_url,
            "timestamp": msg.get("timestamp"),
            "caption": msg.get("content_text"),
            "direction": msg.get("direction"),
        })

    return {
        "conversation_id": conversation_id,
        "media_type": media_type,
        "count": len(gallery_items),
        "items": gallery_items,
    }


@router.get("/media-gallery-account/{account_id}")
async def get_account_media_gallery(
    account_id: str,
    media_type: str = Query("image", description="Type de média: image, video, document, audio"),
    limit: int = Query(500, ge=1, le=1000, description="Nombre maximum de médias à retourner"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Récupère tous les médias de toutes les conversations d'un compte.
    Utilisé pour la galerie globale d'un account.
    """
    current_user.require(PermissionCodes.MESSAGES_VIEW, account_id)

    media_types = {
        "image": ["image", "sticker"],
        "video": ["video"],
        "document": ["document"],
        "audio": ["audio", "voice"],
        "all": ["image", "video", "document", "audio", "sticker", "voice"],
    }

    types_to_fetch = media_types.get(media_type.lower(), media_types["image"])

    if get_pool():
        # PG direct : une seule requête (jointure sur les conversations du compte).
        rows = await fetch_all(
            """
            SELECT m.id, m.message_type, m.storage_url, m.timestamp, m.content_text, m.direction, m.conversation_id
            FROM messages m
            WHERE m.conversation_id IN (SELECT id FROM conversations WHERE account_id = $1::uuid)
              AND m.message_type = ANY($2::text[])
              AND m.storage_url IS NOT NULL
              AND m.storage_url NOT ILIKE '%template-media%'
            ORDER BY m.timestamp DESC
            LIMIT $3
            """,
            account_id,
            types_to_fetch,
            limit,
        )
        messages = rows
    else:
        # Fallback Supabase REST : on chunke les `IN (...)` (limite REST).
        conversations_result = await supabase_execute(
            supabase.table("conversations")
            .select("id")
            .eq("account_id", account_id)
        )
        conversation_ids = [conv["id"] for conv in (conversations_result.data or [])]
        if not conversation_ids:
            return {
                "account_id": account_id,
                "media_type": media_type,
                "count": 0,
                "items": [],
            }
        messages = []
        for i in range(0, len(conversation_ids), SUPABASE_IN_CLAUSE_CHUNK_SIZE):
            chunk = conversation_ids[i: i + SUPABASE_IN_CLAUSE_CHUNK_SIZE]
            query = (
                supabase.table("messages")
                .select("id, message_type, storage_url, timestamp, content_text, direction, conversation_id")
                .in_("conversation_id", chunk)
                .in_("message_type", types_to_fetch)
                .not_.is_("storage_url", "null")
                .not_.ilike("storage_url", "%template-media%")
                .order("timestamp", desc=True)
                .limit(limit)
            )
            result = await supabase_execute(query)
            chunk_data = result.data or []
            messages.extend(chunk_data)
        messages.sort(key=lambda m: m.get("timestamp") or "", reverse=True)
        messages = messages[:limit]

    gallery_items = []
    for msg in messages:
        storage_url = msg.get("storage_url", "")
        message_type_val = msg.get("message_type", "").lower()

        if "template-media" in storage_url or message_type_val == "template":
            continue

        gallery_items.append({
            "id": msg.get("id"),
            "message_id": msg.get("id"),
            "type": msg.get("message_type"),
            "url": storage_url,
            "thumbnail_url": storage_url,
            "timestamp": msg.get("timestamp"),
            "caption": msg.get("content_text"),
            "direction": msg.get("direction"),
            "conversation_id": msg.get("conversation_id"),
        })

    return {
        "account_id": account_id,
        "media_type": media_type,
        "count": len(gallery_items),
        "items": gallery_items,
    }


@router.post("/{message_id}/transcribe-audio")
async def transcribe_message_audio(
    message_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Transcription manuelle d'un message audio/voice entrant (Gemini).
    Idempotent : si `audio_transcript` est déjà renseigné, renvoie la valeur sans rappeler l'API.
    """
    message = await get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message_not_found")

    conversation = await get_conversation_by_id(message["conversation_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])

    result = await transcribe_inbound_audio_on_demand_for_message(message)
    if not result.get("ok"):
        raise HTTPException(
            status_code=int(result.get("status") or 500),
            detail=str(result.get("detail") or "transcription_failed"),
        )
    return {
        "transcript": result.get("transcript") or "",
        "cached": bool(result.get("cached")),
    }
