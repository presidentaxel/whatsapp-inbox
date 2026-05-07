"""Recherche et lecture de conversations inbox pour Axelia (périmètre compte WABA)."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from app.core.db import supabase, supabase_execute
from app.core.pg import fetch_all, fetch_one, get_pool
from app.core.permissions import PermissionCodes
from app.services.account_service import get_all_accounts

if TYPE_CHECKING:
    from app.core.permissions import CurrentUser

_AXELIA_MULTI_MAX_ACCOUNTS = 40
_AXELIA_MULTI_SUMMARY_TIMEOUT_S = 25.0
_AXELIA_MULTI_SEARCH_TIMEOUT_S = 20.0
# Fallback Supabase (sans pool Postgres) : ne balayer que les N conversations les plus récentes
_SUPABASE_FALLBACK_MAX_CONVERSATIONS = 500

# Borne anti-élargissement : évite les requêtes sur 10 ans qui rapatrieraient toute la table
# côté fallback Supabase. Au-delà, on garde la requête mais on log un warning.
_DATE_RANGE_MAX_DAYS = 366

_SATISFACTION_POSITIVE_RE = re.compile(
    r"\b("
    r"merci(?:\s+beaucoup)?|"
    r"parfait|super|top|excellent|g[eé]nial|nickel|impeccable|"
    r"content(?:e|s)?|satisfait(?:e|s)?|ravi(?:e|s)?|"
    r"bravo|professionnel(?:le)?|rapide|efficace|recommande|"
    r"au\s+top|tr[eè]s\s+bien|"
    r"thank\s*you|thanks|great|awesome|perfect"
    r")\b",
    flags=re.IGNORECASE,
)
_SATISFACTION_NEGATIVE_RE = re.compile(
    r"\b("
    r"pas\s+content(?:e|s)?|m[eé]content(?:e|s)?|insatisfait(?:e|s)?|"
    r"nul|catastroph|d[eé]cev|mauvais|lent|probl[eè]me|bug|"
    r"col[èe]re|en\s+retard|remboursement|plainte"
    r")\b",
    flags=re.IGNORECASE,
)


def _score_satisfaction_text(text: str) -> int:
    """Score heuristique de satisfaction implicite.

    >0 = signal positif exploitable ; <=0 = neutre / négatif.
    """
    t = (text or "").strip()
    if not t:
        return 0
    pos = len(_SATISFACTION_POSITIVE_RE.findall(t))
    neg = len(_SATISFACTION_NEGATIVE_RE.findall(t))
    # Les signaux négatifs pèsent plus fort pour éviter les faux positifs.
    return max(0, pos - (neg * 2))


def _sanitize_ilike_fragment(q: str) -> str:
    s = (q or "").strip()
    if len(s) > 120:
        s = s[:120]
    return re.sub(r"[%_]", " ", s)


_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_iso_datetime(
    raw: Any,
    *,
    end_of_day: bool = False,
) -> Optional[datetime]:
    """Parse une date/heure ISO 8601 en `datetime` aware (UTC par défaut).

    Accepte ``YYYY-MM-DD``, ``YYYY-MM-DDTHH:MM:SS`` (avec ou sans fuseau ``Z``/``±HH:MM``).
    Si ``end_of_day=True`` et que la chaîne est une date pure, on positionne l'heure à
    ``23:59:59.999999`` (utile pour ``until`` afin d'inclure toute la journée saisie).

    Retourne ``None`` pour toute entrée invalide - l'appelant doit traiter ``None`` comme
    « pas de borne ».
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    s = str(raw).strip()
    if not s:
        return None
    # Tolérance pratique : on accepte un suffixe `Z` (UTC) que `fromisoformat` < 3.11 rejette.
    s_norm = s.replace("Z", "+00:00") if s.endswith("Z") else s
    try:
        dt = datetime.fromisoformat(s_norm)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if end_of_day and _DATE_ONLY_RE.match(s):
        dt = datetime.combine(dt.date(), time(23, 59, 59, 999_999), tzinfo=dt.tzinfo)
    return dt


def _resolve_date_range(
    since: Any, until: Any
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Parse + normalise (since, until). Inverse l'ordre si l'utilisateur les a swappés."""
    s = parse_iso_datetime(since)
    u = parse_iso_datetime(until, end_of_day=True)
    if s and u and s > u:
        s, u = u, s
    return s, u


def _to_naive_utc(dt: datetime) -> datetime:
    """Convertit un datetime aware/naïf en datetime naïf exprimé en UTC.

    asyncpg refuse de binder un ``datetime`` *aware* sur une colonne
    ``timestamp without time zone`` (cas de ``messages.timestamp`` ici) - il faut
    obligatoirement un naïf. Ce helper centralise la conversion pour ne pas
    perdre l'instant représenté.
    """
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


async def search_messages_text_for_account(
    account_id: str,
    query: str,
    *,
    limit: int = 25,
    match_mode: str = "all",
    since: Any = None,
    until: Any = None,
) -> Dict[str, Any]:
    """
    Recherche textuelle dans les messages du compte (contenu utile pour retrouver une discussion).
    Pas d’embeddings : mots-clés + ILIKE.

    match_mode:
      - ``all`` : tous les tokens doivent apparaître (ET) - précision maximale.
      - ``any`` : au moins un token suffit (OU) - plus de résultats, plus « large ».

    since / until : bornes ISO 8601 (``YYYY-MM-DD`` ou ``YYYY-MM-DDTHH:MM:SS[Z|±HH:MM]``)
    appliquées sur la colonne ``messages.timestamp``. ``until`` saisie en date pure inclut
    la journée entière. Si l'ordre est inversé, on l'auto-corrige.
    """
    raw = _sanitize_ilike_fragment(query)
    if not raw:
        return {"error": "query vide ou trop court.", "hits": []}

    tokens = [t for t in re.split(r"\s+", raw) if len(t) >= 2][:8]
    if not tokens:
        return {"error": "aucun mot-clé exploitable.", "hits": []}

    mode = (match_mode or "all").strip().lower()
    if mode not in ("all", "any"):
        mode = "all"

    since_dt, until_dt = _resolve_date_range(since, until)

    date_filter_meta: Dict[str, Any] = {}
    if since_dt:
        date_filter_meta["since"] = since_dt.isoformat()
    if until_dt:
        date_filter_meta["until"] = until_dt.isoformat()

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
        joiner = " OR " if mode == "any" else " AND "
        where_kw = joiner.join(cond_parts) if cond_parts else "TRUE"
        date_clauses: List[str] = []
        if since_dt:
            date_clauses.append(f"m.timestamp >= ${i}")
            # `messages.timestamp` est `timestamp without time zone` côté schéma -
            # asyncpg exige un datetime naïf pour ce type. On convertit en UTC
            # puis on retire `tzinfo` pour ne pas perdre l'instant représenté.
            params.append(_to_naive_utc(since_dt))
            i += 1
        if until_dt:
            date_clauses.append(f"m.timestamp <= ${i}")
            params.append(_to_naive_utc(until_dt))
            i += 1
        date_sql = (" AND " + " AND ".join(date_clauses)) if date_clauses else ""
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
              AND ({where_kw})
              {date_sql}
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
        out: Dict[str, Any] = {
            "query_tokens": tokens,
            "match_mode": mode,
            "total": len(hits),
            "hits": hits,
        }
        if date_filter_meta:
            out["date_filter"] = date_filter_meta
        return out

    conv_res = await supabase_execute(
        supabase.table("conversations")
        .select("id")
        .eq("account_id", account_id)
        .order("updated_at", desc=True)
        .limit(_SUPABASE_FALLBACK_MAX_CONVERSATIONS)
    )
    conv_ids = [r["id"] for r in (conv_res.data or []) if r.get("id")]
    if not conv_ids:
        out_empty: Dict[str, Any] = {
            "query_tokens": tokens,
            "match_mode": mode,
            "total": 0,
            "hits": [],
        }
        if date_filter_meta:
            out_empty["date_filter"] = date_filter_meta
        return out_empty

    hits: List[Dict[str, Any]] = []
    tl = [t.lower() for t in tokens]
    step = 40

    def _text_matches_any_or_all(raw_text_low: str) -> bool:
        if not raw_text_low:
            return False
        if mode == "any":
            return any(t in raw_text_low for t in tl)
        return all(t in raw_text_low for t in tl)

    def _ts_in_range(ts_value: Any) -> bool:
        if since_dt is None and until_dt is None:
            return True
        # Les timestamps Supabase arrivent généralement en ISO 8601 (string).
        # On évite de planter sur un format inattendu : pas de borne → on garde le hit.
        if isinstance(ts_value, datetime):
            dt = ts_value if ts_value.tzinfo else ts_value.replace(tzinfo=timezone.utc)
        else:
            dt = parse_iso_datetime(ts_value)
            if dt is None:
                return True
        if since_dt and dt < since_dt:
            return False
        if until_dt and dt > until_dt:
            return False
        return True

    for i in range(0, len(conv_ids), step):
        chunk = conv_ids[i : i + step]
        msg_q = (
            supabase.table("messages")
            .select("id, conversation_id, content_text, direction, timestamp")
            .in_("conversation_id", chunk)
            .eq("message_type", "text")
        )
        if since_dt:
            msg_q = msg_q.gte("timestamp", since_dt.isoformat())
        if until_dt:
            msg_q = msg_q.lte("timestamp", until_dt.isoformat())
        msg_q = msg_q.order("timestamp", desc=True).limit(400)
        res = await supabase_execute(msg_q)
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
            if not _text_matches_any_or_all(raw_text):
                continue
            if not _ts_in_range(m.get("timestamp")):
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
    out: Dict[str, Any] = {
        "query_tokens": tokens,
        "match_mode": mode,
        "total": len(hits),
        "hits": hits[:lim],
    }
    if date_filter_meta:
        out["date_filter"] = date_filter_meta
    return out


async def list_accessible_account_rows_for_inbox(user: "CurrentUser") -> List[Dict[str, Any]]:
    """Comptes WABA où l’utilisateur peut voir les conversations (conversations.view)."""
    ids = user.accounts_for(PermissionCodes.CONVERSATIONS_VIEW)
    if ids is None:
        rows = await get_all_accounts(None)
    else:
        rows = await get_all_accounts(list(ids))
    return list(rows)


async def search_messages_all_accessible_accounts(
    user: "CurrentUser",
    query: str,
    *,
    limit_per_account: int = 25,
    max_accounts: Optional[int] = None,
    per_account_timeout_s: float = _AXELIA_MULTI_SEARCH_TIMEOUT_S,
    match_mode: str = "all",
    since: Any = None,
    until: Any = None,
) -> Dict[str, Any]:
    """
    Recherche inbox sur chaque ligne accessible, avec les mêmes plafonds que le chemin une-ligne
    (limit_per_account borné comme search_messages_text_for_account).

    ``since`` / ``until`` (ISO 8601) sont relayés à chaque appel par compte ; voir
    :func:`search_messages_text_for_account` pour le format accepté.
    """
    raw = _sanitize_ilike_fragment(query)
    if not raw:
        return {"error": "query vide ou trop court.", "account_scope": "all_accessible", "accounts": []}

    cap_acc = max_accounts if max_accounts is not None else _AXELIA_MULTI_MAX_ACCOUNTS
    lim_pa = max(1, min(int(limit_per_account), 40))

    since_dt, until_dt = _resolve_date_range(since, until)
    date_filter_meta: Dict[str, Any] = {}
    if since_dt:
        date_filter_meta["since"] = since_dt.isoformat()
    if until_dt:
        date_filter_meta["until"] = until_dt.isoformat()

    rows = await list_accessible_account_rows_for_inbox(user)
    selected = rows[:cap_acc]
    out: List[Dict[str, Any]] = []
    for row in selected:
        aid = str(row.get("id") or "")
        if not aid:
            continue
        if not user.permissions.has(PermissionCodes.CONVERSATIONS_VIEW, aid):
            continue
        try:
            part = await asyncio.wait_for(
                search_messages_text_for_account(
                    aid,
                    query,
                    limit=lim_pa,
                    match_mode=match_mode,
                    since=since_dt,
                    until=until_dt,
                ),
                timeout=per_account_timeout_s,
            )
        except asyncio.TimeoutError:
            part = {"error": f"délai dépassé ({per_account_timeout_s}s)", "hits": [], "total": 0}

        err = part.get("error") if isinstance(part, dict) else None
        hits = part.get("hits") if isinstance(part, dict) else []
        out.append(
            {
                "account_id": aid,
                "account_name": row.get("name") or "-",
                "account_phone": row.get("phone_number") or "-",
                "error": err,
                "hits": hits if isinstance(hits, list) else [],
                "total": part.get("total") if isinstance(part, dict) else 0,
            }
        )

    payload: Dict[str, Any] = {
        "account_scope": "all_accessible",
        "query": query,
        "limit_per_account": lim_pa,
        "accounts": out,
        "accounts_total_in_scope": len(rows),
        "accounts_iterated": len(selected),
        "accounts_capped": len(rows) > cap_acc,
    }
    if date_filter_meta:
        payload["date_filter"] = date_filter_meta
    return payload


async def find_satisfied_contacts_for_account(
    account_id: str,
    *,
    days: int = 30,
    limit: int = 12,
) -> Dict[str, Any]:
    """Détecte les contacts exprimant une satisfaction récente sur une ligne WABA.

    Approche: analyse heuristique des messages `inbound` récents (pas de mot-clé imposé
    par l'utilisateur), scoring positif/négatif, puis agrégation par contact.
    """
    days_i = max(1, min(int(days), 120))
    lim = max(1, min(int(limit), 30))
    since_dt = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=days_i)

    rows: List[Dict[str, Any]] = []
    pool = get_pool()
    if pool:
        rows = await fetch_all(
            """
            SELECT m.content_text,
                   m.timestamp,
                   c.id AS conversation_id,
                   c.client_number,
                   co.id AS contact_id,
                   co.display_name AS contact_display_name
            FROM messages m
            INNER JOIN conversations c ON c.id = m.conversation_id
            LEFT JOIN contacts co ON co.id = c.contact_id
            WHERE c.account_id = $1::uuid
              AND m.direction = 'inbound'
              AND m.message_type = 'text'
              AND COALESCE(m.content_text, '') <> ''
              AND m.timestamp >= $2
            ORDER BY m.timestamp DESC
            LIMIT 1500
            """,
            account_id,
            _to_naive_utc(since_dt),
        )
    else:
        conv_res = await supabase_execute(
            supabase.table("conversations")
            .select("id, client_number, contact_id, contacts(display_name)")
            .eq("account_id", account_id)
            .order("updated_at", desc=True)
            .limit(_SUPABASE_FALLBACK_MAX_CONVERSATIONS)
        )
        conv_map: Dict[str, Dict[str, Any]] = {}
        for c in conv_res.data or []:
            cid = str(c.get("id") or "")
            if not cid:
                continue
            nested = c.get("contacts") or {}
            conv_map[cid] = {
                "client_number": c.get("client_number"),
                "contact_id": c.get("contact_id"),
                "contact_display_name": nested.get("display_name"),
            }
        conv_ids = list(conv_map.keys())
        step = 80
        for i in range(0, len(conv_ids), step):
            chunk = conv_ids[i : i + step]
            res = await supabase_execute(
                supabase.table("messages")
                .select("content_text, timestamp, conversation_id")
                .in_("conversation_id", chunk)
                .eq("direction", "inbound")
                .eq("message_type", "text")
                .gte("timestamp", since_dt.isoformat())
                .order("timestamp", desc=True)
                .limit(400)
            )
            for m in res.data or []:
                cid = str(m.get("conversation_id") or "")
                meta = conv_map.get(cid) or {}
                rows.append(
                    {
                        "content_text": m.get("content_text"),
                        "timestamp": m.get("timestamp"),
                        "conversation_id": cid,
                        "client_number": meta.get("client_number"),
                        "contact_id": meta.get("contact_id"),
                        "contact_display_name": meta.get("contact_display_name"),
                    }
                )
            if len(rows) >= 1500:
                break

    by_contact: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        txt = (r.get("content_text") or "").strip()
        if not txt:
            continue
        score = _score_satisfaction_text(txt)
        if score <= 0:
            continue
        cid = str(r.get("contact_id") or "").strip()
        phone = str(r.get("client_number") or "").strip()
        key = cid or phone
        if not key:
            continue
        label = (r.get("contact_display_name") or phone or "?").strip()
        bucket = by_contact.get(key)
        if not bucket:
            bucket = {
                "contact_id": cid or None,
                "contact_name": label,
                "client_number": phone or None,
                "satisfaction_score": 0,
                "signals_count": 0,
                "conversation_ids": set(),
                "evidence_snippets": [],
                "last_positive_at": None,
            }
            by_contact[key] = bucket
        bucket["satisfaction_score"] += score
        bucket["signals_count"] += 1
        conv_id = str(r.get("conversation_id") or "")
        if conv_id:
            bucket["conversation_ids"].add(conv_id)
        snippet = txt[:220]
        if snippet and len(bucket["evidence_snippets"]) < 3:
            bucket["evidence_snippets"].append(snippet)
        ts = r.get("timestamp")
        ts_iso = ts.isoformat() if isinstance(ts, datetime) else str(ts or "")
        if ts_iso and (
            bucket["last_positive_at"] is None or ts_iso > str(bucket["last_positive_at"])
        ):
            bucket["last_positive_at"] = ts_iso

    ranked = sorted(
        by_contact.values(),
        key=lambda x: (int(x.get("satisfaction_score") or 0), str(x.get("last_positive_at") or "")),
        reverse=True,
    )[:lim]

    contacts = [
        {
            "contact_id": c.get("contact_id"),
            "contact_name": c.get("contact_name"),
            "client_number": c.get("client_number"),
            "satisfaction_score": c.get("satisfaction_score"),
            "signals_count": c.get("signals_count"),
            "conversation_count": len(c.get("conversation_ids") or []),
            "last_positive_at": c.get("last_positive_at"),
            "evidence_snippets": c.get("evidence_snippets") or [],
        }
        for c in ranked
    ]
    return {
        "days": days_i,
        "total": len(contacts),
        "contacts": contacts,
        "method": "heuristic_sentiment_signals_v1",
    }


async def find_satisfied_contacts_all_accessible_accounts(
    user: "CurrentUser",
    *,
    days: int = 30,
    limit_per_account: int = 8,
    max_accounts: Optional[int] = None,
    per_account_timeout_s: float = _AXELIA_MULTI_SUMMARY_TIMEOUT_S,
) -> Dict[str, Any]:
    """Version multi-comptes de `find_satisfied_contacts_for_account`."""
    cap_acc = max_accounts if max_accounts is not None else _AXELIA_MULTI_MAX_ACCOUNTS
    lim_pa = max(1, min(int(limit_per_account), 20))
    rows = await list_accessible_account_rows_for_inbox(user)
    selected = rows[:cap_acc]

    accounts_out: List[Dict[str, Any]] = []
    merged: List[Dict[str, Any]] = []
    for row in selected:
        aid = str(row.get("id") or "")
        if not aid or not user.permissions.has(PermissionCodes.CONVERSATIONS_VIEW, aid):
            continue
        try:
            part = await asyncio.wait_for(
                find_satisfied_contacts_for_account(aid, days=days, limit=lim_pa),
                timeout=per_account_timeout_s,
            )
        except asyncio.TimeoutError:
            part = {"error": "délai dépassé", "contacts": [], "total": 0, "days": days}

        scoped_contacts = []
        for c in part.get("contacts") or []:
            scoped = {
                **c,
                "account_id": aid,
                "account_name": row.get("name") or "-",
                "account_phone": row.get("phone_number") or "-",
            }
            scoped_contacts.append(scoped)
            merged.append(scoped)
        accounts_out.append(
            {
                "account_id": aid,
                "account_name": row.get("name") or "-",
                "account_phone": row.get("phone_number") or "-",
                "total": len(scoped_contacts),
                "contacts": scoped_contacts,
                "error": part.get("error"),
            }
        )

    merged_sorted = sorted(
        merged,
        key=lambda x: (int(x.get("satisfaction_score") or 0), str(x.get("last_positive_at") or "")),
        reverse=True,
    )
    return {
        "account_scope": "all_accessible",
        "days": max(1, min(int(days), 120)),
        "accounts": accounts_out,
        "contacts": merged_sorted,
        "total": len(merged_sorted),
        "accounts_total_in_scope": len(rows),
        "accounts_iterated": len(selected),
        "accounts_capped": len(rows) > cap_acc,
        "method": "heuristic_sentiment_signals_v1",
    }


async def summarize_contact_inbox_all_accessible_accounts(
    user: "CurrentUser",
    contact_query: str,
    *,
    max_threads: int = 8,
    max_messages_per_thread: int = 35,
    max_accounts: Optional[int] = None,
    per_account_timeout_s: float = _AXELIA_MULTI_SUMMARY_TIMEOUT_S,
) -> Dict[str, Any]:
    """
    Résume les fils d’un contact sur **toutes** les lignes WABA accessibles (conversations.view),
    en réutilisant les plafonds du chemin mono-compte par ligne.
    """
    q = _sanitize_ilike_fragment(contact_query)
    if len(q) < 2:
        return {
            "error": "Requête contact trop courte (2 caractères minimum).",
            "account_scope": "all_accessible",
            "accounts": [],
        }

    cap_threads = max(1, min(max_threads, 12))
    cap_msgs = max(5, min(max_messages_per_thread, 60))
    cap_acc = max_accounts if max_accounts is not None else _AXELIA_MULTI_MAX_ACCOUNTS

    rows = await list_accessible_account_rows_for_inbox(user)
    selected = rows[:cap_acc]
    out: List[Dict[str, Any]] = []
    for row in selected:
        aid = str(row.get("id") or "")
        if not aid:
            continue
        if not user.permissions.has(PermissionCodes.CONVERSATIONS_VIEW, aid):
            continue
        try:
            part = await asyncio.wait_for(
                summarize_contact_inbox_for_account(
                    aid,
                    contact_query,
                    max_threads=cap_threads,
                    max_messages_per_thread=cap_msgs,
                ),
                timeout=per_account_timeout_s,
            )
        except asyncio.TimeoutError:
            part = {
                "error": f"délai dépassé ({per_account_timeout_s}s)",
                "bundles": [],
                "contact_query": contact_query,
            }

        out.append(
            {
                "account_id": aid,
                "account_name": row.get("name") or "-",
                "account_phone": row.get("phone_number") or "-",
                "inbox_summary": part,
            }
        )

    return {
        "account_scope": "all_accessible",
        "contact_query": contact_query,
        "max_threads": cap_threads,
        "max_messages_per_thread": cap_msgs,
        "accounts": out,
        "accounts_total_in_scope": len(rows),
        "accounts_iterated": len(selected),
        "accounts_capped": len(rows) > cap_acc,
    }


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


async def summarize_contact_inbox_for_account(
    account_id: str,
    contact_query: str,
    *,
    max_threads: int = 8,
    max_messages_per_thread: int = 35,
) -> Dict[str, Any]:
    """
    Agrège les derniers messages de plusieurs conversations inbox correspondant à un contact
    (nom affiché, numéro WhatsApp ou client_number).
    """
    q = _sanitize_ilike_fragment(contact_query)
    if len(q) < 2:
        return {"error": "Requête contact trop courte (2 caractères minimum).", "bundles": []}

    cap_threads = max(1, min(max_threads, 12))
    cap_msgs = max(5, min(max_messages_per_thread, 60))
    pat = f"%{q}%"

    pool = get_pool()
    thread_rows: List[Dict[str, Any]] = []

    if pool:
        thread_rows = await fetch_all(
            """
            SELECT c.id AS conversation_id,
                   co.id AS contact_id,
                   COALESCE(NULLIF(TRIM(co.display_name), ''), c.client_number, '') AS contact_label,
                   c.client_number,
                   c.updated_at AS last_ts
            FROM conversations c
            LEFT JOIN contacts co ON co.id = c.contact_id
            WHERE c.account_id = $1::uuid
              AND (
                co.display_name ILIKE $2
                OR co.whatsapp_number ILIKE $2
                OR c.client_number ILIKE $2
              )
            ORDER BY c.updated_at DESC NULLS LAST
            LIMIT $3
            """,
            account_id,
            pat,
            cap_threads,
        )
    else:
        res = await supabase_execute(
            supabase.table("conversations")
            .select(
                "id, updated_at, client_number, contact_id, contacts(display_name, whatsapp_number)"
            )
            .eq("account_id", account_id)
            .order("updated_at", desc=True)
            .limit(500)
        )
        needle = q.lower()
        for row in res.data or []:
            nested = row.get("contacts") or {}
            dn = str(nested.get("display_name") or "").lower()
            wn = str(nested.get("whatsapp_number") or "").lower()
            cn = str(row.get("client_number") or "").lower()
            if needle in dn or needle in wn or needle in cn:
                thread_rows.append(
                    {
                        "conversation_id": row.get("id"),
                        "contact_id": row.get("contact_id"),
                        "contact_label": nested.get("display_name") or row.get("client_number"),
                        "client_number": row.get("client_number"),
                        "last_ts": row.get("updated_at"),
                    }
                )
            if len(thread_rows) >= cap_threads:
                break

    if not thread_rows:
        return {
            "contact_query": contact_query,
            "note": "Aucune conversation trouvée pour ce libellé sur ce compte.",
            "bundles": [],
        }

    bundles: List[Dict[str, Any]] = []
    for tr in thread_rows:
        cid_raw = tr.get("conversation_id")
        if not cid_raw:
            continue
        cid = str(cid_raw)
        digest = await get_conversation_digest_for_account(
            account_id, cid, max_messages=cap_msgs
        )
        if digest.get("error"):
            continue
        bundles.append(
            {
                "conversation_id": cid,
                "contact_label": tr.get("contact_label") or digest.get("contact_hint"),
                "client_number": tr.get("client_number"),
                "message_count": digest.get("message_count"),
                "transcript_recent": digest.get("transcript_recent"),
            }
        )

    return {
        "contact_query": contact_query,
        "threads_matched": len(thread_rows),
        "bundles": bundles,
    }
