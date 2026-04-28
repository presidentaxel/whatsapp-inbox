"""Recherche et lecture de conversations inbox pour Axelia (périmètre compte WABA)."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.core.db import supabase, supabase_execute
from app.core.pg import fetch_all, fetch_one, get_pool


def _sanitize_ilike_fragment(q: str) -> str:
    s = (q or "").strip()
    if len(s) > 120:
        s = s[:120]
    return re.sub(r"[%_]", " ", s)


async def search_messages_text_for_account(
    account_id: str,
    query: str,
    *,
    limit: int = 25,
) -> Dict[str, Any]:
    """
    Recherche textuelle dans les messages du compte (contenu utile pour retrouver une discussion).
    Pas d’embeddings : découpage du besoin en mots-clés + ILIKE ; pour une vision « sémantique »,
    combiner avec reformulations dans la requête utilisateur ou évolutions futures (vecteurs messages).
    """
    raw = _sanitize_ilike_fragment(query)
    if not raw:
        return {"error": "query vide ou trop court.", "hits": []}

    tokens = [t for t in re.split(r"\s+", raw) if len(t) >= 2][:8]
    if not tokens:
        return {"error": "aucun mot-clé exploitable.", "hits": []}

    pool = get_pool()
    lim = max(1, min(limit, 40))

    if pool:
        cond_parts = []
        params: List[Any] = [account_id]
        i = 2
        for tok in tokens:
            cond_parts.append(f"m.content_text ILIKE ${i}")
            params.append(f"%{tok}%")
            i += 1
        where_kw = " AND ".join(cond_parts) if cond_parts else "TRUE"
        params.append(lim)
        sql = f"""
            SELECT m.id AS message_id,
                   m.conversation_id,
                   m.content_text,
                   m.direction,
                   m.timestamp,
                   c.client_number,
                   co.display_name AS contact_display_name,
                   co.id AS contact_id
            FROM messages m
            INNER JOIN conversations c ON c.id = m.conversation_id
            LEFT JOIN contacts co ON co.id = c.contact_id
            WHERE c.account_id = $1::uuid
              AND m.message_type = 'text'
              AND COALESCE(m.content_text, '') <> ''
              AND {where_kw}
            ORDER BY m.timestamp DESC
            LIMIT ${i}
        """
        rows = await fetch_all(sql, *params)
        hits = [
            {
                "message_id": str(r["message_id"]),
                "conversation_id": str(r["conversation_id"]),
                "contact_id": str(r["contact_id"]) if r.get("contact_id") else None,
                "contact_name": r.get("contact_display_name") or r.get("client_number") or "?",
                "direction": r.get("direction"),
                "snippet": (r.get("content_text") or "")[:420],
                "timestamp": r.get("timestamp").isoformat() if r.get("timestamp") else None,
            }
            for r in rows
        ]
        return {"query_tokens": tokens, "total": len(hits), "hits": hits}

    conv_res = await supabase_execute(
        supabase.table("conversations").select("id").eq("account_id", account_id)
    )
    conv_ids = [r["id"] for r in (conv_res.data or []) if r.get("id")]
    if not conv_ids:
        return {"query_tokens": tokens, "total": 0, "hits": []}

    hits: List[Dict[str, Any]] = []
    tl = [t.lower() for t in tokens]
    step = 40
    for i in range(0, len(conv_ids), step):
        chunk = conv_ids[i : i + step]
        res = await supabase_execute(
            supabase.table("messages")
            .select("id, conversation_id, content_text, direction, timestamp")
            .in_("conversation_id", chunk)
            .eq("message_type", "text")
            .order("timestamp", desc=True)
            .limit(400)
        )
        chunk_msgs = res.data or []
        conv_need = list({str(m["conversation_id"]) for m in chunk_msgs if m.get("conversation_id")})
        conv_meta: Dict[str, Dict[str, Any]] = {}
        if conv_need:
            cr = await supabase_execute(
                supabase.table("conversations")
                .select("id, client_number, contact_id, contacts(display_name)")
                .in_("id", conv_need[:80])
            )
            for row in cr.data or []:
                cid = str(row.get("id"))
                nested = row.get("contacts") or {}
                conv_meta[cid] = {
                    "contact_id": row.get("contact_id"),
                    "contact_name": nested.get("display_name") or row.get("client_number") or "?",
                }
        for m in chunk_msgs:
            raw_text = (m.get("content_text") or "").lower()
            if not raw_text or not all(t in raw_text for t in tl):
                continue
            cid = str(m.get("conversation_id") or "")
            cm = conv_meta.get(cid) or {}
            hits.append(
                {
                    "message_id": str(m.get("id")),
                    "conversation_id": cid,
                    "contact_id": cm.get("contact_id"),
                    "contact_name": cm.get("contact_name") or "?",
                    "direction": m.get("direction"),
                    "snippet": (m.get("content_text") or "")[:420],
                    "timestamp": m.get("timestamp"),
                }
            )
            if len(hits) >= lim:
                break
        if len(hits) >= lim:
            break

    hits.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)
    return {"query_tokens": tokens, "total": len(hits), "hits": hits[:lim]}


async def get_conversation_digest_for_account(
    account_id: str,
    conversation_id: str,
    *,
    max_messages: int = 40,
) -> Dict[str, Any]:
    """Récupère les derniers messages texte d’une conversation pour résumer ou qualifier."""
    mid = (conversation_id or "").strip()
    if not mid:
        return {"error": "conversation_id requis."}

    pool = get_pool()
    cap = max(5, min(max_messages, 80))

    if pool:
        meta = await fetch_one(
            """
            SELECT c.id, c.account_id, co.display_name AS contact_display_name
            FROM conversations c
            LEFT JOIN contacts co ON co.id = c.contact_id
            WHERE c.id = $1::uuid AND c.account_id = $2::uuid
            LIMIT 1
            """,
            mid,
            account_id,
        )
        if not meta:
            return {"error": "conversation introuvable ou hors périmètre compte."}
        msgs = await fetch_all(
            """
            SELECT direction, content_text, timestamp
            FROM messages
            WHERE conversation_id = $1::uuid
              AND message_type = 'text'
              AND COALESCE(content_text, '') <> ''
              AND message_type IS DISTINCT FROM 'reaction'
            ORDER BY timestamp DESC
            LIMIT $2
            """,
            mid,
            cap,
        )
        lines = []
        for r in reversed(msgs):
            who = "client" if r.get("direction") == "inbound" else "équipe"
            t = (r.get("content_text") or "").strip()[:2000]
            if t:
                lines.append(f"[{who}] {t}")
        return {
            "conversation_id": mid,
            "contact_hint": meta.get("contact_display_name"),
            "message_count": len(lines),
            "transcript_recent": "\n".join(lines),
        }

    conv_one = await supabase_execute(
        supabase.table("conversations")
        .select("id, account_id, contacts(display_name)")
        .eq("id", mid)
        .eq("account_id", account_id)
        .limit(1)
    )
    data = conv_one.data or []
    if not data:
        return {"error": "conversation introuvable ou hors périmètre compte."}
    meta = data[0]
    nested = meta.get("contacts") or {}

    mres = await supabase_execute(
        supabase.table("messages")
        .select("direction, content_text, timestamp")
        .eq("conversation_id", mid)
        .eq("message_type", "text")
        .order("timestamp", desc=True)
        .limit(cap)
    )
    raw = list(reversed(mres.data or []))
    lines = []
    for r in raw:
        who = "client" if r.get("direction") == "inbound" else "équipe"
        t = (r.get("content_text") or "").strip()[:2000]
        if t:
            lines.append(f"[{who}] {t}")
    return {
        "conversation_id": mid,
        "contact_hint": nested.get("display_name"),
        "message_count": len(lines),
        "transcript_recent": "\n".join(lines),
    }
