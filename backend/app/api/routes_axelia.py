import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.schemas.axelia import (
    AxeliaChatRequest,
    AxeliaChatResponse,
    AxeliaConversationCreate,
    AxeliaConversationPatch,
    AxeliaMessageRating,
)
from app.services.account_service import get_account_by_id
from app.services.axelia_chat_service import run_axelia_chat
from app.services.axelia_conv_service import (
    conv_create,
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

router = APIRouter(prefix="/axelia", tags=["Axelia"])

_AXELIA_CONTEXT_ALL = "__all__"


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


@router.get("/conversations")
async def list_axelia_conversations(current_user: CurrentUser = Depends(get_current_user)):
    return await conv_list_visible(current_user.id)


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
    conv = await conv_get_owned(current_user.id, conversation_id)
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
    conv = await conv_get_owned(current_user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation_not_found")

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
        text, model_used, skills_used, pending = await run_axelia_chat(
            messages=msgs,
            attachment=None,
            log_label=f"axelia-rg-{current_user.id}-{conversation_id[:8]}",
            account=account,
            acting_user=current_user,
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

    conv = await conv_get_owned(current_user.id, body.conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    if conv.get("account_context") != body.account_id:
        raise HTTPException(status_code=400, detail="account_context_mismatch")

    txt = (body.user_message or "").strip()
    has_att = bool(body.attachment and (body.attachment.data_base64 or "").strip())
    approve_only = bool(body.approve_tool_calls) and not txt and not has_att
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

    try:
        text, model_used, skills_used, pending = await run_axelia_chat(
            messages=msgs,
            attachment=att,
            log_label=f"axelia-{current_user.id}-{body.conversation_id[:8]}",
            account=account,
            sector=body.sector,
            approve_tool_calls=body.approve_tool_calls if approve_only else None,
            acting_user=current_user,
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
        if code in ("empty_messages", "empty_reply", "attachment_invalid_base64"):
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
