"""
Envois: texte standard, fenêtre gratuite, auto-template, media, interactive.
"""
from ._common import (
    APIRouter,
    Depends,
    HTTPException,
    datetime,
    timezone,
    json,
    logger,
    CurrentUser,
    PermissionCodes,
    find_or_create_template,
    get_conversation_by_id,
    get_current_user,
    is_within_free_window,
    send_free_message,
    send_interactive_message_with_storage,
    send_media_message_with_storage,
    send_message,
    supabase,
    supabase_execute,
)

router = APIRouter()


@router.post("/send")
async def send_api_message(payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    """
    Envoie un message WhatsApp.
    - Si dans la fenêtre gratuite de 24h : envoie un message conversationnel gratuit
    - Si hors fenêtre : utilise automatiquement un template UTILITY (payant mais fonctionne sans erreur)
    """
    logger.debug(
        "POST /messages/send conversation_id=%s content_len=%s",
        payload.get("conversation_id"),
        len(payload.get("content") or ""),
    )
    conversation_id = payload.get("conversation_id")
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id_required")
    conversation = await get_conversation_by_id(conversation_id)
    logger.debug(
        "POST /messages/send conversation found=%s bot_enabled=%s",
        conversation is not None,
        conversation.get("bot_enabled") if conversation else None,
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    access_level = current_user.permissions.account_access_levels.get(conversation["account_id"])
    if access_level == "aucun":
        raise HTTPException(status_code=403, detail="account_access_denied")
    if access_level == "lecture":
        raise HTTPException(status_code=403, detail="write_access_denied")

    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])

    payload.setdefault("sent_by_user_id", str(current_user.id))
    payload.setdefault("sent_via", "ui")
    result = await send_message(payload, force_send=True)

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result.get("message", result.get("error")))

    return result


@router.post("/send-with-auto-template")
async def send_with_auto_template(
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Envoie un message. Si hors fenêtre gratuite, crée automatiquement un template.
    L'utilisateur ne voit pas la différence - le message s'affiche comme envoyé.
    Le template sera validé par Meta en arrière-plan et envoyé automatiquement une fois approuvé.
    """
    conversation_id = payload.get("conversation_id")
    content = payload.get("content", "").strip()

    logger.info("=" * 80)
    logger.info(f"🚀 [SEND-AUTO-TEMPLATE] Début - conversation_id={conversation_id}, content_length={len(content)}")
    logger.info(f"🚀 [SEND-AUTO-TEMPLATE] Payload: {payload}")

    if not conversation_id:
        logger.error("❌ [SEND-AUTO-TEMPLATE] conversation_id manquant")
        raise HTTPException(status_code=400, detail="conversation_id_required")

    if not content:
        logger.error("❌ [SEND-AUTO-TEMPLATE] content manquant")
        raise HTTPException(status_code=400, detail="content_required")

    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        logger.error(f"❌ [SEND-AUTO-TEMPLATE] Conversation {conversation_id} non trouvée")
        raise HTTPException(status_code=404, detail="conversation_not_found")

    logger.info(f"✅ [SEND-AUTO-TEMPLATE] Conversation trouvée: account_id={conversation.get('account_id')}")

    access_level = current_user.permissions.account_access_levels.get(conversation["account_id"])
    if access_level == "aucun":
        logger.error(f"❌ [SEND-AUTO-TEMPLATE] Accès refusé (aucun)")
        raise HTTPException(status_code=403, detail="account_access_denied")
    if access_level == "lecture":
        logger.error(f"❌ [SEND-AUTO-TEMPLATE] Accès refusé (lecture seule)")
        raise HTTPException(status_code=403, detail="write_access_denied")

    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])

    logger.info(f"🔍 [SEND-AUTO-TEMPLATE] Vérification de la fenêtre gratuite...")
    is_free, last_interaction_time = await is_within_free_window(conversation_id)
    logger.info(
        f"📊 [SEND-AUTO-TEMPLATE] Fenêtre gratuite: is_free={is_free}, "
        f"dernier_message_client={last_interaction_time} (seuls les messages entrants comptent)"
    )

    if is_free:
        logger.info("✅ [SEND-AUTO-TEMPLATE] Dans la fenêtre gratuite - envoi normal")
        payload.setdefault("sent_by_user_id", str(current_user.id))
        payload.setdefault("sent_via", "ui")
        result = await send_message(payload, force_send=True)
        if result.get("error"):
            logger.error(f"❌ [SEND-AUTO-TEMPLATE] Erreur lors de l'envoi: {result.get('error')}")
            raise HTTPException(status_code=400, detail=result.get("message", result.get("error")))
        logger.info(f"✅ [SEND-AUTO-TEMPLATE] Message envoyé avec succès: message_id={result.get('message_id')}")
        return {
            "success": True,
            "message_id": result.get("message_id"),
            "status": "sent",
            "message": "Message envoyé avec succès",
        }

    logger.info("⏳ [SEND-AUTO-TEMPLATE] Hors fenêtre gratuite - création d'un template automatique")
    logger.info("📝 [SEND-AUTO-TEMPLATE] Création du message en base...")

    message_payload = {
        "conversation_id": conversation_id,
        "direction": "outbound",
        "content_text": content,
        "status": "pending",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_type": "text",
        "sent_by_user_id": str(current_user.id),
        "sent_via": "ui",
    }

    message_result = await supabase_execute(
        supabase.table("messages").insert(message_payload)
    )

    if not message_result.data or len(message_result.data) == 0:
        logger.error("❌ [SEND-AUTO-TEMPLATE] Échec de la création du message en base")
        logger.error(f"   Résultat: {message_result}")
        raise HTTPException(status_code=500, detail="failed_to_create_message")

    message_id = message_result.data[0]["id"]
    logger.info(f"✅ [SEND-AUTO-TEMPLATE] Message créé en base: message_id={message_id}")

    logger.info(f"🔧 [SEND-AUTO-TEMPLATE] Recherche/création du template pour account_id={conversation['account_id']}")
    template_result = await find_or_create_template(
        conversation_id=conversation_id,
        account_id=conversation["account_id"],
        message_id=message_id,
        text_content=content,
        created_by_user_id=str(current_user.id),
    )

    logger.info(f"📋 [SEND-AUTO-TEMPLATE] Résultat de la création du template: success={template_result.get('success')}")

    if not template_result.get("success"):
        error_message = "; ".join(template_result.get("errors", ["Erreur inconnue"]))
        logger.error(f"❌ [SEND-AUTO-TEMPLATE] Erreur de validation: {error_message}")
        await supabase_execute(
            supabase.table("messages")
            .update({"status": "failed", "error_message": error_message})
            .eq("id", message_id)
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Erreur de validation du message",
                "errors": template_result.get("errors", []),
            },
        )

    logger.info(f"✅ [SEND-AUTO-TEMPLATE] Template créé avec succès, retour du message optimiste")
    logger.info("=" * 80)
    return {
        "success": True,
        "message_id": message_id,
        "status": "pending",
        "message": "Message en cours de validation par Meta. Il sera envoyé automatiquement une fois approuvé.",
    }


@router.post("/send-free")
async def send_free_api_message(payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    """
    Envoie un message WhatsApp uniquement si on est dans la fenêtre gratuite de 24h.
    Si hors fenêtre, retourne 400 avec `requires_template=True`.
    """
    conversation_id = payload.get("conversation_id")
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id_required")

    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    access_level = current_user.permissions.account_access_levels.get(conversation["account_id"])
    if access_level == "aucun":
        raise HTTPException(status_code=403, detail="account_access_denied")
    if access_level == "lecture":
        raise HTTPException(status_code=403, detail="write_access_denied")

    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])

    payload.setdefault("sent_by_user_id", str(current_user.id))
    payload.setdefault("sent_via", "ui")
    result = await send_free_message(payload)

    if result.get("error") == "free_window_expired":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "free_window_expired",
                "message": result.get("message"),
                "last_inbound_time": result.get("last_inbound_time"),
                "requires_template": True,
            },
        )

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result.get("message", result.get("error")))

    return result


@router.post("/send-media")
async def send_media_api_message(payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    """
    Envoie un message média (image, audio, vidéo, document).
    """
    conversation_id = payload.get("conversation_id")
    media_type = payload.get("media_type")
    media_id = payload.get("media_id")
    caption = payload.get("caption")

    if not conversation_id or not media_type or not media_id:
        raise HTTPException(status_code=400, detail="conversation_id, media_type, and media_id are required")

    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    access_level = current_user.permissions.account_access_levels.get(conversation["account_id"])
    if access_level == "aucun":
        raise HTTPException(status_code=403, detail="account_access_denied")
    if access_level == "lecture":
        raise HTTPException(status_code=403, detail="write_access_denied")

    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])

    return await send_media_message_with_storage(
        conversation_id=conversation_id,
        media_type=media_type,
        media_id=media_id,
        caption=caption,
        sent_by_user_id=str(current_user.id),
        sent_via="ui",
    )


@router.post("/send-interactive")
async def send_interactive_api_message(payload: dict, current_user: CurrentUser = Depends(get_current_user)):
    """
    Envoie un message interactif (boutons ou liste).
    Si hors fenêtre gratuite, crée automatiquement un template avec le texte (sans les boutons).
    """
    conversation_id = payload.get("conversation_id")
    interactive_type = payload.get("interactive_type")
    body_text = payload.get("body_text")
    header_text = payload.get("header_text")
    footer_text = payload.get("footer_text")

    if not conversation_id or not interactive_type or not body_text:
        raise HTTPException(status_code=400, detail="conversation_id, interactive_type, and body_text are required")

    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    access_level = current_user.permissions.account_access_levels.get(conversation["account_id"])
    if access_level == "aucun":
        raise HTTPException(status_code=403, detail="account_access_denied")
    if access_level == "lecture":
        raise HTTPException(status_code=403, detail="write_access_denied")

    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])

    logger.info(f"🔍 [SEND-INTERACTIVE] Vérification de la fenêtre gratuite pour conversation {conversation_id}")
    is_free, last_interaction_time = await is_within_free_window(conversation_id)
    logger.info(f"📊 [SEND-INTERACTIVE] Fenêtre gratuite: is_free={is_free}, last_interaction={last_interaction_time}")

    if not is_free:
        # Hors fenêtre : créer un template avec le texte. Les boutons sont
        # archivés dans interactive_data pour rendu UI mais pas envoyés via
        # template (Meta ne permet pas d'ajouter des boutons à la volée).
        logger.info("=" * 80)
        logger.info("⏳ [SEND-INTERACTIVE] ========== HORS FENÊTRE GRATUITE ==========")
        logger.info(f"⏳ [SEND-INTERACTIVE] conversation_id={conversation_id}")
        logger.info(f"⏳ [SEND-INTERACTIVE] interactive_type={interactive_type}")
        logger.info(f"⏳ [SEND-INTERACTIVE] Payload reçu complet:")
        logger.info(f"   {json.dumps(payload, indent=2, ensure_ascii=False)}")
        logger.info(f"⏳ [SEND-INTERACTIVE] Paramètres extraits:")
        logger.info(f"   - body_text: {repr(body_text)}")
        logger.info(f"   - header_text (raw): {repr(header_text)}")
        logger.info(f"   - footer_text (raw): {repr(footer_text)}")
        logger.info(f"   - buttons (raw): {repr(payload.get('buttons'))}")
        logger.info("⏳ [SEND-INTERACTIVE] Hors fenêtre gratuite - création d'un template automatique")

        full_text = ""
        if header_text:
            full_text += f"{header_text}\n\n"
        full_text += body_text
        if footer_text:
            full_text += f"\n\n{footer_text}"

        buttons_data = None
        if interactive_type == "button":
            buttons_data = payload.get("buttons", [])
            if buttons_data:
                buttons_data = [btn for btn in buttons_data if btn.get("title") and btn.get("id")]
                if len(buttons_data) == 0:
                    buttons_data = None

        normalized_header_text = header_text.strip() if header_text and header_text.strip() else None
        normalized_footer_text = footer_text.strip() if footer_text and footer_text.strip() else None

        logger.info(f"🔍 [SEND-INTERACTIVE] Paramètres pour le template:")
        logger.info(f"   - header_text: {normalized_header_text}")
        logger.info(f"   - body_text: {body_text}")
        logger.info(f"   - footer_text: {normalized_footer_text}")
        logger.info(f"   - buttons: {buttons_data}")
        logger.info(f"   - buttons_count: {len(buttons_data) if buttons_data else 0}")

        logger.info("📝 [SEND-INTERACTIVE] Création du message en base...")

        interactive_data_dict = {
            "type": interactive_type,
            "header": normalized_header_text,
            "body": body_text,
            "footer": normalized_footer_text,
        }

        if interactive_type == "button" and buttons_data:
            interactive_data_dict["action"] = {
                "buttons": [
                    {"type": "reply", "reply": {"id": btn["id"], "title": btn["title"]}}
                    for btn in buttons_data
                ]
            }
            interactive_data_dict["buttons"] = [
                {"type": "QUICK_REPLY", "text": btn["title"]}
                for btn in buttons_data
            ]

        message_payload = {
            "conversation_id": conversation_id,
            "direction": "outbound",
            "content_text": full_text,
            "status": "pending",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message_type": "interactive",
            "interactive_data": json.dumps(interactive_data_dict),
            "sent_by_user_id": str(current_user.id),
            "sent_via": "ui",
        }

        message_result = await supabase_execute(
            supabase.table("messages").insert(message_payload)
        )

        if not message_result.data or len(message_result.data) == 0:
            logger.error("❌ [SEND-INTERACTIVE] Échec de la création du message en base")
            raise HTTPException(status_code=500, detail="failed_to_create_message")

        message_id = message_result.data[0]["id"]
        logger.info(f"✅ [SEND-INTERACTIVE] Message créé en base: message_id={message_id}")

        logger.info(f"🔧 [SEND-INTERACTIVE] Recherche/création du template pour account_id={conversation['account_id']}")
        logger.info(f"🔧 [SEND-INTERACTIVE] Appel à find_or_create_template avec:")
        logger.info(f"   - header_text={normalized_header_text}")
        logger.info(f"   - body_text={body_text}")
        logger.info(f"   - footer_text={normalized_footer_text}")
        logger.info(f"   - buttons={buttons_data}")

        template_result = await find_or_create_template(
            conversation_id=conversation_id,
            account_id=conversation["account_id"],
            message_id=message_id,
            text_content=full_text,
            header_text=normalized_header_text,
            body_text=body_text,
            footer_text=normalized_footer_text,
            buttons=buttons_data,
            created_by_user_id=str(current_user.id),
        )

        logger.info(f"📋 [SEND-INTERACTIVE] Résultat de la création du template: success={template_result.get('success')}")

        if not template_result.get("success"):
            error_message = "; ".join(template_result.get("errors", ["Erreur inconnue"]))
            logger.error(f"❌ [SEND-INTERACTIVE] Erreur de validation: {error_message}")
            await supabase_execute(
                supabase.table("messages")
                .update({"status": "failed", "error_message": error_message})
                .eq("id", message_id)
            )
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Erreur de validation du message",
                    "errors": template_result.get("errors", []),
                },
            )

        logger.info(f"✅ [SEND-INTERACTIVE] Template créé avec succès, retour du message optimiste")
        return {
            "status": "pending",
            "message_id": message_id,
            "message": "Message en cours de validation par Meta. Il sera envoyé automatiquement une fois approuvé.",
        }

    # Fenêtre gratuite : envoi normal du message interactif
    logger.info("=" * 80)
    logger.info("✅ [SEND-INTERACTIVE] ========== FENÊTRE GRATUITE ==========")
    logger.info(f"✅ [SEND-INTERACTIVE] conversation_id={conversation_id}")
    logger.info(f"✅ [SEND-INTERACTIVE] interactive_type={interactive_type}")
    logger.info(f"✅ [SEND-INTERACTIVE] Paramètres extraits:")
    logger.info(f"   - body_text: {repr(body_text)}")
    logger.info(f"   - header_text: {repr(header_text)}")
    logger.info(f"   - footer_text: {repr(footer_text)}")
    logger.info(f"   - buttons (raw): {repr(payload.get('buttons'))}")
    logger.info(f"   - sections (raw): {repr(payload.get('sections'))}")
    logger.info(f"   - button_text (raw): {repr(payload.get('button_text'))}")

    normalized_header_text = header_text.strip() if header_text and header_text.strip() else None
    normalized_footer_text = footer_text.strip() if footer_text and footer_text.strip() else None

    logger.info(f"✅ [SEND-INTERACTIVE] Après normalisation:")
    logger.info(f"   - normalized_header_text: {repr(normalized_header_text)}")
    logger.info(f"   - normalized_footer_text: {repr(normalized_footer_text)}")

    if interactive_type == "button":
        buttons = payload.get("buttons", [])
        logger.info(f"✅ [SEND-INTERACTIVE] Boutons extraits: {repr(buttons)}")
        if not buttons:
            raise HTTPException(status_code=400, detail="buttons are required for button type")

        valid_buttons = [btn for btn in buttons if btn.get("id") and btn.get("title")]
        logger.info(f"✅ [SEND-INTERACTIVE] Boutons valides: {len(valid_buttons)}/{len(buttons)}")
        if not valid_buttons:
            raise HTTPException(status_code=400, detail="Aucun bouton valide (id et title requis)")

        interactive_payload = {
            "buttons": [
                {"type": "reply", "reply": {"id": btn["id"], "title": btn["title"]}}
                for btn in valid_buttons
            ]
        }
        logger.info(f"✅ [SEND-INTERACTIVE] interactive_payload construit: {json.dumps(interactive_payload, indent=2, ensure_ascii=False)}")
    elif interactive_type == "list":
        sections = payload.get("sections", [])
        button_text = payload.get("button_text", "Voir les options")
        logger.info(f"✅ [SEND-INTERACTIVE] Sections extraites: {repr(sections)}")
        logger.info(f"✅ [SEND-INTERACTIVE] button_text: {repr(button_text)}")
        if not sections:
            raise HTTPException(status_code=400, detail="sections are required for list type")

        interactive_payload = {
            "button": button_text,
            "sections": sections,
        }
        logger.info(f"✅ [SEND-INTERACTIVE] interactive_payload construit: {json.dumps(interactive_payload, indent=2, ensure_ascii=False)}")
    else:
        raise HTTPException(status_code=400, detail="invalid interactive_type")

    logger.info(f"✅ [SEND-INTERACTIVE] Appel à send_interactive_message_with_storage avec:")
    logger.info(f"   - header_text: {repr(normalized_header_text)}")
    logger.info(f"   - body_text: {repr(body_text)}")
    logger.info(f"   - footer_text: {repr(normalized_footer_text)}")
    logger.info(f"   - interactive_payload: {json.dumps(interactive_payload, indent=2, ensure_ascii=False)}")
    logger.info(f"✅ [SEND-INTERACTIVE] ======================================")

    return await send_interactive_message_with_storage(
        conversation_id=conversation_id,
        interactive_type=interactive_type,
        body_text=body_text,
        interactive_payload=interactive_payload,
        header_text=normalized_header_text,
        footer_text=normalized_footer_text,
        sent_by_user_id=str(current_user.id),
        sent_via="ui",
    )
