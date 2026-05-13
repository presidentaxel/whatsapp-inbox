"""
CRUD fils d’assistant Playground (nom, messages JSON, masquage doux).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.db import supabase, supabase_execute
from app.core.pg import execute, fetch_all, fetch_one, get_pool


def _serialize_messages(messages: Any) -> List[Dict[str, Any]]:
    if not isinstance(messages, list):
        return []
    out: List[Dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        item: Dict[str, Any] = {
            "role": role,
            "content": str(m.get("content") or ""),
        }
        if m.get("proposedGraph") is not None:
            item["proposedGraph"] = m.get("proposedGraph")
        out.append(item)
    return out


def _row_to_api(row: Dict[str, Any]) -> Dict[str, Any]:
    raw_msgs = row.get("messages")
    if isinstance(raw_msgs, str):
        try:
            raw_msgs = json.loads(raw_msgs)
        except Exception:
            raw_msgs = []
    if not isinstance(raw_msgs, list):
        raw_msgs = []
    return {
        "id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "account_id": str(row["account_id"]),
        "flow_id": str(row["flow_id"]),
        "title": row.get("title") or "Nouvelle discussion",
        "messages": raw_msgs,
        "hidden_at": row.get("hidden_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


async def list_threads(
    user_id: str,
    account_id: str,
    flow_id: str,
    *,
    archived_only: bool = False,
) -> List[Dict[str, Any]]:
    """Si archived_only : uniquement fils masqués ; sinon uniquement visibles (hidden_at IS NULL)."""
    if get_pool():
        if archived_only:
            rows = await fetch_all(
                """
                SELECT * FROM playground_assist_threads
                WHERE user_id = $1::uuid AND account_id = $2::uuid AND flow_id = $3::uuid
                  AND hidden_at IS NOT NULL
                ORDER BY updated_at DESC
                """,
                user_id,
                account_id,
                flow_id,
            )
        else:
            rows = await fetch_all(
                """
                SELECT * FROM playground_assist_threads
                WHERE user_id = $1::uuid AND account_id = $2::uuid AND flow_id = $3::uuid
                  AND hidden_at IS NULL
                ORDER BY updated_at DESC
                """,
                user_id,
                account_id,
                flow_id,
            )
        return [_row_to_api(dict(r)) for r in rows]

    q = (
        supabase.table("playground_assist_threads")
        .select("*")
        .eq("user_id", user_id)
        .eq("account_id", account_id)
        .eq("flow_id", flow_id)
    )
    if archived_only:
        q = q.not_.is_("hidden_at", "null")
    else:
        q = q.is_("hidden_at", "null")
    res = await supabase_execute(q.order("updated_at", desc=True))
    data = res.data or []
    return [_row_to_api(dict(r)) for r in data]


async def get_thread(
    thread_id: str, user_id: str, account_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    if get_pool():
        if account_id:
            row = await fetch_one(
                """
                SELECT * FROM playground_assist_threads
                WHERE id = $1::uuid AND user_id = $2::uuid AND account_id = $3::uuid
                """,
                thread_id,
                user_id,
                account_id,
            )
        else:
            row = await fetch_one(
                """
                SELECT * FROM playground_assist_threads
                WHERE id = $1::uuid AND user_id = $2::uuid
                """,
                thread_id,
                user_id,
            )
        return _row_to_api(dict(row)) if row else None
    q = (
        supabase.table("playground_assist_threads")
        .select("*")
        .eq("id", thread_id)
        .eq("user_id", user_id)
    )
    if account_id:
        q = q.eq("account_id", account_id)
    res = await supabase_execute(q.limit(1))
    if not res.data:
        return None
    return _row_to_api(dict(res.data[0]))


async def assert_flow_belongs_to_account(flow_id: str, account_id: str) -> bool:
    if get_pool():
        row = await fetch_one(
            "SELECT 1 FROM playground_flows WHERE id = $1::uuid AND account_id = $2::uuid",
            flow_id,
            account_id,
        )
        return row is not None
    res = await supabase_execute(
        supabase.table("playground_flows")
        .select("id")
        .eq("id", flow_id)
        .eq("account_id", account_id)
        .limit(1)
    )
    return bool(res.data)


async def create_thread(
    user_id: str,
    account_id: str,
    flow_id: str,
    title: str,
    messages: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    tid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    title_clean = (title or "").strip() or "Nouvelle discussion"
    msgs = _serialize_messages(messages if messages is not None else [])

    if get_pool():
        row = await fetch_one(
            """
            INSERT INTO playground_assist_threads (
              id, user_id, account_id, flow_id, title, messages, hidden_at, created_at, updated_at
            )
            VALUES ($1::uuid, $2::uuid, $3::uuid, $4::uuid, $5, $6::jsonb, NULL, $7::timestamptz, $7::timestamptz)
            RETURNING *
            """,
            tid,
            user_id,
            account_id,
            flow_id,
            title_clean,
            json.dumps(msgs),
            now,
        )
        return _row_to_api(dict(row)) if row else None

    payload = {
        "id": tid,
        "user_id": user_id,
        "account_id": account_id,
        "flow_id": flow_id,
        "title": title_clean,
        "messages": msgs,
        "hidden_at": None,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    await supabase_execute(supabase.table("playground_assist_threads").insert(payload))
    return _row_to_api(payload)


async def update_thread(
    thread_id: str,
    user_id: str,
    *,
    title: Optional[str] = None,
    messages: Optional[List[Dict[str, Any]]] = None,
    set_title: bool = False,
    set_messages: bool = False,
) -> Optional[Dict[str, Any]]:
    existing = await get_thread(thread_id, user_id)
    if not existing:
        return None

    now = datetime.now(timezone.utc)
    new_title = existing["title"]
    if set_title and title is not None:
        new_title = (title or "").strip() or "Nouvelle discussion"

    new_messages = existing["messages"]
    if set_messages and messages is not None:
        new_messages = _serialize_messages(messages)

    if get_pool():
        await execute(
            """
            UPDATE playground_assist_threads
            SET title = $2, messages = $3::jsonb, updated_at = $4::timestamptz
            WHERE id = $1::uuid AND user_id = $5::uuid
            """,
            thread_id,
            new_title,
            json.dumps(new_messages),
            now,
            user_id,
        )
        return await get_thread(thread_id, user_id)

    patch: Dict[str, Any] = {
        "title": new_title,
        "messages": new_messages,
        "updated_at": now.isoformat(),
    }
    await supabase_execute(
        supabase.table("playground_assist_threads").update(patch).eq("id", thread_id).eq("user_id", user_id)
    )
    return await get_thread(thread_id, user_id)


async def soft_hide_thread(thread_id: str, user_id: str) -> bool:
    now = datetime.now(timezone.utc)
    if get_pool():
        row = await fetch_one(
            """
            UPDATE playground_assist_threads
            SET hidden_at = $2::timestamptz, updated_at = $2::timestamptz
            WHERE id = $1::uuid AND user_id = $3::uuid AND hidden_at IS NULL
            RETURNING id
            """,
            thread_id,
            now,
            user_id,
        )
        return row is not None
    res = await supabase_execute(
        supabase.table("playground_assist_threads")
        .update({"hidden_at": now.isoformat(), "updated_at": now.isoformat()})
        .eq("id", thread_id)
        .eq("user_id", user_id)
        .is_("hidden_at", "null")
    )
    return bool(res.data)


async def restore_thread(thread_id: str, user_id: str) -> bool:
    now = datetime.now(timezone.utc)
    if get_pool():
        row = await fetch_one(
            """
            UPDATE playground_assist_threads
            SET hidden_at = NULL, updated_at = $2::timestamptz
            WHERE id = $1::uuid AND user_id = $3::uuid AND hidden_at IS NOT NULL
            RETURNING id
            """,
            thread_id,
            now,
            user_id,
        )
        return row is not None
    res = await supabase_execute(
        supabase.table("playground_assist_threads")
        .update({"hidden_at": None, "updated_at": now.isoformat()})
        .eq("id", thread_id)
        .eq("user_id", user_id)
        .not_.is_("hidden_at", "null")
    )
    return bool(res.data)
