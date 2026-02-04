import uuid as uuid_module
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.core.db import supabase, supabase_execute
from app.services.contact_service import list_contacts
from app.services.account_service import get_account_by_id
from app.services.profile_picture_service import update_all_contacts_profile_pictures

router = APIRouter()


class ContactCreate(BaseModel):
    whatsapp_number: str
    display_name: str | None = None


class ContactUpdate(BaseModel):
    display_name: str | None = None
    whatsapp_number: str | None = None


@router.get("")
async def fetch_contacts(current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.CONTACTS_VIEW)
    return await list_contacts()


@router.post("")
async def create_contact(
    contact: ContactCreate,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Crée un nouveau contact"""
    current_user.require(PermissionCodes.CONTACTS_VIEW)
    
    # Nettoyer le numéro de téléphone
    clean_number = contact.whatsapp_number.replace("+", "").replace(" ", "").replace("-", "")
    
    # Vérifier si le contact existe déjà
    existing = await supabase_execute(
        supabase.table("contacts")
        .select("id")
        .eq("whatsapp_number", clean_number)
        .limit(1)
    )
    
    if existing.data:
        raise HTTPException(status_code=400, detail="contact_already_exists")
    
    # Créer le contact
    result = await supabase_execute(
        supabase.table("contacts")
        .insert({
            "whatsapp_number": clean_number,
            "display_name": contact.display_name
        })
        .select()
    )
    
    if not result.data:
        raise HTTPException(status_code=500, detail="contact_creation_failed")
    
    return result.data[0]


@router.put("/{contact_id}")
async def update_contact(
    contact_id: str,
    contact: ContactUpdate,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Met à jour un contact"""
    _validate_contact_id(contact_id)
    current_user.require(PermissionCodes.CONTACTS_VIEW)
    
    # Vérifier que le contact existe
    existing = await supabase_execute(
        supabase.table("contacts")
        .select("id")
        .eq("id", contact_id)
        .limit(1)
    )
    
    if not existing.data:
        raise HTTPException(status_code=404, detail="contact_not_found")
    
    # Préparer les données à mettre à jour
    update_data = {}
    if contact.display_name is not None:
        update_data["display_name"] = contact.display_name
    if contact.whatsapp_number is not None:
        clean_number = contact.whatsapp_number.replace("+", "").replace(" ", "").replace("-", "")
        # Vérifier si le nouveau numéro existe déjà
        if clean_number != existing.data[0].get("whatsapp_number"):
            duplicate = await supabase_execute(
                supabase.table("contacts")
                .select("id")
                .eq("whatsapp_number", clean_number)
                .limit(1)
            )
            if duplicate.data:
                raise HTTPException(status_code=400, detail="whatsapp_number_already_exists")
        update_data["whatsapp_number"] = clean_number
    
    if not update_data:
        raise HTTPException(status_code=400, detail="no_fields_to_update")
    
    # Mettre à jour
    result = await supabase_execute(
        supabase.table("contacts")
        .update(update_data)
        .eq("id", contact_id)
        .select()
    )
    
    if not result.data:
        raise HTTPException(status_code=500, detail="contact_update_failed")
    
    return result.data[0]


@router.delete("/{contact_id}")
async def delete_contact(
    contact_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Supprime un contact"""
    _validate_contact_id(contact_id)
    current_user.require(PermissionCodes.CONTACTS_VIEW)
    
    # Vérifier que le contact existe
    existing = await supabase_execute(
        supabase.table("contacts")
        .select("id")
        .eq("id", contact_id)
        .limit(1)
    )
    
    if not existing.data:
        raise HTTPException(status_code=404, detail="contact_not_found")
    
    # Supprimer le contact
    await supabase_execute(
        supabase.table("contacts")
        .delete()
        .eq("id", contact_id)
    )
    
    return {"success": True, "message": "contact_deleted"}


@router.post("/{contact_id}/profile-picture")
async def update_contact_profile_picture(
    contact_id: str,
    account_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Met à jour l'image de profil d'un contact en récupérant l'image depuis WhatsApp
    Utilise le système de queue pour traiter en arrière-plan
    
    Args:
        contact_id: ID du contact
        account_id: ID du compte WhatsApp à utiliser pour récupérer l'image
    """
    _validate_contact_id(contact_id)
    current_user.require(PermissionCodes.MESSAGES_VIEW, account_id)
    
    # Récupérer le contact
    contact_res = await supabase_execute(
        supabase.table("contacts").select("*").eq("id", contact_id).limit(1)
    )
    
    if not contact_res.data:
        raise HTTPException(status_code=404, detail="contact_not_found")
    
    contact = contact_res.data[0]
    whatsapp_number = contact.get("whatsapp_number")
    
    if not whatsapp_number:
        raise HTTPException(status_code=400, detail="contact_has_no_whatsapp_number")
    
    # Utiliser le service de queue pour mettre à jour en arrière-plan
    from app.services.profile_picture_service import queue_profile_picture_update
    
    await queue_profile_picture_update(
        contact_id=contact_id,
        whatsapp_number=whatsapp_number,
        account_id=account_id,
        priority=True
    )
    
    return {
        "success": True,
        "message": "Profile picture update queued",
        "status": "processing"
    }


@router.post("/update-all-profile-pictures")
async def update_all_profile_pictures(
    account_id: str,
    limit: int = 50,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Met à jour les images de profil de tous les contacts sans image
    Traite de manière asynchrone pour ne pas bloquer l'API
    
    Args:
        account_id: ID du compte WhatsApp à utiliser
        limit: Nombre maximum de contacts à traiter (défaut: 50)
    """
    current_user.require(PermissionCodes.MESSAGES_VIEW, account_id)
    
    # Vérifier que le compte existe
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    # Lancer la mise à jour en arrière-plan
    import asyncio
    asyncio.create_task(update_all_contacts_profile_pictures(account_id, limit))
    
    return {
        "success": True,
        "message": f"Profile picture update queued for up to {limit} contacts",
        "status": "processing"
    }


def _validate_contact_id(contact_id: str) -> None:
    """Lève HTTPException 400 si contact_id n'est pas un UUID valide."""
    if not contact_id or contact_id.strip() in ("undefined", "null", ""):
        raise HTTPException(status_code=400, detail="contact_id is required and must be a valid UUID")
    try:
        uuid_module.UUID(contact_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="contact_id must be a valid UUID")


@router.get("/{contact_id}/whatsapp-info")
async def get_contact_whatsapp_info(
    contact_id: str,
    account_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Récupère les informations complètes d'un contact depuis WhatsApp API
    Inclut: nom, photo de profil, et autres métadonnées disponibles
    
    Args:
        contact_id: ID du contact
        account_id: ID du compte WhatsApp à utiliser
    """
    _validate_contact_id(contact_id)
    current_user.require(PermissionCodes.MESSAGES_VIEW, account_id)
    
    # Récupérer le contact
    contact_res = await supabase_execute(
        supabase.table("contacts").select("*").eq("id", contact_id).limit(1)
    )
    
    if not contact_res.data:
        raise HTTPException(status_code=404, detail="contact_not_found")
    
    contact = contact_res.data[0]
    whatsapp_number = contact.get("whatsapp_number")
    
    if not whatsapp_number:
        raise HTTPException(status_code=400, detail="contact_has_no_whatsapp_number")
    
    # Récupérer le compte WhatsApp
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    
    # Récupérer les informations depuis WhatsApp API
    from app.services.whatsapp_api_service import get_contact_info
    from datetime import datetime, timezone
    
    try:
        contact_info = await get_contact_info(
            phone_number_id=account.get("phone_number_id"),
            access_token=account.get("access_token"),
            phone_number=whatsapp_number
        )
        
        # OPTIMISATION: Si l'appel WhatsApp échoue mais qu'on a des données existantes, les utiliser
        # Ne pas lever d'erreur 5xx si les données sont déjà en cache/local
        has_existing_data = contact.get("whatsapp_name") or contact.get("profile_picture_url")
        
        # Enregistrer les informations dans la base de données (seulement si on a de nouvelles données)
        update_data = {
            "whatsapp_info_fetched_at": datetime.now(timezone.utc).isoformat()
        }
        
        if contact_info.get("name"):
            update_data["whatsapp_name"] = contact_info["name"]
        elif has_existing_data and contact.get("whatsapp_name"):
            # Utiliser les données existantes si l'API n'a pas retourné de nom
            contact_info["name"] = contact.get("whatsapp_name")
        
        if contact_info.get("profile_picture_url"):
            update_data["profile_picture_url"] = contact_info["profile_picture_url"]
        elif has_existing_data and contact.get("profile_picture_url"):
            # Utiliser les données existantes si l'API n'a pas retourné d'image
            contact_info["profile_picture_url"] = contact.get("profile_picture_url")
        
        if update_data:
            await supabase_execute(
                supabase.table("contacts")
                .update(update_data)
                .eq("id", contact_id)
            )
        
        return {
            "success": True,
            "data": contact_info
        }
    except Exception as e:
        # OPTIMISATION: Améliorer la gestion d'erreur pour éviter les 5xx systématiques
        error_msg = str(e)
        logger.error(f"❌ Error fetching WhatsApp info for contact {contact_id}: {error_msg}", exc_info=True)
        
        # Si on a des données existantes, les retourner avec un avertissement plutôt qu'une erreur
        has_existing_data = contact.get("whatsapp_name") or contact.get("profile_picture_url")
        if has_existing_data:
            logger.warning(f"⚠️ WhatsApp API failed for contact {contact_id}, using cached data")
            return {
                "success": True,
                "data": {
                    "name": contact.get("whatsapp_name"),
                    "profile_picture_url": contact.get("profile_picture_url"),
                    "phone_number": whatsapp_number
                },
                "warning": "WhatsApp API unavailable, using cached data"
            }
        
        # Si pas de données existantes et erreur WhatsApp API, retourner 503 Service Unavailable
        # plutôt que 500 Internal Server Error pour indiquer un problème temporaire
        if "whatsapp" in error_msg.lower() or "api" in error_msg.lower() or "graph" in error_msg.lower():
            raise HTTPException(
                status_code=503,
                detail=f"WhatsApp API temporarily unavailable: {error_msg}"
            )
        
        # Pour les autres erreurs, retourner 500
        raise HTTPException(status_code=500, detail=f"Error fetching WhatsApp info: {error_msg}")

