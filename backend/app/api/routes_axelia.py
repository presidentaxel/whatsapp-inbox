import codecs
import json as _json
import logging
from types import SimpleNamespace
from typing import Any, AsyncIterator, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes, load_current_user_async
from app.schemas.axelia import (
    AxeliaChatRequest,
    AxeliaChatResponse,
    AxeliaConversationCreate,
    AxeliaConversationPatch,
    AxeliaConversationShareCreate,
    AxeliaConversationShareResult,
    AxeliaShareCandidate,
    AxeliaMessageRating,
)
from app.core.db import supabase, supabase_execute
from app.services.account_service import get_account_by_id, get_all_accounts
from app.services.axelia_chat_service import (
    context_cache_stats,
    metrics_snapshot,
    progress_get,
    run_axelia_chat,
    stream_axelia_chat,
)
from app.services.axelia_conv_service import (
    conversation_share_create,
    conversation_shares_list,
    conv_create,
    conv_get_accessible,
    conv_get_owned,
    conv_list_visible,
    conv_update,
    delete_last_assistant,
    message_insert,
    message_set_rating,
    messages_list,
    title_from_prompt,
)

logger = logging.getLogger(__name__)


def require_axelia_hub_access(current_user: CurrentUser = Depends(get_current_user)) -> None:
    """Toutes les routes /axelia exigent la permission globale axelia.access."""
    current_user.require(PermissionCodes.AXELIA_ACCESS)


router = APIRouter(
    prefix="/axelia",
    tags=["Axelia"],
    dependencies=[Depends(require_axelia_hub_access)],
)

_AXELIA_CONTEXT_ALL = "__all__"


def _consume_sse_done_from_buffer(buffer: str) -> tuple[str, Optional[dict[str, Any]]]:
    """Consomme les frames SSE complètes et extrait le dernier payload `event: done` trouvé."""
    done_payload: Optional[dict[str, Any]] = None
    while True:
        sep = buffer.find("\n\n")
        if sep < 0:
            break
        frame = buffer[:sep]
        buffer = buffer[sep + 2 :]
        if "event: done" not in frame:
            continue
        data_lines = []
        for line in frame.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not data_lines:
            continue
        try:
            payload = _json.loads("\n".join(data_lines))
            if isinstance(payload, dict):
                done_payload = payload
        except Exception:
            logger.debug("axelia stream: invalid done payload", exc_info=True)
    return buffer, done_payload


async def build_axelia_perimeter_context(
    current_user: CurrentUser,
    account_id: str,
    *,
    ui_hint: Optional[str] = None,
) -> dict:
    """Données périmètre WABA injectées dans le prompt (côté serveur, alignées sur les droits utilisateur)."""
    hint = (ui_hint or "").strip() or None
    out: dict = {"ui_hint": hint}
    if account_id == _AXELIA_CONTEXT_ALL:
        out["mode"] = "all"
        ids = current_user.accounts_for(PermissionCodes.CONVERSATIONS_VIEW)
        if ids is None:
            rows = await get_all_accounts(None)
        else:
            rows = await get_all_accounts(list(ids))
        preview = []
        for r in rows[:40]:
            preview.append(
                {
                    "id": str(r.get("id")),
                    "name": r.get("name") or "-",
                    "phone_number": r.get("phone_number") or "-",
                }
            )
        out["all_accounts_preview"] = preview
        return out
    acc = await get_account_by_id(account_id)
    out["mode"] = "single"
    if acc:
        out["primary"] = {
            "id": str(acc.get("id")),
            "name": acc.get("name") or "-",
            "phone_number": acc.get("phone_number") or "-",
        }
    else:
        out["primary"] = {
            "id": str(account_id),
            "name": "-",
            "phone_number": "-",
        }
    return out


def _user_can_scope_all_accounts(current_user: CurrentUser) -> bool:
    if PermissionCodes.CONVERSATIONS_VIEW in current_user.permissions.global_permissions:
        return True
    scoped = current_user.permissions.accounts_with(PermissionCodes.CONVERSATIONS_VIEW)
    return bool(scoped)


async def _check_account_access(current_user: CurrentUser, account_id: str):
    if account_id == _AXELIA_CONTEXT_ALL:
        if not _user_can_scope_all_accounts(current_user):
            raise HTTPException(status_code=403, detail="permission_denied")
        return
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    current_user.require(PermissionCodes.CONVERSATIONS_VIEW, account_id)


async def _load_user_by_app_user_id(user_id: str) -> Optional[CurrentUser]:
    row_res = await supabase_execute(
        supabase.table("app_users")
        .select("user_id,email,is_active")
        .eq("user_id", user_id)
        .limit(1)
    )
    rows = list(row_res.data or [])
    if not rows:
        return None
    row = rows[0]
    if not bool(row.get("is_active", True)):
        return None
    pseudo = SimpleNamespace(
        id=str(row.get("user_id")),
        email=row.get("email"),
        user_metadata={},
    )
    try:
        return await load_current_user_async(pseudo)
    except Exception:
        logger.warning("axelia share: failed loading target user permissions", exc_info=True)
        return None


def _build_share_warning(
    *,
    account_context: str,
    target_user: Optional[CurrentUser],
) -> Optional[str]:
    if not target_user:
        return (
            "Le collègue destinataire n'a pas un profil d'accès résolu côté serveur. "
            "Certaines données peuvent ne pas lui être accessibles."
        )
    if account_context == _AXELIA_CONTEXT_ALL:
        can_all = _user_can_scope_all_accounts(target_user)
        if not can_all:
            return (
                "Le collègue n'a pas accès à l'ensemble des comptes de ce fil. "
                "Certaines données de la discussion peuvent être indisponibles pour lui."
            )
        return None
    has_account_access = target_user.permissions.has(
        PermissionCodes.CONVERSATIONS_VIEW,
        account_context,
    )
    if not has_account_access:
        return (
            "Le collègue n'a pas l'accès conversation à ce compte. "
            "Certaines données mentionnées dans ce fil peuvent lui être indisponibles."
        )
    return None


@router.get("/conversations")
async def list_axelia_conversations(
    current_user: CurrentUser = Depends(get_current_user),
    limit: Optional[int] = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Liste légère (sans messages). Pagination optionnelle : `limit` + `offset` sur la liste triée (épinglés d’abord)."""
    return await conv_list_visible(current_user.id, limit=limit, offset=offset)


@router.get("/share/candidates", response_model=List[AxeliaShareCandidate])
async def list_axelia_share_candidates(
    q: str = Query("", max_length=120),
    limit: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
):
    needle = (q or "").strip().lower()
    res = await supabase_execute(
        supabase.table("app_users")
        .select("user_id,email,display_name,is_active")
        .eq("is_active", True)
        .order("display_name")
    )
    out: List[AxeliaShareCandidate] = []
    for row in res.data or []:
        uid = str(row.get("user_id") or "")
        if not uid or uid == current_user.id:
            continue
        dn = (row.get("display_name") or "").strip()
        em = (row.get("email") or "").strip()
        hay = f"{dn} {em}".lower()
        if needle and needle not in hay:
            continue
        out.append(AxeliaShareCandidate(user_id=uid, display_name=dn or None, email=em or None))
        if len(out) >= limit:
            break
    return out


@router.post("/conversations")
async def create_axelia_conversation(
    body: AxeliaConversationCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    ctx = body.account_context.strip() or _AXELIA_CONTEXT_ALL
    await _check_account_access(current_user, ctx)
    title = (body.title or "Nouvelle discussion").strip() or "Nouvelle discussion"
    row = await conv_create(current_user.id, ctx, title=title[:240])
    if not row.get("id"):
        raise HTTPException(status_code=500, detail="create_failed")
    return row


@router.get("/conversations/{conversation_id}/shares")
async def get_axelia_conversation_shares(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    conv = await conv_get_owned(current_user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    rows = await conversation_shares_list(current_user.id, conversation_id)
    if not rows:
        return []
    user_ids = [str(r.get("shared_with_user_id")) for r in rows if r.get("shared_with_user_id")]
    users_map: dict[str, dict[str, Any]] = {}
    if user_ids:
        ures = await supabase_execute(
            supabase.table("app_users")
            .select("user_id,display_name,email")
            .in_("user_id", user_ids)
        )
        users_map = {str(r.get("user_id")): r for r in (ures.data or [])}
    out = []
    for r in rows:
        uid = str(r.get("shared_with_user_id") or "")
        u = users_map.get(uid) or {}
        out.append(
            {
                **r,
                "shared_with_display_name": u.get("display_name"),
                "shared_with_email": u.get("email"),
            }
        )
    return out


@router.post("/conversations/{conversation_id}/shares", response_model=AxeliaConversationShareResult)
async def post_axelia_conversation_share(
    conversation_id: str,
    body: AxeliaConversationShareCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    conv = await conv_get_owned(current_user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    target_user_id = (body.target_user_id or "").strip()
    if not target_user_id:
        raise HTTPException(status_code=400, detail="target_user_id_required")
    if target_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="cannot_share_with_self")

    target_user = await _load_user_by_app_user_id(target_user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="target_user_not_found")
    if not target_user.permissions.has(PermissionCodes.AXELIA_ACCESS):
        raise HTTPException(status_code=400, detail="target_user_axelia_access_required")

    warning = _build_share_warning(
        account_context=str(conv.get("account_context") or _AXELIA_CONTEXT_ALL),
        target_user=target_user,
    )
    await conversation_share_create(
        current_user.id,
        conversation_id,
        target_user_id,
        warning_message=warning,
    )
    return AxeliaConversationShareResult(
        conversation_id=conversation_id,
        target_user_id=target_user_id,
        warning=warning,
    )


@router.patch("/conversations/{conversation_id}")
async def patch_axelia_conversation(
    conversation_id: str,
    body: AxeliaConversationPatch,
    current_user: CurrentUser = Depends(get_current_user),
):
    row = await conv_update(
        current_user.id,
        conversation_id,
        title=body.title,
        pinned=body.pinned,
        hidden=body.hidden,
    )
    if not row:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    return row


@router.get("/conversations/{conversation_id}/messages")
async def get_axelia_messages(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    conv = await conv_get_accessible(current_user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    rows = await messages_list(conversation_id)
    return [{"id": m["id"], **{k: v for k, v in m.items() if k != "id"}} for m in rows]


@router.patch("/messages/{message_id}/rating")
async def patch_message_rating(
    message_id: str,
    body: AxeliaMessageRating,
    current_user: CurrentUser = Depends(get_current_user),
):
    row = await message_set_rating(current_user.id, message_id, body.rating)
    if not row:
        raise HTTPException(status_code=404, detail="message_not_found")
    return row


@router.post("/conversations/{conversation_id}/regenerate", response_model=AxeliaChatResponse)
async def regenerate_axelia_reply(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    conv = await conv_get_accessible(current_user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    if conv.get("read_only"):
        raise HTTPException(status_code=403, detail="conversation_read_only")

    await _check_account_access(current_user, conv.get("account_context") or _AXELIA_CONTEXT_ALL)

    ok = await delete_last_assistant(conversation_id)
    if not ok:
        raise HTTPException(status_code=400, detail="no_assistant_to_regenerate")

    rows = await messages_list(conversation_id)
    if not rows:
        raise HTTPException(status_code=400, detail="empty_thread")

    msgs: List[dict[str, Any]] = []
    for r in rows:
        msgs.append(
            {
                "role": r["role"],
                "text": r.get("content_text") or "",
            }
        )

    try:
        ctx = conv.get("account_context") or _AXELIA_CONTEXT_ALL
        account = await get_account_by_id(ctx) if ctx != _AXELIA_CONTEXT_ALL else None
        perimeter = await build_axelia_perimeter_context(current_user, ctx)
        text, model_used, skills_used, pending = await run_axelia_chat(
            messages=msgs,
            attachment=None,
            log_label=f"axelia-rg-{current_user.id}-{conversation_id[:8]}",
            account=account,
            acting_user=current_user,
            perimeter_context=perimeter,
        )
    except ValueError as exc:
        code = str(exc) or "bad_request"
        if code == "gemini_not_configured":
            raise HTTPException(status_code=503, detail=code)
        if code == "gemini_unavailable":
            raise HTTPException(status_code=503, detail=code)
        raise HTTPException(status_code=400, detail=code)
    except Exception as exc:
        logger.exception("axelia regenerate: %s", exc)
        raise HTTPException(status_code=500, detail="axelia_failed")

    as_row = await message_insert(
        conversation_id,
        role="model",
        content_text=text,
        model_used=model_used,
    )
    await conv_update(current_user.id, conversation_id)

    return AxeliaChatResponse(
        text=text,
        generation_model=model_used,
        assistant_message_id=as_row.get("id"),
        user_message_id=None,
        skills_used=skills_used or None,
        pending_tool_calls=pending or None,
    )


@router.post("/chat", response_model=AxeliaChatResponse)
async def axelia_chat(
    body: AxeliaChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    await _check_account_access(current_user, body.account_id)

    conv = await conv_get_accessible(current_user.id, body.conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    if conv.get("read_only"):
        raise HTTPException(status_code=403, detail="conversation_read_only")

    txt = (body.user_message or "").strip()
    has_att = bool(body.attachment and (body.attachment.data_base64 or "").strip())
    approve_only = bool(body.approve_tool_calls) and not txt and not has_att

    # Une discussion lancée en « Tous les comptes » peut viser une ligne précise au moment
    # de la confirmation d'une action sensible (ex. upsert_agent_studio_config) sans qu'on
    # force l'utilisateur à recréer un fil : on accepte l'override si le contexte stocké
    # est `__all__` et que l'utilisateur a accès à la ligne demandée (déjà vérifié plus haut).
    conv_ctx = conv.get("account_context") or _AXELIA_CONTEXT_ALL
    if conv_ctx != body.account_id:
        allow_override = (
            approve_only
            and conv_ctx == _AXELIA_CONTEXT_ALL
            and body.account_id != _AXELIA_CONTEXT_ALL
        )
        if not allow_override:
            raise HTTPException(status_code=400, detail="account_context_mismatch")

    if approve_only and body.account_id == _AXELIA_CONTEXT_ALL:
        raise HTTPException(
            status_code=400,
            detail="account_required_for_tools",
        )
    if not txt and not has_att and not approve_only:
        raise HTTPException(status_code=400, detail="empty_user_message")

    att: Optional[dict[str, str]] = None
    if body.attachment:
        att = {
            "mime_type": body.attachment.mime_type,
            "data_base64": body.attachment.data_base64,
        }

    user_mid = None
    if not approve_only:
        focus_for_msg = None
        if body.account_id != _AXELIA_CONTEXT_ALL:
            sec_raw = ((body.sector or "").strip() or "general")[:80]
            if sec_raw and sec_raw != "general":
                focus_for_msg = sec_raw
        um = await message_insert(
            body.conversation_id,
            role="user",
            content_text=txt or ("(image)" if has_att else ""),
            model_used=None,
            focus_tag=focus_for_msg,
        )
        user_mid = um.get("id")

        if (conv.get("title") or "").strip() in ("", "Nouvelle discussion") and txt:
            await conv_update(
                current_user.id,
                body.conversation_id,
                title=title_from_prompt(txt),
            )

    rows = await messages_list(body.conversation_id)
    msgs = [
        {"role": r["role"], "text": r.get("content_text") or ""} for r in rows
    ]

    account = (
        await get_account_by_id(body.account_id)
        if body.account_id != _AXELIA_CONTEXT_ALL
        else None
    )

    perimeter = await build_axelia_perimeter_context(
        current_user,
        body.account_id,
        ui_hint=body.ui_perimeter_hint,
    )

    progress_key = (body.progress_key or "").strip()[:80] or None
    if progress_key:
        from app.services.axelia_chat_service import progress_set as _pset

        _pset(
            progress_key,
            {
                "phase": "received",
                "user_id": current_user.id,
                "conversation_id": body.conversation_id,
                "skills": [],
            },
        )

    try:
        text, model_used, skills_used, pending = await run_axelia_chat(
            messages=msgs,
            attachment=att,
            log_label=f"axelia-{current_user.id}-{body.conversation_id[:8]}",
            account=account,
            sector=body.sector,
            response_depth=body.response_depth,
            approve_tool_calls=body.approve_tool_calls if approve_only else None,
            acting_user=current_user,
            perimeter_context=perimeter,
            progress_key=progress_key,
        )
    except ValueError as exc:
        code = str(exc) or "bad_request"
        if code == "gemini_not_configured":
            raise HTTPException(status_code=503, detail=code)
        if code == "gemini_unavailable":
            raise HTTPException(status_code=503, detail=code)
        if code == "invalid_approve_tool_calls":
            raise HTTPException(status_code=400, detail=code)
        if code == "account_required_for_approve":
            raise HTTPException(status_code=400, detail=code)
        if code == "user_required_for_approve_block":
            raise HTTPException(status_code=400, detail=code)
        if code == "axelia_tools_timeout":
            raise HTTPException(status_code=504, detail=code)
        if code in (
            "empty_messages",
            "empty_reply",
            "attachment_invalid_base64",
            "attachment_unsupported_mime",
        ):
            raise HTTPException(status_code=400, detail=code)
        logger.warning("axelia chat failed: %s", exc)
        raise HTTPException(status_code=400, detail=code)
    except Exception as exc:
        logger.exception("axelia chat error: %s", exc)
        raise HTTPException(status_code=500, detail="axelia_failed")

    am = await message_insert(
        body.conversation_id,
        role="model",
        content_text=text,
        model_used=model_used,
    )

    await conv_update(current_user.id, body.conversation_id)

    return AxeliaChatResponse(
        text=text,
        generation_model=model_used,
        user_message_id=user_mid,
        assistant_message_id=am.get("id"),
        skills_used=skills_used or None,
        pending_tool_calls=pending or None,
    )


@router.get("/chat/progress/{progress_key}")
async def get_axelia_chat_progress(
    progress_key: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Lecture légère de l'état d'avancement d'une requête `/axelia/chat` en cours.

    Renvoie `{}` si la clé est inconnue (requête pas démarrée, déjà terminée ou TTL expiré).
    Réservé au propriétaire de la requête (filtrage par `user_id` côté serveur).
    """
    payload = progress_get(progress_key, owner_user_id=current_user.id)
    return payload or {}


@router.post("/chat/stream")
async def axelia_chat_stream(
    body: AxeliaChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Streaming SSE de la réponse Axelia.

    Mêmes pré-conditions que `/axelia/chat` (auth, périmètre, persistance). Le corps de la
    réponse est un flux ``text/event-stream`` avec les évènements suivants :
    - ``meta``     : modèle choisi, classifier, périmètre, ``user_message_id``.
    - ``progress`` : phase, skills courants, skills cumulés, ``todos`` (mis à jour en direct pendant les outils).
    - ``token``    : delta texte de la réponse finale (peut survenir plusieurs fois).
    - ``done``     : payload final (``text``, ``model``, ``skills_used``, ``pending_tool_calls``,
                     ``assistant_message_id``).
    - ``error``    : ``{code, message}`` côté serveur.

    L'enregistrement du message assistant se fait dans ce handler (persistant) après
    l'évènement ``done`` du service.
    """
    await _check_account_access(current_user, body.account_id)

    conv = await conv_get_accessible(current_user.id, body.conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    if conv.get("read_only"):
        raise HTTPException(status_code=403, detail="conversation_read_only")

    txt = (body.user_message or "").strip()
    has_att = bool(body.attachment and (body.attachment.data_base64 or "").strip())
    approve_only = bool(body.approve_tool_calls) and not txt and not has_att

    # Voir `axelia_chat` : on autorise un override de ligne au moment de la confirmation
    # quand la discussion est en « Tous les comptes » (sinon l'utilisateur reste bloqué
    # sans pouvoir changer le périmètre dans un fil déjà entamé).
    conv_ctx = conv.get("account_context") or _AXELIA_CONTEXT_ALL
    if conv_ctx != body.account_id:
        allow_override = (
            approve_only
            and conv_ctx == _AXELIA_CONTEXT_ALL
            and body.account_id != _AXELIA_CONTEXT_ALL
        )
        if not allow_override:
            raise HTTPException(status_code=400, detail="account_context_mismatch")

    if approve_only and body.account_id == _AXELIA_CONTEXT_ALL:
        raise HTTPException(status_code=400, detail="account_required_for_tools")
    if not txt and not has_att and not approve_only:
        raise HTTPException(status_code=400, detail="empty_user_message")

    att: Optional[dict[str, str]] = None
    if body.attachment:
        att = {
            "mime_type": body.attachment.mime_type,
            "data_base64": body.attachment.data_base64,
        }

    user_mid: Optional[str] = None
    if not approve_only:
        focus_for_msg = None
        if body.account_id != _AXELIA_CONTEXT_ALL:
            sec_raw = ((body.sector or "").strip() or "general")[:80]
            if sec_raw and sec_raw != "general":
                focus_for_msg = sec_raw
        um = await message_insert(
            body.conversation_id,
            role="user",
            content_text=txt or ("(image)" if has_att else ""),
            model_used=None,
            focus_tag=focus_for_msg,
        )
        user_mid = um.get("id")

        if (conv.get("title") or "").strip() in ("", "Nouvelle discussion") and txt:
            await conv_update(
                current_user.id,
                body.conversation_id,
                title=title_from_prompt(txt),
            )

    rows = await messages_list(body.conversation_id)
    msgs = [{"role": r["role"], "text": r.get("content_text") or ""} for r in rows]

    account = (
        await get_account_by_id(body.account_id)
        if body.account_id != _AXELIA_CONTEXT_ALL
        else None
    )
    perimeter = await build_axelia_perimeter_context(
        current_user, body.account_id, ui_hint=body.ui_perimeter_hint
    )

    progress_key = (body.progress_key or "").strip()[:80] or None
    if progress_key:
        from app.services.axelia_chat_service import progress_set as _pset

        _pset(
            progress_key,
            {
                "phase": "received",
                "user_id": current_user.id,
                "conversation_id": body.conversation_id,
                "skills": [],
            },
        )

    async def _event_stream() -> AsyncIterator[bytes]:
        # Premier event : on confirme l'`user_message_id` côté client (utile pour mettre
        # à jour la bulle optimiste sans attendre le `done`).
        if user_mid:
            preface = (
                "event: user-saved\n"
                f"data: {{\"user_message_id\": {_json.dumps(user_mid)}}}\n\n"
            )
            yield preface.encode("utf-8")

        final_text = ""
        final_model: Optional[str] = None
        parsed_done: Optional[dict[str, Any]] = None
        sse_buffer = ""
        # Décodage UTF-8 incrémental : ``chunk.decode(..., errors="ignore")`` sur des frontières
        # arbitraires peut tronquer des séquences multi-octets et casser le JSON du frame ``done``
        # → ``final_text`` reste vide et aucune réponse assistant n'est persistée (symptôme « rien ne se sauvegarde »).
        sse_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

        try:
            async for chunk in stream_axelia_chat(
                messages=msgs,
                attachment=att,
                log_label=f"axelia-stream-{current_user.id}-{body.conversation_id[:8]}",
                account=account,
                sector=body.sector,
                response_depth=body.response_depth,
                approve_tool_calls=body.approve_tool_calls if approve_only else None,
                acting_user=current_user,
                perimeter_context=perimeter,
                progress_key=progress_key,
            ):
                # On laisse passer chaque event tel-quel ; on inspecte uniquement `done`
                # pour persister la réponse côté DB.
                yield chunk
                try:
                    sse_buffer += sse_decoder.decode(chunk)
                    sse_buffer, payload = _consume_sse_done_from_buffer(sse_buffer)
                    if isinstance(payload, dict):
                        parsed_done = payload
                        final_text = str(payload.get("text") or "")
                        final_model = payload.get("model")
                except Exception:
                    logger.debug(
                        "axelia stream: post-parse done failed", exc_info=True
                    )
            # Vide le tampon UTF-8 et traite un éventuel frame ``done`` encore dans le buffer.
            sse_buffer += sse_decoder.decode(b"", final=True)
            sse_buffer, payload_tail = _consume_sse_done_from_buffer(sse_buffer)
            if isinstance(payload_tail, dict):
                parsed_done = payload_tail
                final_text = str(payload_tail.get("text") or "")
                final_model = payload_tail.get("model")
        except Exception as exc:
            logger.exception("axelia stream pipe crashed: %s", exc)
            err = (
                "event: error\n"
                + f"data: {_json.dumps({'code': 'axelia_failed', 'message': 'Erreur interne.'})}\n\n"
            )
            yield err.encode("utf-8")
            return

        if parsed_done is not None:
            text_to_store = (final_text or "").strip() or "Réponse vide."
            try:
                am = await message_insert(
                    body.conversation_id,
                    role="model",
                    content_text=text_to_store,
                    model_used=final_model,
                )
                await conv_update(current_user.id, body.conversation_id)
                tail = (
                    "event: persisted\n"
                    + f"data: {_json.dumps({'assistant_message_id': am.get('id'), 'user_message_id': user_mid})}\n\n"
                )
                yield tail.encode("utf-8")
            except Exception as exc:
                logger.exception("axelia stream persist failed: %s", exc)
                err = (
                    "event: error\n"
                    + f"data: {_json.dumps({'code': 'persist_failed', 'message': 'Sauvegarde échouée.'})}\n\n"
                )
                yield err.encode("utf-8")
        else:
            logger.warning(
                "axelia stream: flux terminé sans frame `done` exploitable (conv=%s…)",
                body.conversation_id[:8],
            )

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",  # Désactive le buffering nginx (utile derrière proxy)
        "Connection": "keep-alive",
    }
    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers=headers,
    )


@router.get("/metrics")
async def get_axelia_metrics(current_user: CurrentUser = Depends(get_current_user)):
    """Snapshot des compteurs internes (latence par modèle, ratios, tokens cumulés).

    Visible uniquement si l'utilisateur a la permission `axelia.access` (déjà filtrée par le
    routeur). Les compteurs sont en mémoire (process unique) - pour multi-worker, brancher
    un backend partagé.
    """
    return {
        "metrics": metrics_snapshot(),
        "context_cache": context_cache_stats(),
    }
