"""Persistance des conversations Axelia (PostgreSQL Supabase PostgREST)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.db import supabase, supabase_execute

# Sentinelle : ne pas modifier `account_context` dans `conv_update`.
CONV_ACCOUNT_CONTEXT_UNCHANGED = object()


def _is_uuid(val: str) -> bool:
    try:
        UUID(val)
        return True
    except (ValueError, TypeError):
        return False


async def conv_create(user_id: str, account_context: str, title: str = "Nouvelle discussion") -> Dict[str, Any]:
    payload = {
        "user_id": user_id,
        "account_context": account_context,
        "title": title,
        "pinned": False,
        "hidden_at": None,
        "updated_at": datetime.utcnow().isoformat() + "+00:00",
    }
    res = await supabase_execute(supabase.table("axelia_conversations").insert(payload))
    return (res.data or [{}])[0]


async def conv_list_visible(
    user_id: str,
    *,
    limit: Optional[int] = None,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    owned_res = await supabase_execute(
        supabase.table("axelia_conversations")
        .select("id,user_id,account_context,title,pinned,created_at,updated_at,hidden_at")
        .eq("user_id", user_id)
        .is_("hidden_at", "null")
    )
    owned_rows = [
        {
            **r,
            "read_only": False,
            "access_mode": "owner",
            "shared_by_user_id": None,
            "share_warning": None,
        }
        for r in list(owned_res.data or [])
    ]
    shared_res = await supabase_execute(
        supabase.table("axelia_conversation_shares")
        .select("conversation_id,owner_user_id,warning_message")
        .eq("shared_with_user_id", user_id)
    )
    shared_meta = list(shared_res.data or [])
    shared_ids = [
        str(r.get("conversation_id"))
        for r in shared_meta
        if str(r.get("conversation_id") or "").strip()
    ]
    shared_rows: List[Dict[str, Any]] = []
    if shared_ids:
        conv_res = await supabase_execute(
            supabase.table("axelia_conversations")
            .select("id,user_id,account_context,title,pinned,created_at,updated_at,hidden_at")
            .in_("id", shared_ids)
            .is_("hidden_at", "null")
        )
        conv_map = {str(r.get("id")): r for r in list(conv_res.data or [])}
        for s in shared_meta:
            cid = str(s.get("conversation_id") or "")
            conv = conv_map.get(cid)
            if not conv:
                continue
            if str(conv.get("user_id") or "") == user_id:
                # Défense en profondeur: ne pas dupliquer une conv dont on est propriétaire.
                continue
            shared_rows.append(
                {
                    **conv,
                    "read_only": True,
                    "access_mode": "shared",
                    "shared_by_user_id": s.get("owner_user_id"),
                    "share_warning": s.get("warning_message"),
                }
            )
    rows = [*owned_rows, *shared_rows]
    pinned = [r for r in rows if r.get("pinned")]
    unpinned = [r for r in rows if not r.get("pinned")]
    pinned.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
    unpinned.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
    ordered = pinned + unpinned
    if limit is None:
        return ordered
    off = max(0, int(offset or 0))
    lim = max(1, int(limit))
    return ordered[off : off + lim]


async def conv_get_owned(user_id: str, conversation_id: str) -> Optional[Dict[str, Any]]:
    if not _is_uuid(conversation_id):
        return None
    res = await supabase_execute(
        supabase.table("axelia_conversations")
        .select("*")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .limit(1)
    )
    data = res.data
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict):
        return data
    return None


async def conv_get_accessible(user_id: str, conversation_id: str) -> Optional[Dict[str, Any]]:
    """Retourne une conversation visible par l'utilisateur (owner ou partagée)."""
    owned = await conv_get_owned(user_id, conversation_id)
    if owned:
        return {
            **owned,
            "read_only": False,
            "access_mode": "owner",
            "shared_by_user_id": None,
            "share_warning": None,
        }
    if not _is_uuid(conversation_id):
        return None
    share_res = await supabase_execute(
        supabase.table("axelia_conversation_shares")
        .select("conversation_id,owner_user_id,warning_message")
        .eq("conversation_id", conversation_id)
        .eq("shared_with_user_id", user_id)
        .limit(1)
    )
    srows = list(share_res.data or [])
    if not srows:
        return None
    conv_res = await supabase_execute(
        supabase.table("axelia_conversations")
        .select("*")
        .eq("id", conversation_id)
        .is_("hidden_at", "null")
        .limit(1)
    )
    crows = list(conv_res.data or [])
    if not crows:
        return None
    conv = crows[0]
    return {
        **conv,
        "read_only": True,
        "access_mode": "shared",
        "shared_by_user_id": srows[0].get("owner_user_id"),
        "share_warning": srows[0].get("warning_message"),
    }


async def conv_update(
    user_id: str,
    conversation_id: str,
    *,
    title=None,
    pinned=None,
    hidden: Optional[bool] = None,
    account_context: Any = CONV_ACCOUNT_CONTEXT_UNCHANGED,
):
    if not await conv_get_owned(user_id, conversation_id):
        return None
    patch: Dict[str, Any] = {"updated_at": datetime.utcnow().isoformat() + "+00:00"}
    if title is not None:
        patch["title"] = str(title)[:240]
    if pinned is not None:
        patch["pinned"] = bool(pinned)
    if hidden:
        patch["hidden_at"] = datetime.utcnow().isoformat() + "+00:00"
    elif hidden is False:
        patch["hidden_at"] = None
    if account_context is not CONV_ACCOUNT_CONTEXT_UNCHANGED:
        ac = (account_context or "").strip() or "__all__"
        patch["account_context"] = ac
    res = await supabase_execute(
        supabase.table("axelia_conversations")
        .update(patch)
        .eq("id", conversation_id)
        .eq("user_id", user_id)
    )
    data = res.data
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict):
        return data
    return None


async def conversation_share_create(
    owner_user_id: str,
    conversation_id: str,
    shared_with_user_id: str,
    *,
    warning_message: Optional[str] = None,
) -> Dict[str, Any]:
    payload = {
        "conversation_id": conversation_id,
        "owner_user_id": owner_user_id,
        "shared_with_user_id": shared_with_user_id,
        "warning_message": warning_message,
    }
    res = await supabase_execute(
        supabase.table("axelia_conversation_shares").upsert(
            payload,
            on_conflict="conversation_id,shared_with_user_id",
        )
    )
    data = res.data
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict):
        return data
    return {}


async def conversation_shares_list(
    owner_user_id: str,
    conversation_id: str,
) -> List[Dict[str, Any]]:
    res = await supabase_execute(
        supabase.table("axelia_conversation_shares")
        .select("id,conversation_id,owner_user_id,shared_with_user_id,warning_message,created_at")
        .eq("owner_user_id", owner_user_id)
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
    )
    return list(res.data or [])


async def messages_list(conversation_id: str) -> List[Dict[str, Any]]:
    res = await supabase_execute(
        supabase.table("axelia_messages")
        .select("id,conversation_id,role,content_text,rating,model_used,created_at,focus_tag")
        .eq("conversation_id", conversation_id)
        .order("created_at")
    )
    return list(res.data or [])


async def message_insert(
    conversation_id: str,
    *,
    role: str,
    content_text: str,
    model_used: Optional[str],
    focus_tag: Optional[str] = None,
):
    payload: Dict[str, Any] = {
        "conversation_id": conversation_id,
        "role": role,
        "content_text": (content_text or "")[:120000],
        "model_used": model_used,
    }
    if focus_tag is not None:
        ft = (focus_tag or "").strip()
        if ft:
            payload["focus_tag"] = ft[:80]
    res = await supabase_execute(supabase.table("axelia_messages").insert(payload))
    data = res.data
    if isinstance(data, list) and data:
        return data[0]
    return data if isinstance(data, dict) else {}


async def message_set_rating(owner_user_id: str, message_id: str, rating: Optional[int]):
    res = await supabase_execute(
        supabase.table("axelia_messages")
        .select("id,conversation_id")
        .eq("id", message_id)
        .limit(1)
    )
    rows = res.data or []
    if not rows:
        return None
    row = rows[0]
    if not await conv_get_owned(owner_user_id, row["conversation_id"]):
        return None
    if rating is None:
        rdict = {"rating": None}
    elif rating == 1:
        rdict = {"rating": 1}
    elif rating == -1:
        rdict = {"rating": -1}
    else:
        return None
    res2 = await supabase_execute(
        supabase.table("axelia_messages").update(rdict).eq("id", message_id)
    )
    r2 = res2.data
    if isinstance(r2, list) and r2:
        return r2[0]
    return r2 if isinstance(r2, dict) else None


async def delete_last_assistant(conversation_id: str) -> bool:
    res = await supabase_execute(
        supabase.table("axelia_messages")
        .select("id,role,created_at")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(20)
    )
    rows = list(res.data or [])
    target = None
    for r in rows:
        if r.get("role") == "model":
            target = r
            break
    if not target:
        return False
    await supabase_execute(
        supabase.table("axelia_messages").delete().eq("id", target["id"])
    )
    return True


def title_from_prompt(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return "Nouvelle discussion"
    if len(t) <= 52:
        return t
    return t[:49] + "…"
