"""
Actions sur un message individuel: édition, suppression, pin/unpin, réactions,
et utilitaire `check-whatsapp` pour valider qu'un numéro a un compte WhatsApp.
"""
from ._common import (
    APIRouter,
    Depends,
    HTTPException,
    logger,
    CurrentUser,
    PermissionCodes,
    add_reaction,
    check_phone_number_has_whatsapp,
    delete_message_scope,
    get_account_by_id,
    get_conversation_by_id,
    get_current_user,
    get_message_by_id,
    is_within_free_window,
    remove_reaction,
    send_message,
    send_reaction_to_whatsapp,
    supabase,
    supabase_execute,
    update_message_content,
)

router = APIRouter()


@router.patch("/{message_id}")
async def edit_message(
    message_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Édite un message texte (édition locale uniquement)."""
    new_content = (payload.get("content_text") or "").strip()
    if not new_content:
        raise HTTPException(status_code=400, detail="content_text_required")

    message = await get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message_not_found")

    conversation = await get_conversation_by_id(message["conversation_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])

    result = await update_message_content(message_id, new_content, current_user.id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result["message"]


@router.post("/{message_id}/delete")
async def delete_message(
    message_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Suppression locale d'un message.
    `scope=me`  : masque pour l'utilisateur courant.
    `scope=all` : marque comme supprimé pour tous (pas de delete réseau WhatsApp).
    """
    scope = payload.get("scope", "me")
    if scope not in ("me", "all"):
        raise HTTPException(status_code=400, detail="invalid_scope")

    message = await get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message_not_found")

    conversation = await get_conversation_by_id(message["conversation_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])

    result = await delete_message_scope(message_id, scope, current_user.id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result["message"]


@router.delete("/{message_id}")
async def permanently_delete_message(
    message_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Supprime DÉFINITIVEMENT un message de la base.
    Utilisé pour purger les messages échoués avant un renvoi.
    """
    message = await get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message_not_found")

    conversation = await get_conversation_by_id(message["conversation_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])

    await supabase_execute(
        supabase.table("messages").delete().eq("id", message_id)
    )

    return {"status": "deleted", "message_id": message_id}


@router.post("/reactions/add")
async def add_message_reaction(
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Ajoute une réaction à un message (DB + envoi WhatsApp si `wa_message_id`).
    """
    message_id = payload.get("message_id")
    emoji = payload.get("emoji")

    if not message_id or not emoji:
        raise HTTPException(status_code=400, detail="message_id and emoji are required")

    message = await get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message_not_found")

    conversation = await get_conversation_by_id(message["conversation_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])

    account = await get_account_by_id(conversation["account_id"])
    from_number = payload.get("from_number") or account.get("phone_number") or account.get("phone_number_id")

    if not from_number:
        raise HTTPException(status_code=400, detail="from_number is required")

    result = await add_reaction(message_id, emoji, from_number)

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    if message.get("wa_message_id"):
        wa_result = await send_reaction_to_whatsapp(
            conversation["id"],
            message["wa_message_id"],
            emoji,
        )
        if wa_result.get("error"):
            logger.warning("Failed to send reaction to WhatsApp: %s", wa_result)

    return result


@router.post("/reactions/remove")
async def remove_message_reaction(
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Supprime une réaction (DB + envoi WhatsApp avec emoji vide si `wa_message_id`).
    """
    message_id = payload.get("message_id")
    emoji = payload.get("emoji")

    if not message_id or not emoji:
        raise HTTPException(status_code=400, detail="message_id and emoji are required")

    message = await get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message_not_found")

    conversation = await get_conversation_by_id(message["conversation_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])

    account = await get_account_by_id(conversation["account_id"])
    from_number = payload.get("from_number") or account.get("phone_number") or account.get("phone_number_id")

    if not from_number:
        raise HTTPException(status_code=400, detail="from_number is required")

    result = await remove_reaction(message_id, emoji, from_number)

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    if message.get("wa_message_id"):
        # Emoji vide = signal de suppression côté WhatsApp.
        wa_result = await send_reaction_to_whatsapp(
            conversation["id"],
            message["wa_message_id"],
            "",
        )
        if wa_result.get("error"):
            logger.warning("Failed to remove reaction on WhatsApp: %s", wa_result)

    return result


@router.post("/check-whatsapp")
async def check_phone_has_whatsapp(
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Vérifie si un numéro a un compte WhatsApp actif (lookup Meta).
    Si `account_id` n'est pas fourni, prend le premier compte auquel l'utilisateur a accès.
    """
    phone_number = payload.get("phone_number")
    account_id = payload.get("account_id")

    if not phone_number:
        raise HTTPException(status_code=400, detail="phone_number is required")

    if account_id:
        account = await get_account_by_id(account_id)
        if not account:
            raise HTTPException(status_code=404, detail="account_not_found")
        current_user.require(PermissionCodes.MESSAGES_VIEW, account_id)
    else:
        from app.services.account_service import get_all_accounts
        all_accounts = await get_all_accounts()
        if not all_accounts:
            raise HTTPException(status_code=404, detail="no_accounts_found")

        account = None
        for acc in all_accounts:
            try:
                current_user.require(PermissionCodes.MESSAGES_VIEW, acc["id"])
                account = acc
                break
            except Exception:
                continue

        if not account:
            raise HTTPException(status_code=403, detail="no_account_access")

    phone_number_id = account.get("phone_number_id")
    access_token = account.get("access_token")

    if not phone_number_id or not access_token:
        raise HTTPException(status_code=400, detail="whatsapp_not_configured")

    result = await check_phone_number_has_whatsapp(
        phone_number_id=phone_number_id,
        access_token=access_token,
        phone_number=phone_number,
    )

    return result


@router.post("/{message_id}/pin")
async def pin_message(
    message_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Épingle un message dans la conversation et notifie l'autre partie via
    WhatsApp (envoi immédiat si fenêtre gratuite, sinon mise en file d'attente).
    """
    message = await get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message_not_found")

    conversation = await get_conversation_by_id(message["conversation_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])

    result = await supabase_execute(
        supabase.table("messages")
        .update({"is_pinned": True})
        .eq("id", message_id)
    )

    if not result.data:
        raise HTTPException(status_code=500, detail="failed_to_pin_message")

    try:
        from app.services.pinned_notification_service import queue_pin_notification

        is_free, _ = await is_within_free_window(conversation["id"])

        notification_text = (
            "💡 Astuce : Ce message a été marqué comme important. "
            "Vous pouvez aussi épingler des messages en maintenant appuyé sur un message "
            "et en sélectionnant 'Épingler'."
        )

        wa_message_id = message.get("wa_message_id")
        reply_to_message_id = message_id if wa_message_id else None

        if is_free:
            account = await get_account_by_id(conversation["account_id"])
            if account:
                message_payload = {
                    "conversation_id": conversation["id"],
                    "content": notification_text,
                }

                if reply_to_message_id:
                    message_payload["reply_to_message_id"] = reply_to_message_id
                    logger.info(f"📎 [PIN] Envoi immédiat avec référence au message épinglé: message_id={message_id}, wa_message_id={wa_message_id}")
                else:
                    logger.info(f"📎 [PIN] Envoi immédiat sans référence (pas de wa_message_id): message_id={message_id}")

                send_result = await send_message(
                    message_payload,
                    skip_bot_trigger=True,
                    force_send=False,
                    is_system=True,
                )

                if send_result.get("error"):
                    logger.error(f"❌ [PIN] Erreur lors de l'envoi de la notification: {send_result.get('error')}")
                else:
                    logger.info("✅ [PIN] Notification d'épinglage envoyée immédiatement")
            else:
                logger.warning(f"⚠️ [PIN] Compte non trouvé pour account_id={conversation['account_id']}")
        else:
            queue_result = await queue_pin_notification(
                message_id=message_id,
                conversation_id=conversation["id"],
                notification_text=notification_text,
                reply_to_message_id=reply_to_message_id,
            )

            if queue_result.get("status") == "queued":
                logger.info("📌 [PIN] Notification mise en file d'attente (hors fenêtre gratuite)")
            else:
                logger.warning(f"⚠️ [PIN] Échec de la mise en file d'attente: {queue_result.get('error')}")

    except Exception as e:
        # On n'échoue pas le pin si la notification rate.
        logger.error(f"❌ [PIN] Exception lors de l'envoi/queue de la notification d'épinglage : {e}", exc_info=True)

    return {"status": "pinned", "message_id": message_id}


@router.post("/{message_id}/unpin")
async def unpin_message(
    message_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Désépingle un message et notifie l'autre partie (envoi forcé même hors
    fenêtre gratuite - `force_send=True`).
    """
    message = await get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message_not_found")

    conversation = await get_conversation_by_id(message["conversation_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])

    result = await supabase_execute(
        supabase.table("messages")
        .update({"is_pinned": False})
        .eq("id", message_id)
    )

    if not result.data:
        raise HTTPException(status_code=500, detail="failed_to_unpin_message")

    try:
        account = await get_account_by_id(conversation["account_id"])
        if account:
            notification_text = "📌 Ce message a été désépinglé."

            wa_message_id = message.get("wa_message_id")

            message_payload = {
                "conversation_id": conversation["id"],
                "content": notification_text,
            }

            if wa_message_id:
                message_payload["reply_to_message_id"] = message_id
                logger.info(f"📎 [UNPIN] Envoi de la notification avec référence au message désépinglé: message_id={message_id}, wa_message_id={wa_message_id}")

            send_result = await send_message(
                message_payload,
                skip_bot_trigger=True,
                force_send=True,
                is_system=True,
            )

            if send_result.get("error"):
                logger.error(f"❌ [UNPIN] Erreur lors de l'envoi de la notification: {send_result.get('error')} - {send_result.get('details', '')}")
            else:
                logger.info("✅ [UNPIN] Notification de désépinglage envoyée avec succès")
        else:
            logger.warning(f"⚠️ [UNPIN] Compte non trouvé pour account_id={conversation['account_id']}")
    except Exception as e:
        logger.error(f"❌ [UNPIN] Exception lors de l'envoi de la notification de désépinglage : {e}", exc_info=True)

    return {"status": "unpinned", "message_id": message_id}
