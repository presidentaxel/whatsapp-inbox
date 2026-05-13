import re
from typing import Optional

from app.core.db import supabase, supabase_execute
from app.core.pg import fetch_all, fetch_one, get_pool

_SELECT = "id, whatsapp_number, display_name, profile_picture_url, whatsapp_name, whatsapp_info_fetched_at, created_at"


def _search_param(search: Optional[str]) -> Optional[str]:
    s = (search or "").strip()
    return s[:200] if s else None


async def list_contacts(limit: int = 200, offset: int = 0, search: Optional[str] = None):
    q = _search_param(search)
    if get_pool():
        if q:
            rows = await fetch_all(
                f"""
                SELECT {_SELECT}
                FROM contacts
                WHERE (
                  regexp_replace(
                    lower(
                      coalesce(display_name, '')
                      || coalesce(whatsapp_name, '')
                      || coalesce(whatsapp_number, '')
                    ),
                    '\\s', '', 'g'
                  ) LIKE '%' || regexp_replace(lower(trim($3::text)), '\\s', '', 'g') || '%'
                  OR (
                    length(regexp_replace(trim($3::text), '\\D', '', 'g')) >= 2
                    AND whatsapp_number LIKE '%' || regexp_replace(trim($3::text), '\\D', '', 'g') || '%'
                  )
                )
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
                q,
            )
        else:
            rows = await fetch_all(
                f"""
                SELECT {_SELECT}
                FROM contacts
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
        return [dict(r) for r in rows]

    qb = (
        supabase.table("contacts")
        .select(_SELECT)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if q:
        # PostgREST or_ : pas de virgule dans les valeurs - plusieurs mots → %mot1%mot2%
        safe = re.sub(r"[%]", "", q.replace(",", " "))
        parts = [p for p in safe.split() if p]
        if len(parts) > 1:
            pat = "%" + "%".join(parts) + "%"
        else:
            pat = f"%{safe}%"
        d = re.sub(r"\D", "", q)
        if len(d) >= 2:
            dpat = f"%{d}%"
            qb = qb.or_(
                f"display_name.ilike.{pat},whatsapp_name.ilike.{pat},whatsapp_number.ilike.{pat},whatsapp_number.like.{dpat}"
            )
        else:
            qb = qb.or_(f"display_name.ilike.{pat},whatsapp_name.ilike.{pat},whatsapp_number.ilike.{pat}")
    res = await supabase_execute(qb)
    return res.data or []


async def count_contacts() -> int:
    if get_pool():
        row = await fetch_one("SELECT count(*)::int AS cnt FROM contacts")
        return row["cnt"] if row else 0
    res = await supabase_execute(
        supabase.table("contacts").select("id", count="exact")
    )
    return res.count if hasattr(res, "count") and res.count is not None else len(res.data or [])

