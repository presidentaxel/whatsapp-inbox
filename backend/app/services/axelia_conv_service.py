"""Persistance des conversations Axelia (PostgreSQL Supabase PostgREST)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.db import supabase, supabase_execute


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
    res = await supabase_execute(
        supabase.table("axelia_conversations")
        .select("id,user_id,account_context,title,pinned,created_at,updated_at,hidden_at")
        .eq("user_id", user_id)
        .is_("hidden_at", "null")
    )
    rows = list(res.data or [])
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


async def conv_update(
    user_id: str,
    conversation_id: str,
    *,
    title=None,
    pinned=None,
    hidden: Optional[bool] = None,
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
