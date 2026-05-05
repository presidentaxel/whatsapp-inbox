"""
Templates: listing, téléchargement de média de header, envoi via template,
vérification du statut Meta après création.
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
    calculate_message_price,
    get_account_by_id,
    get_conversation_by_id,
    get_current_user,
    supabase,
    supabase_execute,
    whatsapp_api_service,
)

router = APIRouter()


@router.get("/templates/{conversation_id}")
async def get_available_templates(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Récupère la liste des templates disponibles pour une conversation.
    Retourne les templates UTILITY, MARKETING et AUTHENTICATION approuvés.
    """
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])

    account = await get_account_by_id(conversation["account_id"])
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")

    waba_id = account.get("waba_id")
    access_token = account.get("access_token")
    phone_number_id = account.get("phone_number_id")

    if not waba_id and phone_number_id and access_token:
        try:
            from app.services.whatsapp_api_service import get_phone_number_details
            phone_details = await get_phone_number_details(phone_number_id, access_token)
            waba_id = phone_details.get("waba_id") or phone_details.get("whatsapp_business_account_id")

            if waba_id:
                await supabase_execute(
                    supabase.table("whatsapp_accounts")
                    .update({"waba_id": waba_id})
                    .eq("id", account["id"])
                )
                account["waba_id"] = waba_id
                logger.info(f"✅ WABA ID récupéré et sauvegardé pour le compte {account.get('name')}: {waba_id}")
        except Exception as e:
            logger.warning(f"⚠️ Impossible de récupérer le WABA ID depuis phone_number_id: {e}")

    if not access_token:
        return {
            "templates": [],
            "account_not_configured": True,
            "message": "Configure the WhatsApp account (access_token) to list templates.",
        }

    if not waba_id:
        return {
            "templates": [],
            "account_not_configured": True,
            "message": "Configure the WhatsApp Business Account ID (waba_id) in account settings to list templates.",
        }

    try:
        all_templates = []
        after = None
        limit = 100

        while True:
            templates_result = await whatsapp_api_service.list_message_templates(
                waba_id=waba_id,
                access_token=access_token,
                limit=limit,
                after=after,
            )

            templates_batch = templates_result.get("data", [])
            if not templates_batch:
                break

            all_templates.extend(templates_batch)

            paging = templates_result.get("paging", {})
            after = paging.get("cursors", {}).get("after")
            if not after:
                break

        templates = all_templates

        def get_template_price(category):
            """Prix d'un template selon sa catégorie (prix Meta officiels)."""
            prices = {
                "UTILITY": {"usd": 0.0248, "eur": 0.0248},
                "MARKETING": {"usd": 0.1186, "eur": 0.1186},
                "AUTHENTICATION": {"usd": 0.0248, "eur": 0.0248},
            }
            category_upper = (category or "").upper()
            return prices.get(category_upper, {"usd": 0.0248, "eur": 0.0248})

        approved_templates = []
        for t in templates:
            status = (t.get("status") or "").upper()
            category = (t.get("category") or "").upper()
            template_name = (t.get("name") or "").lower()

            if template_name in ["hello_world", "hello-world"]:
                continue

            # Templates auto-créés (préfixe `auto_`) : temporaires, à masquer.
            if template_name.startswith("auto_"):
                continue

            if status == "APPROVED" and category in ["UTILITY", "MARKETING", "AUTHENTICATION"]:
                price = get_template_price(category)

                template_components = t.get("components", [])
                header_component = next(
                    (c for c in template_components if c.get("type") == "HEADER"),
                    None,
                )

                header_media_url = None
                header_media_type = None

                if header_component:
                    header_format = header_component.get("format")
                    if header_format in ["IMAGE", "VIDEO", "DOCUMENT"]:
                        example = header_component.get("example", {})
                        header_handle = example.get("header_handle", [])
                        example_url = header_handle[0] if isinstance(header_handle, list) and len(header_handle) > 0 else None

                        try:
                            from app.services.storage_service import get_template_media_url, download_and_store_template_media
                            header_media_url = await get_template_media_url(
                                template_name=t.get("name"),
                                template_language=t.get("language", "fr"),
                                account_id=account["id"],
                                media_type=header_format,
                            )

                            if not header_media_url and example_url:
                                try:
                                    logger.info(f"  📥 Téléchargement automatique de l'image pour template {t.get('name')}")
                                    import httpx
                                    async with httpx.AsyncClient(timeout=10.0) as client:
                                        head_response = await client.head(example_url)
                                        content_type = head_response.headers.get("content-type", "image/jpeg")

                                    header_media_url = await download_and_store_template_media(
                                        template_name=t.get("name"),
                                        template_language=t.get("language", "fr"),
                                        account_id=account["id"],
                                        media_url=example_url,
                                        media_type=header_format,
                                        content_type=content_type,
                                    )
                                    if header_media_url:
                                        logger.info(f"  ✅ Image téléchargée et stockée pour template {t.get('name')}: {header_media_url}")
                                except Exception as download_error:
                                    logger.warning(f"  ⚠️  Erreur lors du téléchargement de l'image pour template {t.get('name')}: {download_error}")
                                    header_media_url = example_url

                            if not header_media_url and example_url:
                                header_media_url = example_url
                                logger.info(f"  📷 Utilisation de l'URL d'exemple pour template {t.get('name')}")

                            header_media_type = header_format
                        except Exception as media_error:
                            logger.warning(f"  ⚠️  Erreur lors de la récupération du média pour template {t.get('name')}: {media_error}")
                            if example_url:
                                header_media_url = example_url
                                header_media_type = header_format
                            else:
                                header_media_url = None
                                header_media_type = None

                template_data = {
                    "name": t.get("name"),
                    "status": t.get("status"),
                    "category": t.get("category"),
                    "language": t.get("language"),
                    "components": template_components,
                    "price_usd": price["usd"],
                    "price_eur": price["eur"],
                }

                if header_media_url:
                    template_data["header_media_url"] = header_media_url
                    template_data["header_media_type"] = header_media_type

                approved_templates.append(template_data)

        return {"templates": approved_templates}
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error fetching templates: {error_msg}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f"Error fetching templates: {error_msg}. Check backend logs for details.",
        )


@router.post("/templates/{conversation_id}/download-media")
async def download_template_media(
    conversation_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Télécharge et stocke l'image d'un template depuis une URL.
    """
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_VIEW, conversation["account_id"])

    account = await get_account_by_id(conversation["account_id"])
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")

    template_name = payload.get("template_name")
    template_language = payload.get("template_language", "fr")
    media_url = payload.get("media_url")
    media_type = payload.get("media_type", "IMAGE")

    if not template_name or not media_url:
        raise HTTPException(status_code=400, detail="template_name and media_url are required")

    if media_type not in ["IMAGE", "VIDEO", "DOCUMENT"]:
        raise HTTPException(status_code=400, detail="media_type must be IMAGE, VIDEO, or DOCUMENT")

    try:
        from app.services.storage_service import download_and_store_template_media
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            head_response = await client.head(media_url)
            content_type = head_response.headers.get("content-type", "image/jpeg")

        storage_url = await download_and_store_template_media(
            template_name=template_name,
            template_language=template_language,
            account_id=account["id"],
            media_url=media_url,
            media_type=media_type,
            content_type=content_type,
        )

        if not storage_url:
            raise HTTPException(status_code=500, detail="Failed to download and store template media")

        return {
            "status": "success",
            "storage_url": storage_url,
            "template_name": template_name,
            "template_language": template_language,
            "media_type": media_type,
        }
    except Exception as e:
        logger.error(f"Error downloading template media: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/send-template/{conversation_id}")
async def send_template_message_api(
    conversation_id: str,
    payload: dict,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Envoie un message via template pour une conversation.
    Gère :
      - les templates avec HEADER média (upload automatique → media_id),
      - les variables nommées (`parameter_name`) et numériques (`{{1}}`, ...),
      - la sauvegarde optimiste du message en DB avec boutons et image.
    """
    logger.info(
        "[TEMPLATE SEND] Début conversation_id=%s template_keys=%s",
        conversation_id,
        list(payload.keys()) if isinstance(payload, dict) else "n/a",
    )
    logger.debug("[TEMPLATE SEND] payload=%s", payload)

    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_SEND, conversation["account_id"])

    template_name = payload.get("template_name")
    components = payload.get("components")
    language_code = payload.get("language_code", "fr")

    if not template_name:
        raise HTTPException(status_code=400, detail="template_name_required")

    account = await get_account_by_id(conversation["account_id"])
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")

    phone_id = account.get("phone_number_id")
    token = account.get("access_token")
    to_number = conversation["client_number"]

    if not phone_id or not token:
        raise HTTPException(status_code=400, detail="whatsapp_not_configured")

    try:
        waba_id = account.get("waba_id")
        template_details = None
        if waba_id:
            try:
                all_templates = []
                after = None
                limit = 100

                while True:
                    templates_result = await whatsapp_api_service.list_message_templates(
                        waba_id=waba_id,
                        access_token=token,
                        limit=limit,
                        after=after,
                    )

                    templates_batch = templates_result.get("data", [])
                    if not templates_batch:
                        break

                    all_templates.extend(templates_batch)

                    paging = templates_result.get("paging", {})
                    after = paging.get("cursors", {}).get("after")
                    if not after:
                        break

                template_details = next(
                    (t for t in all_templates if t.get("name") == template_name and t.get("language") == language_code),
                    None,
                )

                if not template_details:
                    template_details = next(
                        (t for t in all_templates if t.get("name") == template_name),
                        None,
                    )
                    if template_details:
                        logger.info(f"  Template trouvé avec une langue différente: {template_details.get('language')} au lieu de {language_code}")

                if template_details:
                    logger.info(f"  ✅ Template trouvé: {template_details.get('name')}, language: {template_details.get('language')}")
                else:
                    logger.warning(f"  ⚠️ Template {template_name} non trouvé dans {len(all_templates)} templates")
            except Exception as e:
                logger.warning(f"Could not fetch template details: {e}", exc_info=True)

        logger.info(f"📤 Envoi template: name={template_name}, to={to_number}, components={components}")
        if template_details:
            logger.info(f"  Template details: {template_details.get('components', [])}")

        final_components = []
        template_header_image_url = None

        # HEADER média : upload de l'exemple → media_id à passer dans le component HEADER.
        if template_details:
            template_components = template_details.get("components", [])
            header_component_template = next(
                (c for c in template_components if c.get("type") == "HEADER"),
                None,
            )

            if header_component_template:
                header_format = header_component_template.get("format")
                if header_format in ["IMAGE", "VIDEO", "DOCUMENT"]:
                    example = header_component_template.get("example", {})
                    header_handle = example.get("header_handle", [])
                    example_url = header_handle[0] if isinstance(header_handle, list) and len(header_handle) > 0 else None

                    if example_url:
                        template_header_image_url = example_url

                        try:
                            from app.core.http_client import get_http_client_for_media
                            from app.services.whatsapp_api_service import upload_media_from_bytes

                            logger.info(f"  📥 Téléchargement du média pour le header: {example_url[:100]}...")
                            client = await get_http_client_for_media()
                            media_response = await client.get(example_url)
                            media_response.raise_for_status()

                            content_type = media_response.headers.get("content-type", "image/jpeg")
                            media_data = media_response.content

                            extension_map = {
                                "image/jpeg": ".jpg",
                                "image/png": ".png",
                                "image/gif": ".gif",
                                "image/webp": ".webp",
                                "video/mp4": ".mp4",
                                "application/pdf": ".pdf",
                            }
                            extension = extension_map.get(content_type, ".jpg")
                            filename = f"template_{template_name}_{header_format.lower()}{extension}"

                            logger.info(f"  📤 Upload du média vers WhatsApp...")
                            upload_result = await upload_media_from_bytes(
                                phone_number_id=phone_id,
                                access_token=token,
                                file_content=media_data,
                                filename=filename,
                                mime_type=content_type,
                            )

                            media_id = upload_result.get("id")
                            if media_id:
                                logger.info(f"  ✅ Média uploadé avec succès, media_id: {media_id}")
                                final_components.append({
                                    "type": "HEADER",
                                    "parameters": [{
                                        "type": header_format.lower(),
                                        header_format.lower(): {"id": media_id},
                                    }],
                                })
                            else:
                                logger.warning(f"  ⚠️ Upload réussi mais pas de media_id dans la réponse: {upload_result}")
                                final_components.append({
                                    "type": "HEADER",
                                    "parameters": [],
                                })
                        except Exception as media_error:
                            logger.error(f"  ❌ Erreur lors de l'upload du média pour le header: {media_error}", exc_info=True)
                            final_components.append({
                                "type": "HEADER",
                                "parameters": [],
                            })
                    else:
                        logger.warning(f"  ⚠️ Pas d'URL d'exemple pour le header {header_format}")
                        final_components.append({
                            "type": "HEADER",
                            "parameters": [],
                        })

        # Variables nommées : Meta exige `parameter_name` (au lieu de l'ordre séquentiel)
        # quand le template définit `body_text_named_params` dans son example.
        has_named_params = False
        named_params_map = {}

        if template_details:
            body_component = next(
                (c for c in template_details.get("components", []) if c.get("type") == "BODY"),
                None,
            )
            if body_component:
                example = body_component.get("example", {})
                body_text_named_params = example.get("body_text_named_params", [])
                if body_text_named_params and len(body_text_named_params) > 0:
                    has_named_params = True
                    for idx, param_info in enumerate(body_text_named_params, start=1):
                        param_name = param_info.get("param_name")
                        if param_name:
                            named_params_map[idx] = param_name
                    logger.info(f"  ℹ️ Template utilise des variables nommées: {named_params_map}")

        if components and len(components) > 0:
            existing_types = {comp.get("type") for comp in final_components}

            for comp in components:
                comp_type = comp.get("type", "").upper()
                if comp_type not in existing_types:
                    if comp.get("parameters") and isinstance(comp.get("parameters"), list) and len(comp.get("parameters", [])) > 0:
                        if has_named_params and comp_type == "BODY":
                            modified_comp = comp.copy()
                            modified_parameters = []
                            for idx, param in enumerate(comp.get("parameters", []), start=1):
                                param_name = named_params_map.get(idx)
                                if param_name:
                                    modified_param = param.copy()
                                    modified_param["parameter_name"] = param_name
                                    modified_parameters.append(modified_param)
                                    logger.info(f"  📝 Paramètre {idx} mappé à variable nommée '{param_name}': {param.get('text', '')[:50]}")
                                else:
                                    modified_parameters.append(param)
                            modified_comp["parameters"] = modified_parameters
                            final_components.append(modified_comp)
                            logger.info(f"  ✅ Component {comp_type} ajouté avec {len(modified_parameters)} paramètres (variables nommées)")
                        else:
                            final_components.append(comp)
                            logger.info(f"  ✅ Component {comp_type} ajouté avec {len(comp.get('parameters', []))} paramètres (ordre séquentiel)")
                        existing_types.add(comp_type)
                else:
                    logger.warning(f"  ⚠️ Component {comp_type} déjà présent dans final_components, ignoré pour éviter les doublons")

        if len(final_components) == 0:
            final_components = None

        logger.info(f"  Final components: {final_components}")

        response = await whatsapp_api_service.send_template_message(
            phone_number_id=phone_id,
            access_token=token,
            to=to_number,
            template_name=template_name,
            language_code=language_code,
            components=final_components,
        )

        message_id = response.get("messages", [{}])[0].get("id")
        timestamp_iso = datetime.now(timezone.utc).isoformat()

        # Reconstruire le texte affiché en remplaçant les variables.
        template_text = ""
        template_buttons = []
        template_variables_dict = {}
        template_named_variables_dict = {}

        if final_components:
            for comp in final_components:
                if comp.get("type") in ["BODY", "HEADER", "FOOTER"] and comp.get("parameters"):
                    parameters = comp.get("parameters", [])
                    for idx, param in enumerate(parameters, start=1):
                        if param.get("type") == "text":
                            text_value = param.get("text", "")
                            param_name = param.get("parameter_name")
                            if param_name:
                                template_named_variables_dict[param_name] = text_value
                            else:
                                template_variables_dict[str(idx)] = text_value

        if template_details:
            template_components = template_details.get("components", [])
            logger.info(f"  Template components: {template_components}")
            body_component = next(
                (c for c in template_components if c.get("type") == "BODY"),
                None,
            )
            header_component = next(
                (c for c in template_components if c.get("type") == "HEADER"),
                None,
            )
            footer_component = next(
                (c for c in template_components if c.get("type") == "FOOTER"),
                None,
            )
            buttons_component = next(
                (c for c in template_components if c.get("type") == "BUTTONS"),
                None,
            )

            if buttons_component and buttons_component.get("buttons"):
                template_buttons = buttons_component.get("buttons", [])
                logger.info(f"  Template buttons found: {len(template_buttons)} buttons")

            import re

            def replace_variables(text, numeric_variables, named_variables):
                """Remplace les variables `{{1}}`, `{{2}}`, etc. et `{{name}}` par leurs valeurs."""
                if not text:
                    return text
                result = text

                if named_variables:
                    for var_name, var_value in named_variables.items():
                        pattern = r'\{\{' + re.escape(var_name) + r'\}\}'
                        result = re.sub(pattern, var_value, result)

                if numeric_variables:
                    # Décroissant pour éviter `{{10}}` → `{{1}}0`.
                    for var_num in sorted(numeric_variables.keys(), key=lambda x: int(x), reverse=True):
                        var_value = numeric_variables[var_num]
                        pattern = r'\{\{' + str(var_num) + r'\}\}'
                        result = re.sub(pattern, var_value, result)
                return result

            if header_component and header_component.get("text"):
                header_text = header_component.get("text", "")
                header_text = replace_variables(header_text, template_variables_dict, template_named_variables_dict)
                if header_text:
                    template_text = header_text + "\n\n"

            if body_component:
                body_text = body_component.get("text", "")
                body_text = replace_variables(body_text, template_variables_dict, template_named_variables_dict)
                template_text += body_text
                logger.info(f"  Template text from BODY (with variables): {body_text}")

            if footer_component:
                footer_text = footer_component.get("text", "")
                footer_text = replace_variables(footer_text, template_variables_dict, template_named_variables_dict)
                if footer_text:
                    if template_text:
                        template_text = f"{template_text}\n\n{footer_text}"
                    else:
                        template_text = footer_text
                    logger.info(f"  Template text with footer: {template_text}")

            if not template_text:
                logger.warning(f"  No BODY or FOOTER component found in template {template_name}")
        else:
            logger.warning(f"  Template details not found for {template_name}, language {language_code}")

        if not template_text:
            template_text = f"[Template: {template_name}]"
            logger.info(f"  Using fallback template text: {template_text}")

        logger.info(f"  Final template text to save (with variables replaced): {template_text}")
        logger.info(f"  Template variables (numeric): {template_variables_dict}")
        logger.info(f"  Template variables (named): {template_named_variables_dict}")

        from app.services.message_service import _update_conversation_timestamp

        # Si le template a une image, on type le message comme `image` pour
        # que l'UI affiche l'aperçu (le `template_name` reste sauvegardé).
        message_type = "template"
        if template_header_image_url:
            message_type = "image"

        message_payload = {
            "conversation_id": conversation_id,
            "direction": "outbound",
            "content_text": template_text,
            "timestamp": timestamp_iso,
            "wa_message_id": message_id,
            "message_type": message_type,
            "status": "sent",
            "template_name": template_name,
            "template_language": language_code,
        }

        if template_variables_dict:
            message_payload["template_variables"] = json.dumps(template_variables_dict)
            logger.info(f"  ✅ Variables sauvegardées: {template_variables_dict}")

        if template_buttons:
            interactive_data = {
                "type": "button",
                "buttons": [
                    {
                        "type": btn.get("type", "QUICK_REPLY"),
                        "text": btn.get("text", ""),
                        "url": btn.get("url", ""),
                        "phone_number": btn.get("phone_number", ""),
                    }
                    for btn in template_buttons[:5]
                ],
            }
            message_payload["interactive_data"] = json.dumps(interactive_data)
            logger.info(f"  ✅ Boutons sauvegardés dans interactive_data: {len(template_buttons)} boutons")

        if template_header_image_url:
            try:
                from app.services.storage_service import download_and_store_template_media
                import httpx

                async with httpx.AsyncClient(timeout=10.0) as client:
                    head_response = await client.head(template_header_image_url)
                    content_type = head_response.headers.get("content-type", "image/jpeg")

                storage_url = await download_and_store_template_media(
                    template_name=template_name,
                    template_language=language_code,
                    account_id=account["id"],
                    media_url=template_header_image_url,
                    media_type="IMAGE",
                    content_type=content_type,
                )

                if storage_url:
                    message_payload["storage_url"] = storage_url
                    logger.info(f"  ✅ Image du template stockée: {storage_url}")
                else:
                    message_payload["storage_url"] = template_header_image_url
                    logger.info(f"  ⚠️ Stockage échoué, utilisation de l'URL WhatsApp directement")
            except Exception as storage_error:
                logger.warning(f"  ⚠️ Erreur lors du stockage de l'image du template: {storage_error}")
                message_payload["storage_url"] = template_header_image_url

        logger.debug("[TEMPLATE SEND] message_payload keys=%s", list(message_payload.keys()))

        try:
            existing = await supabase_execute(
                supabase.table("messages")
                .select("id, content_text")
                .eq("wa_message_id", message_id)
                .limit(1)
            )

            if existing.data:
                # Le webhook peut nous avoir précédés : on ne ré-écrit pas le
                # `content_text` s'il est déjà rempli pour ne pas effacer le
                # contenu rendu correctement.
                existing_record = existing.data[0]
                update_data = {
                    "status": "sent",
                    "timestamp": timestamp_iso,
                }
                if not existing_record.get("content_text"):
                    update_data["content_text"] = template_text
                    logger.info(f"  📝 Mise à jour du content_text vide avec: {template_text[:50]}...")
                else:
                    logger.info(f"  ℹ️  Le message a déjà un content_text, on ne l'écrase pas")

                await supabase_execute(
                    supabase.table("messages")
                    .update(update_data)
                    .eq("id", existing_record["id"])
                )
            else:
                result = await supabase_execute(
                    supabase.table("messages").insert(message_payload)
                )
                logger.info(f"  ✅ Nouveau message template créé avec texte: {template_text[:50]}...")

            await _update_conversation_timestamp(conversation_id, timestamp_iso)
        except Exception as e:
            logger.error("Error saving template message to database: %s", e, exc_info=True)

        price_info = await calculate_message_price(conversation_id, use_template=True)

        return {
            "status": "sent",
            "message_id": message_id,
            "is_free": False,
            "price_usd": price_info["price_usd"],
            "price_eur": price_info["price_eur"],
            "category": "utility",
            "template_name": template_name,
        }
    except Exception as e:
        logger.error(f"Error sending template message: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/check-template-status/{message_id}")
async def check_template_status_endpoint(
    message_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Force la vérification du statut d'un template et l'envoie si approuvé.
    """
    from app.services.pending_template_service import (
        check_and_update_template_status,
        send_pending_template,
        mark_message_as_failed,
    )

    message_result = await supabase_execute(
        supabase.table("messages")
        .select("conversation_id, conversations!inner(account_id)")
        .eq("id", message_id)
        .limit(1)
    )

    if not message_result.data or len(message_result.data) == 0:
        raise HTTPException(status_code=404, detail="message_not_found")

    conversation = message_result.data[0].get("conversations", {})
    if isinstance(conversation, list) and len(conversation) > 0:
        conversation = conversation[0]

    account_id = conversation.get("account_id")
    if not account_id:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    current_user.require(PermissionCodes.MESSAGES_SEND, account_id)

    result = await check_and_update_template_status(message_id)

    if result["status"] == "APPROVED":
        logger.info(f"✅ [MANUAL-CHECK] Template approuvé pour le message {message_id}, envoi en cours...")
        await send_pending_template(message_id)
        return {
            "success": True,
            "status": "approved",
            "message": "Template approuvé et message envoyé",
        }
    elif result["status"] == "REJECTED":
        logger.warning(f"❌ [MANUAL-CHECK] Template rejeté pour le message {message_id}")
        await mark_message_as_failed(message_id, result.get("rejection_reason", "Template rejeté par Meta"))
        return {
            "success": False,
            "status": "rejected",
            "message": f"Template rejeté: {result.get('rejection_reason', 'Raison inconnue')}",
        }
    elif result["status"] == "PENDING":
        return {
            "success": True,
            "status": "pending",
            "message": "Template encore en attente d'approbation",
        }
    else:
        return {
            "success": False,
            "status": result.get("status", "unknown"),
            "message": "Statut inconnu ou template non trouvé",
        }
