"""Contacts, conversations récentes, campagnes et profil WABA pour Axelia (lecture)."""
from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from app.core.db import supabase, supabase_execute
from app.core.permissions import PermissionCodes
from app.core.pg import fetch_all, fetch_one, get_pool
from app.services.broadcast_service import (
    get_broadcast_campaign,
    get_broadcast_campaigns,
    get_campaign_stats,
)
from app.services.axelia_inbox_tools import (
    _AXELIA_MULTI_MAX_ACCOUNTS,
    list_accessible_account_rows_for_inbox,
)

if TYPE_CHECKING:
    from app.core.permissions import CurrentUser

_AXELIA_CAMPAIGN_MULTI_TIMEOUT_S = 22.0


def _user_may_use_contacts_api(user: "CurrentUser") -> bool:
    """Aligné sur GET /contacts : contacts.view globale ou au moins un compte dans le périmètre."""
    if user.permissions.has(PermissionCodes.CONTACTS_VIEW):
        return True
    scoped = user.accounts_for(PermissionCodes.CONTACTS_VIEW)
    return bool(scoped)


def _sanitize_search(q: str) -> str:
    s = (q or "").strip()
    if len(s) > 200:
        s = s[:200]
    return re.sub(r"[%_]", " ", s)


def _can_view_account(user: Optional["CurrentUser"], account_id: str) -> bool:
    if not user:
        return False
    return user.permissions.has(PermissionCodes.CONVERSATIONS_VIEW, account_id)


async def search_contacts_for_account(
    account_id: str,
    query: str,
    *,
    limit: int = 15,
) -> Dict[str, Any]:
    raw = _sanitize_search(query)
    if len(raw) < 2:
        return {"error": "Requête trop courte (2 caractères minimum).", "contacts": []}

    lim = max(1, min(int(limit), 40))
    digits = re.sub(r"\D", "", raw)

    pool = get_pool()
    if pool:
        if len(digits) >= 2:
            rows = await fetch_all(
                """
                SELECT DISTINCT ct.id, ct.display_name, ct.whatsapp_number, ct.profile_picture_url
                FROM contacts ct
                INNER JOIN conversations cv ON cv.contact_id = ct.id
                WHERE cv.account_id = $1::uuid
                  AND (
                    COALESCE(ct.display_name, '') ILIKE '%' || $2 || '%'
                    OR COALESCE(ct.whatsapp_name, '') ILIKE '%' || $2 || '%'
                    OR regexp_replace(COALESCE(ct.whatsapp_number, ''), '\\D', '', 'g')
                        LIKE '%' || $3 || '%'
                  )
                ORDER BY ct.display_name NULLS LAST
                LIMIT $4
                """,
                account_id,
                raw,
                digits,
                lim,
            )
        else:
            rows = await fetch_all(
                """
                SELECT DISTINCT ct.id, ct.display_name, ct.whatsapp_number, ct.profile_picture_url
                FROM contacts ct
                INNER JOIN conversations cv ON cv.contact_id = ct.id
                WHERE cv.account_id = $1::uuid
                  AND (
                    COALESCE(ct.display_name, '') ILIKE '%' || $2 || '%'
                    OR COALESCE(ct.whatsapp_name, '') ILIKE '%' || $2 || '%'
                  )
                ORDER BY ct.display_name NULLS LAST
                LIMIT $3
                """,
                account_id,
                raw,
                lim,
            )
        contacts = [
            {
                "id": str(r["id"]),
                "display_name": r.get("display_name"),
                "whatsapp_number": r.get("whatsapp_number"),
                "profile_picture_url": r.get("profile_picture_url"),
            }
            for r in rows
        ]
        return {"query": raw, "total": len(contacts), "contacts": contacts}

    conv_res = await supabase_execute(
        supabase.table("conversations").select("contact_id").eq("account_id", account_id)
    )
    contact_ids = list(
        {str(r["contact_id"]) for r in (conv_res.data or []) if r.get("contact_id")}
    )
    if not contact_ids:
        return {"query": raw, "total": 0, "contacts": []}

    raw_low = raw.lower()
    out: List[Dict[str, Any]] = []
    step = 80
    for i in range(0, len(contact_ids), step):
        chunk = contact_ids[i : i + step]
        res = await supabase_execute(
            supabase.table("contacts")
            .select("id, display_name, whatsapp_number, profile_picture_url, whatsapp_name")
            .in_("id", chunk[:step])
        )
        for row in res.data or []:
            dn = (row.get("display_name") or "").lower()
            wn = (row.get("whatsapp_name") or "").lower()
            wa = row.get("whatsapp_number") or ""
            wa_digits = re.sub(r"\D", "", str(wa))
            match_name = raw_low in dn or raw_low in wn
            match_phone = len(digits) >= 2 and digits in wa_digits
            if not (match_name or match_phone):
                continue
            out.append(
                {
                    "id": str(row["id"]),
                    "display_name": row.get("display_name"),
                    "whatsapp_number": row.get("whatsapp_number"),
                    "profile_picture_url": row.get("profile_picture_url"),
                }
            )
            if len(out) >= lim:
                break
        if len(out) >= lim:
            break

    return {"query": raw, "total": len(out), "contacts": out[:lim]}


async def search_contacts_all_accessible_accounts(
    user: "CurrentUser",
    query: str,
    *,
    limit_per_account: int = 12,
    max_accounts: Optional[int] = None,
    per_account_timeout_s: float = 18.0,
) -> Dict[str, Any]:
    raw = _sanitize_search(query)
    if len(raw) < 2:
        return {"error": "Requête trop courte.", "account_scope": "all_accessible", "accounts": []}

    if not _user_may_use_contacts_api(user):
        return {
            "error": "Permission contacts.view requise pour la recherche de contacts.",
            "account_scope": "all_accessible",
            "accounts": [],
        }

    cap_acc = max_accounts if max_accounts is not None else _AXELIA_MULTI_MAX_ACCOUNTS
    lim_pa = max(1, min(int(limit_per_account), 25))

    rows = await list_accessible_account_rows_for_inbox(user)
    selected = rows[:cap_acc]
    out: List[Dict[str, Any]] = []
    seen_contact: set[str] = set()

    for row in selected:
        aid = str(row.get("id") or "")
        if not aid:
            continue
        if not _can_view_account(user, aid):
            continue
        try:
            part = await asyncio.wait_for(
                search_contacts_for_account(aid, raw, limit=lim_pa),
                timeout=per_account_timeout_s,
            )
        except asyncio.TimeoutError:
            part = {"error": "délai dépassé", "contacts": [], "total": 0}

        contacts = []
        for c in part.get("contacts") or []:
            cid = str(c.get("id") or "")
            if not cid or cid in seen_contact:
                continue
            seen_contact.add(cid)
            contacts.append({**c, "matched_on_account_id": aid})
        out.append(
            {
                "account_id": aid,
                "account_name": row.get("name") or "-",
                "contacts": contacts,
                "total": len(contacts),
                "error": part.get("error"),
            }
        )

    return {
        "account_scope": "all_accessible",
        "query": raw,
        "accounts": out,
        "unique_contacts_found": len(seen_contact),
        "accounts_total_in_scope": len(rows),
        "accounts_iterated": len(selected),
        "accounts_capped": len(rows) > cap_acc,
    }


async def get_contact_detail_for_account(account_id: str, contact_id: str) -> Dict[str, Any]:
    cid = (contact_id or "").strip()
    if not cid:
        return {"error": "contact_id requis."}

    pool = get_pool()
    if pool:
        row = await fetch_one(
            """
            SELECT ct.id, ct.display_name, ct.whatsapp_number, ct.profile_picture_url,
                   ct.whatsapp_name, ct.created_at,
                   (SELECT COUNT(*)::int FROM conversations cv
                    WHERE cv.contact_id = ct.id AND cv.account_id = $2::uuid) AS conversation_count
            FROM contacts ct
            WHERE ct.id = $1::uuid
              AND EXISTS (
                SELECT 1 FROM conversations cv
                WHERE cv.contact_id = ct.id AND cv.account_id = $2::uuid
              )
            LIMIT 1
            """,
            cid,
            account_id,
        )
        if not row:
            return {"error": "Contact introuvable sur cette ligne ou sans conversation sur ce compte."}
        r = dict(row)
        return {
            "contact": {
                "id": str(r["id"]),
                "display_name": r.get("display_name"),
                "whatsapp_number": r.get("whatsapp_number"),
                "whatsapp_name": r.get("whatsapp_name"),
                "profile_picture_url": r.get("profile_picture_url"),
                "created_at": r.get("created_at").isoformat() if r.get("created_at") else None,
                "conversation_count_on_account": r.get("conversation_count"),
            }
        }

    chk = await supabase_execute(
        supabase.table("conversations").select("id").eq("account_id", account_id).eq("contact_id", cid).limit(1)
    )
    if not chk.data:
        return {"error": "Ce contact n’a pas de conversation sur ce compte."}
    conv_cnt_res = await supabase_execute(
        supabase.table("conversations").select("id", count="exact").eq("account_id", account_id).eq("contact_id", cid)
    )
    conv_cnt = getattr(conv_cnt_res, "count", None)
    if conv_cnt is None:
        conv_cnt = len(conv_cnt_res.data or [])
    ct = await supabase_execute(
        supabase.table("contacts")
        .select("id, display_name, whatsapp_number, profile_picture_url, whatsapp_name, created_at")
        .eq("id", cid)
        .limit(1)
    )
    if not ct.data:
        return {"error": "Contact introuvable."}
    row = ct.data[0]
    return {
        "contact": {
            "id": str(row["id"]),
            "display_name": row.get("display_name"),
            "whatsapp_number": row.get("whatsapp_number"),
            "whatsapp_name": row.get("whatsapp_name"),
            "profile_picture_url": row.get("profile_picture_url"),
            "created_at": row.get("created_at"),
            "conversation_count_on_account": conv_cnt,
        }
    }


async def list_recent_conversations_for_account(account_id: str, *, limit: int = 25) -> Dict[str, Any]:
    lim = max(1, min(int(limit), 60))
    pool = get_pool()
    if pool:
        rows = await fetch_all(
            """
            SELECT c.id,
                   c.updated_at,
                   c.client_number,
                   c.status,
                   co.id AS contact_id,
                   co.display_name AS contact_display_name
            FROM conversations c
            LEFT JOIN contacts co ON co.id = c.contact_id
            WHERE c.account_id = $1::uuid
            ORDER BY c.updated_at DESC NULLS LAST
            LIMIT $2
            """,
            account_id,
            lim,
        )
        items = [
            {
                "conversation_id": str(r["id"]),
                "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
                "client_number": r.get("client_number"),
                "status": r.get("status"),
                "contact_id": str(r["contact_id"]) if r.get("contact_id") else None,
                "contact_display_name": r.get("contact_display_name"),
            }
            for r in rows
        ]
        return {"total": len(items), "conversations": items}

    res = await supabase_execute(
        supabase.table("conversations")
        .select("id, updated_at, client_number, status, contact_id, contacts(display_name)")
        .eq("account_id", account_id)
        .order("updated_at", desc=True)
        .limit(lim)
    )
    items = []
    for row in res.data or []:
        nested = row.get("contacts") or {}
        items.append(
            {
                "conversation_id": str(row["id"]),
                "updated_at": row.get("updated_at"),
                "client_number": row.get("client_number"),
                "status": row.get("status"),
                "contact_id": str(row["contact_id"]) if row.get("contact_id") else None,
                "contact_display_name": nested.get("display_name"),
            }
        )
    return {"total": len(items), "conversations": items}


async def list_recent_conversations_all_accessible(
    user: "CurrentUser",
    *,
    limit_per_account: int = 15,
    max_accounts: Optional[int] = None,
    per_account_timeout_s: float = 18.0,
) -> Dict[str, Any]:
    cap_acc = max_accounts if max_accounts is not None else _AXELIA_MULTI_MAX_ACCOUNTS
    lim_pa = max(1, min(int(limit_per_account), 35))

    rows = await list_accessible_account_rows_for_inbox(user)
    selected = rows[:cap_acc]
    out: List[Dict[str, Any]] = []

    for row in selected:
        aid = str(row.get("id") or "")
        if not aid or not _can_view_account(user, aid):
            continue
        try:
            part = await asyncio.wait_for(
                list_recent_conversations_for_account(aid, limit=lim_pa),
                timeout=per_account_timeout_s,
            )
        except asyncio.TimeoutError:
            part = {"error": "délai dépassé", "conversations": [], "total": 0}

        convs = []
        for c in part.get("conversations") or []:
            convs.append({**c, "account_id": aid, "account_name": row.get("name") or "-"})
        out.append(
            {
                "account_id": aid,
                "account_name": row.get("name") or "-",
                "conversations": convs,
                "total": len(convs),
                "error": part.get("error"),
            }
        )

    return {
        "account_scope": "all_accessible",
        "accounts": out,
        "accounts_total_in_scope": len(rows),
        "accounts_iterated": len(selected),
        "accounts_capped": len(rows) > cap_acc,
    }


def _slim_campaign_row(c: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(c.get("id")),
        "group_id": str(c.get("group_id")),
        "account_id": str(c.get("account_id")),
        "status": c.get("status"),
        "message_type": c.get("message_type"),
        "content_preview": ((c.get("content_text") or "")[:200]),
        "scheduled_for": c.get("scheduled_for"),
        "sent_at": c.get("sent_at"),
        "created_at": c.get("created_at"),
        "total_recipients": c.get("total_recipients"),
        "sent_count": c.get("sent_count"),
        "delivered_count": c.get("delivered_count"),
        "read_count": c.get("read_count"),
    }


async def list_broadcast_campaigns_for_account(account_id: str, *, limit: int = 25) -> Dict[str, Any]:
    lim = max(1, min(int(limit), 50))
    campaigns = await get_broadcast_campaigns(account_id=account_id)
    slim = [_slim_campaign_row(c) for c in campaigns[:lim]]
    return {"total": len(slim), "campaigns": slim}


async def list_broadcast_campaigns_all_accessible(
    user: "CurrentUser",
    *,
    limit_per_account: int = 15,
    max_accounts: Optional[int] = None,
    per_account_timeout_s: float = _AXELIA_CAMPAIGN_MULTI_TIMEOUT_S,
) -> Dict[str, Any]:
    cap_acc = max_accounts if max_accounts is not None else _AXELIA_MULTI_MAX_ACCOUNTS
    lim_pa = max(1, min(int(limit_per_account), 30))

    rows = await list_accessible_account_rows_for_inbox(user)
    selected = rows[:cap_acc]
    out: List[Dict[str, Any]] = []

    for row in selected:
        aid = str(row.get("id") or "")
        if not aid or not _can_view_account(user, aid):
            continue
        try:
            part = await asyncio.wait_for(
                list_broadcast_campaigns_for_account(aid, limit=lim_pa),
                timeout=per_account_timeout_s,
            )
        except asyncio.TimeoutError:
            part = {"error": "délai dépassé", "campaigns": [], "total": 0}

        out.append(
            {
                "account_id": aid,
                "account_name": row.get("name") or "-",
                "campaigns": part.get("campaigns") or [],
                "total": part.get("total") or 0,
                "error": part.get("error"),
            }
        )

    return {
        "account_scope": "all_accessible",
        "accounts": out,
        "accounts_total_in_scope": len(rows),
        "accounts_iterated": len(selected),
        "accounts_capped": len(rows) > cap_acc,
    }


async def get_campaign_bundle_skill(
    user: "CurrentUser",
    campaign_id: str,
    *,
    max_recipient_rows: int = 40,
) -> Dict[str, Any]:
    cid = (campaign_id or "").strip()
    if not cid:
        return {"error": "campaign_id requis."}

    campaign = await get_broadcast_campaign(cid)
    if not campaign:
        return {"error": "Campagne introuvable."}
    aid = str(campaign.get("account_id") or "")
    if not aid or not user.permissions.has(PermissionCodes.CONVERSATIONS_VIEW, aid):
        return {"error": "Campagne inaccessible avec tes permissions sur ce compte."}

    stats = await get_campaign_stats(cid)
    rec = stats.get("recipients") or []
    truncated = len(rec) > max_recipient_rows
    stats["recipients"] = rec[:max_recipient_rows]
    stats["recipients_truncated"] = truncated
    stats["campaign_row"] = _slim_campaign_row(campaign)
    return stats


async def get_whatsapp_business_profile_skill(account: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.whatsapp_api_service import get_business_profile

    pnid = account.get("phone_number_id")
    tok = account.get("access_token")
    if not pnid or not tok:
        return {"error": "Compte sans phone_number_id ou access_token pour appeler Meta."}

    try:
        prof = await get_business_profile(str(pnid), str(tok))
        return {"profile": prof}
    except Exception as exc:
        return {"error": f"Lecture profil Meta impossible : {str(exc)[:280]}"}

