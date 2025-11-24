from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from app.core.config import settings
from app.core.db import supabase

DEFAULT_ACCOUNT_SLUG = "default-env-account"


def _sanitize_account(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": record.get("id"),
        "name": record.get("name"),
        "slug": record.get("slug"),
        "phone_number": record.get("phone_number"),
        "phone_number_id": record.get("phone_number_id"),
    }


def get_all_accounts(account_ids: Optional[Sequence[str]] = None) -> Sequence[Dict[str, Any]]:
    ensure_default_account()
    query = (
        supabase.table("whatsapp_accounts")
        .select("id,name,slug,phone_number,phone_number_id,is_active")
        .eq("is_active", True)
        .order("name")
    )
    if account_ids is not None:
        if not account_ids:
            return []
        query = query.in_("id", list(account_ids))
    res = query.execute()
    return res.data


def get_account_by_id(account_id: str) -> Optional[Dict[str, Any]]:
    if not account_id:
        return None

    res = (
        supabase.table("whatsapp_accounts")
        .select("*")
        .eq("id", account_id)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]
    return None


def get_account_by_verify_token(token: str | None) -> Optional[Dict[str, Any]]:
    if not token:
        return None

    ensure_default_account()
    res = (
        supabase.table("whatsapp_accounts")
        .select("*")
        .eq("verify_token", token)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]
    return None


def get_account_by_phone_number_id(phone_number_id: str | None) -> Optional[Dict[str, Any]]:
    if not phone_number_id:
        return None

    ensure_default_account()
    res = (
        supabase.table("whatsapp_accounts")
        .select("*")
        .eq("phone_number_id", phone_number_id)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]
    return None


def ensure_default_account() -> Optional[Dict[str, Any]]:
    """
    If legacy env vars are set, mirror them inside whatsapp_accounts
    so the rest of the system can treat everything uniformly.
    """
    if not (
        settings.WHATSAPP_PHONE_ID
        and settings.WHATSAPP_TOKEN
        and settings.WHATSAPP_VERIFY_TOKEN
    ):
        return None

    existing = (
        supabase.table("whatsapp_accounts")
        .select("*")
        .eq("slug", DEFAULT_ACCOUNT_SLUG)
        .limit(1)
        .execute()
    )

    if existing.data:
        record = existing.data[0]
        updates: Dict[str, Any] = {}
        if record.get("phone_number_id") != settings.WHATSAPP_PHONE_ID:
            updates["phone_number_id"] = settings.WHATSAPP_PHONE_ID
        if record.get("access_token") != settings.WHATSAPP_TOKEN:
            updates["access_token"] = settings.WHATSAPP_TOKEN
        if record.get("verify_token") != settings.WHATSAPP_VERIFY_TOKEN:
            updates["verify_token"] = settings.WHATSAPP_VERIFY_TOKEN
        if (
            settings.WHATSAPP_PHONE_NUMBER
            and record.get("phone_number") != settings.WHATSAPP_PHONE_NUMBER
        ):
            updates["phone_number"] = settings.WHATSAPP_PHONE_NUMBER

        if updates:
            supabase.table("whatsapp_accounts").update(updates).eq("id", record["id"]).execute()
            record.update(updates)
        return record

    payload = {
        "name": "Compte par défaut",
        "slug": DEFAULT_ACCOUNT_SLUG,
        "phone_number": settings.WHATSAPP_PHONE_NUMBER,
        "phone_number_id": settings.WHATSAPP_PHONE_ID,
        "access_token": settings.WHATSAPP_TOKEN,
        "verify_token": settings.WHATSAPP_VERIFY_TOKEN,
        "is_active": True,
    }
    inserted = supabase.table("whatsapp_accounts").insert(payload).execute()
    if inserted.data:
        return inserted.data[0]
    return None


def expose_accounts_public() -> Sequence[Dict[str, Any]]:
    """Utility used by API routes to avoid leaking credentials."""
    return [_sanitize_account(acc) for acc in get_all_accounts()]


def expose_accounts_limited(account_ids: Optional[Sequence[str]]) -> Sequence[Dict[str, Any]]:
    if account_ids is None:
        return expose_accounts_public()
    return [_sanitize_account(acc) for acc in get_all_accounts(account_ids)]


def create_account(payload: Dict[str, Any]) -> Dict[str, Any]:
    ensure_default_account()
    result = supabase.table("whatsapp_accounts").insert(payload).execute()
    return _sanitize_account(result.data[0])


def delete_account(account_id: str) -> bool:
    supabase.table("whatsapp_accounts").delete().eq("id", account_id).execute()
    return True


