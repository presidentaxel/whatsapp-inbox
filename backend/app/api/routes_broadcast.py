from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from typing import Any, List, Optional

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.broadcast_service import (
    create_broadcast_group,
    get_broadcast_group,
    get_broadcast_groups,
    update_broadcast_group,
    delete_broadcast_group,
    add_recipient_to_group,
    get_group_recipients,
    remove_recipient_from_group,
    import_recipients_for_broadcast_group,
    parse_broadcast_import_csv,
    send_broadcast_campaign,
    get_broadcast_campaign,
    get_broadcast_campaigns,
    get_campaign_stats,
    get_campaign_heatmap,
    get_campaign_timeline,
)

router = APIRouter()


# ==================== GROUPES ====================

@router.post("/groups")
async def create_group(
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Crée un nouveau groupe de diffusion"""
    account_id = payload.get("account_id")
    name = payload.get("name")
    
    if not account_id or not name:
        raise HTTPException(status_code=400, detail="account_id and name are required")
    
    # Vérifier les permissions
    current_user.require(PermissionCodes.MESSAGES_SEND, account_id)
    
    description = payload.get("description")
    created_by = current_user.id
    
    group = await create_broadcast_group(
        account_id=account_id,
        name=name,
        description=description,
        created_by=created_by,
    )
    
    return group


@router.get("/groups")
async def list_groups(
    account_id: str = Query(..., description="WhatsApp account ID"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Liste tous les groupes d'un compte"""
    # Vérifier les permissions
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, account_id)
    
    groups = await get_broadcast_groups(account_id)
    return groups


@router.get("/groups/{group_id}")
async def get_group(
    group_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Récupère un groupe par son ID"""
    group = await get_broadcast_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="group_not_found")
    
    # Vérifier les permissions
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, group["account_id"])
    
    return group


@router.patch("/groups/{group_id}")
async def update_group(
    group_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Met à jour un groupe"""
    group = await get_broadcast_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="group_not_found")
    
    # Vérifier les permissions
    current_user.require(PermissionCodes.MESSAGES_SEND, group["account_id"])
    
    name = payload.get("name")
    description = payload.get("description")
    
    updated = await update_broadcast_group(
        group_id=group_id,
        name=name,
        description=description,
    )
    
    return updated


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Supprime un groupe"""
    group = await get_broadcast_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="group_not_found")
    
    # Vérifier les permissions
    current_user.require(PermissionCodes.MESSAGES_SEND, group["account_id"])
    
    await delete_broadcast_group(group_id)
    return {"status": "ok"}


# ==================== DESTINATAIRES ====================

@router.post("/groups/{group_id}/recipients")
async def add_recipient(
    group_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Ajoute un destinataire à un groupe"""
    group = await get_broadcast_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="group_not_found")
    
    # Vérifier les permissions
    current_user.require(PermissionCodes.MESSAGES_SEND, group["account_id"])
    
    phone_number = payload.get("phone_number")
    if not phone_number:
        raise HTTPException(status_code=400, detail="phone_number is required")
    
    contact_id = payload.get("contact_id")
    display_name = payload.get("display_name")
    
    recipient = await add_recipient_to_group(
        group_id=group_id,
        phone_number=phone_number,
        contact_id=contact_id,
        display_name=display_name,
    )
    
    return recipient


@router.get("/groups/{group_id}/recipients")
async def list_recipients(
    group_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Liste tous les destinataires d'un groupe"""
    group = await get_broadcast_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="group_not_found")
    
    # Vérifier les permissions
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, group["account_id"])
    
    recipients = await get_group_recipients(group_id)
    return recipients


@router.delete("/groups/{group_id}/recipients/{recipient_id}")
async def remove_recipient(
    group_id: str,
    recipient_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Retire un destinataire d'un groupe"""
    group = await get_broadcast_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="group_not_found")
    
    # Vérifier les permissions
    current_user.require(PermissionCodes.MESSAGES_SEND, group["account_id"])
    
    await remove_recipient_from_group(recipient_id)
    return {"status": "ok"}


@router.post("/groups/{group_id}/import")
async def import_recipients_bulk(
    group_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Import JSON : { "rows": [ {"phone":"...", "name":"..."}, ... ], "create_conversations": true }
    Crée/met à jour les contacts, ouvre les conversations inbox sur le compte du groupe, rattache au groupe.
    """
    group = await get_broadcast_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="group_not_found")

    current_user.require(PermissionCodes.MESSAGES_SEND, group["account_id"])

    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=400, detail="rows_required")

    cc_raw = payload.get("create_conversations")
    if cc_raw is None:
        create_conversations = True
    elif isinstance(cc_raw, bool):
        create_conversations = cc_raw
    elif isinstance(cc_raw, str):
        create_conversations = cc_raw.lower() in ("1", "true", "yes", "on")
    else:
        create_conversations = bool(cc_raw)

    normalized_rows: List[Dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        phone = item.get("phone") or item.get("telephone")
        if not phone:
            continue
        normalized_rows.append(
            {
                "phone": str(phone).strip(),
                "name": (item.get("name") or item.get("display_name") or ""),
            }
        )

    if not normalized_rows:
        raise HTTPException(status_code=400, detail="no_valid_rows")

    result = await import_recipients_for_broadcast_group(
        group_id,
        str(group["account_id"]),
        normalized_rows,
        create_conversations=create_conversations,
    )
    return result


@router.post("/groups/{group_id}/import-csv")
async def import_recipients_csv(
    group_id: str,
    file: UploadFile = File(...),
    create_conversations: str = Form("true"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Import fichier CSV (colonnes téléphone + nom / prénom…)."""
    group = await get_broadcast_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="group_not_found")

    current_user.require(PermissionCodes.MESSAGES_SEND, group["account_id"])

    content = await file.read()
    if len(content) > 6 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="file_too_large")

    try:
        parsed = parse_broadcast_import_csv(content)
    except ValueError as e:
        if str(e) == "file_too_large":
            raise HTTPException(status_code=413, detail="file_too_large") from e
        raise HTTPException(status_code=400, detail=str(e)) from e

    if not parsed:
        raise HTTPException(status_code=400, detail="csv_empty_or_no_phone_column")

    cc = str(create_conversations).lower() in ("1", "true", "yes", "on")

    result = await import_recipients_for_broadcast_group(
        group_id,
        str(group["account_id"]),
        parsed,
        create_conversations=cc,
    )
    result["csv_rows_detected"] = len(parsed)
    return result


# ==================== CAMPAGNES ====================

@router.post("/groups/{group_id}/send")
async def send_campaign(
    group_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Envoie un message à tous les destinataires d'un groupe, ou planifie l'envoi (scheduled_for ISO8601 UTC)."""
    group = await get_broadcast_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="group_not_found")
    
    # Vérifier les permissions
    current_user.require(PermissionCodes.MESSAGES_SEND, group["account_id"])
    
    content_text = payload.get("content_text")
    if not content_text:
        raise HTTPException(status_code=400, detail="content_text is required")
    
    message_type = payload.get("message_type", "text")
    media_url = payload.get("media_url")
    sent_by = current_user.id
    scheduled_for = payload.get("scheduled_for")
    
    campaign = await send_broadcast_campaign(
        group_id=group_id,
        account_id=group["account_id"],
        content_text=content_text,
        message_type=message_type,
        media_url=media_url,
        sent_by=sent_by,
        scheduled_for=scheduled_for,
    )
    
    return campaign


@router.get("/campaigns")
async def list_campaigns(
    group_id: Optional[str] = Query(None, description="Filter by group ID"),
    account_id: Optional[str] = Query(None, description="Filter by account ID"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Liste les campagnes (optionnellement filtrées)"""
    if group_id:
        group = await get_broadcast_group(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="group_not_found")
        current_user.require(PermissionCodes.CONVERSATIONS_VIEW, group["account_id"])
        account_id = group["account_id"]
    elif account_id:
        current_user.require(PermissionCodes.CONVERSATIONS_VIEW, account_id)
    else:
        raise HTTPException(status_code=400, detail="group_id or account_id is required")
    
    campaigns = await get_broadcast_campaigns(group_id=group_id, account_id=account_id)
    return campaigns


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Récupère une campagne par son ID"""
    campaign = await get_broadcast_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign_not_found")
    
    # Vérifier les permissions
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, campaign["account_id"])
    
    return campaign


@router.get("/campaigns/{campaign_id}/stats")
async def get_stats(
    campaign_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Récupère les statistiques complètes d'une campagne"""
    campaign = await get_broadcast_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign_not_found")
    
    # Vérifier les permissions
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, campaign["account_id"])
    
    stats = await get_campaign_stats(campaign_id)
    return stats


@router.get("/campaigns/{campaign_id}/heatmap")
async def get_heatmap(
    campaign_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Récupère les données pour la heat map"""
    campaign = await get_broadcast_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign_not_found")
    
    # Vérifier les permissions
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, campaign["account_id"])
    
    heatmap = await get_campaign_heatmap(campaign_id)
    return heatmap


@router.get("/campaigns/{campaign_id}/timeline")
async def get_timeline(
    campaign_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Récupère la timeline pour les courbes temporelles"""
    campaign = await get_broadcast_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign_not_found")
    
    # Vérifier les permissions
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, campaign["account_id"])
    
    timeline = await get_campaign_timeline(campaign_id)
    return timeline

