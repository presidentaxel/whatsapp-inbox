from __future__ import annotations

import time
from typing import Any, Dict, Optional, Sequence

from app.core.config import settings
from app.core.db import supabase, supabase_execute
from app.core.pg import execute as pg_execute, fetch_all, fetch_one, get_pool

DEFAULT_ACCOUNT_SLUG = "default-env-account"
_CACHE_TTL_SECONDS = 60
_account_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
_phone_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
_verify_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
_default_account_synced = False
_default_account_record: Optional[Dict[str, Any]] = None


def _sanitize_account(record: Dict[str, Any]) -> Dict[str, Any]:
    """Nettoie les données du compte pour l'API (masque les tokens sensibles)"""
    return {
        "id": record.get("id"),
        "name": record.get("name"),
        "slug": record.get("slug"),
        "phone_number": record.get("phone_number"),
        "phone_number_id": record.get("phone_number_id"),
        "google_drive_enabled": record.get("google_drive_enabled", False),
        "google_drive_folder_id": record.get("google_drive_folder_id"),
        "google_drive_connected": bool(record.get("google_drive_access_token")),
    }


def _cache_get(cache: Dict[str, tuple[float, Dict[str, Any]]], key: str) -> Optional[Dict[str, Any]]:
    entry = cache.get(key)
    if not entry:
        return None
    expires_at, payload = entry
    if expires_at < time.time():
        cache.pop(key, None)
        return None
    return payload


def _cache_set(cache: Dict[str, tuple[float, Dict[str, Any]]], key: str, value: Dict[str, Any]):
    cache[key] = (time.time() + _CACHE_TTL_SECONDS, value)


def _cache_pop(cache: Dict[str, tuple[float, Dict[str, Any]]], key: str):
    cache.pop(key, None)


def invalidate_account_cache(account_id: str):
    """
    Invalide le cache d'un compte pour forcer le rechargement depuis la DB.
    Utile après des modifications comme la connexion Google Drive.
    """
    _cache_pop(_account_cache, account_id)
    # Invalider aussi les caches par phone_number_id et verify_token si on a le compte
    # (on ne peut pas les invalider directement sans connaître les valeurs)
    # Nettoyer aussi les caches dérivés
    for cache in (_phone_cache, _verify_cache):
        keys_to_purge = [key for key, (_, record) in cache.items() if record.get("id") == account_id]
        for key in keys_to_purge:
            cache.pop(key, None)


async def get_all_accounts(account_ids: Optional[Sequence[str]] = None) -> Sequence[Dict[str, Any]]:
    await ensure_default_account()
    if get_pool():
        if account_ids is not None and not account_ids:
            return []
        if account_ids is not None:
            rows = await fetch_all(
                """
                SELECT id, name, slug, phone_number, phone_number_id, is_active, google_drive_enabled,
                       google_drive_folder_id, google_drive_access_token, google_drive_refresh_token, google_drive_token_expiry
                FROM whatsapp_accounts
                WHERE is_active = true AND id = ANY($1::uuid[])
                ORDER BY name
                """,
                list(account_ids),
            )
        else:
            rows = await fetch_all(
                """
                SELECT id, name, slug, phone_number, phone_number_id, is_active, google_drive_enabled,
                       google_drive_folder_id, google_drive_access_token, google_drive_refresh_token, google_drive_token_expiry
                FROM whatsapp_accounts
                WHERE is_active = true
                ORDER BY name
                """
            )
        return rows
    query = (
        supabase.table("whatsapp_accounts")
        .select("id,name,slug,phone_number,phone_number_id,is_active,google_drive_enabled,google_drive_folder_id,google_drive_access_token,google_drive_refresh_token,google_drive_token_expiry")
        .eq("is_active", True)
        .order("name")
    )
    if account_ids is not None:
        if not account_ids:
            return []
        query = query.in_("id", list(account_ids))
    res = await supabase_execute(query)
    return res.data or []


async def get_account_by_id(account_id: str) -> Optional[Dict[str, Any]]:
    if not account_id:
        return None

    cached = _cache_get(_account_cache, account_id)
    if cached:
        return cached

    if get_pool():
        row = await fetch_one(
            "SELECT * FROM whatsapp_accounts WHERE id = $1::uuid LIMIT 1",
            account_id,
        )
        if row:
            record = dict(row)
            _cache_set(_account_cache, account_id, record)
            if record.get("phone_number_id"):
                _cache_set(_phone_cache, record["phone_number_id"], record)
            if record.get("verify_token"):
                _cache_set(_verify_cache, record["verify_token"], record)
            return record
        _cache_pop(_account_cache, account_id)
        return None

    res = await supabase_execute(
        supabase.table("whatsapp_accounts").select("*").eq("id", account_id).limit(1)
    )
    if res.data:
        record = res.data[0]
        _cache_set(_account_cache, account_id, record)
        if record.get("phone_number_id"):
            _cache_set(_phone_cache, record["phone_number_id"], record)
        if record.get("verify_token"):
            _cache_set(_verify_cache, record["verify_token"], record)
        return record

    _cache_pop(_account_cache, account_id)
    return None


async def get_account_by_verify_token(token: str | None) -> Optional[Dict[str, Any]]:
    if not token:
        return None

    cached = _cache_get(_verify_cache, token)
    if cached:
        return cached

    await ensure_default_account()
    if get_pool():
        row = await fetch_one(
            "SELECT * FROM whatsapp_accounts WHERE verify_token = $1 LIMIT 1",
            token,
        )
        if row:
            record = dict(row)
            _cache_set(_verify_cache, token, record)
            return record
        _cache_pop(_verify_cache, token)
        return None
    res = await supabase_execute(
        supabase.table("whatsapp_accounts").select("*").eq("verify_token", token).limit(1)
    )
    if res.data:
        record = res.data[0]
        _cache_set(_verify_cache, token, record)
        return record
    _cache_pop(_verify_cache, token)
    return None


async def get_account_by_phone_number_id(phone_number_id: str | None) -> Optional[Dict[str, Any]]:
    if not phone_number_id:
        return None

    cached = _cache_get(_phone_cache, phone_number_id)
    if cached:
        return cached

    await ensure_default_account()
    if get_pool():
        row = await fetch_one(
            "SELECT * FROM whatsapp_accounts WHERE phone_number_id = $1 LIMIT 1",
            phone_number_id,
        )
        if row:
            record = dict(row)
            _cache_set(_phone_cache, phone_number_id, record)
            _cache_set(_account_cache, record["id"], record)
            return record
        _cache_pop(_phone_cache, phone_number_id)
        return None
    res = await supabase_execute(
        supabase.table("whatsapp_accounts")
        .select("*")
        .eq("phone_number_id", phone_number_id)
        .limit(1)
    )
    if res.data:
        record = res.data[0]
        _cache_set(_phone_cache, phone_number_id, record)
        _cache_set(_account_cache, record["id"], record)
        return record
    _cache_pop(_phone_cache, phone_number_id)
    return None


async def ensure_default_account() -> Optional[Dict[str, Any]]:
    """
    If legacy env vars are set, mirror them inside whatsapp_accounts
    so the rest of the system can treat everything uniformly.
    """
    global _default_account_synced, _default_account_record

    if not (
        settings.WHATSAPP_PHONE_ID
        and settings.WHATSAPP_TOKEN
        and settings.WHATSAPP_VERIFY_TOKEN
    ):
        return None

    if _default_account_synced and _default_account_record:
        return _default_account_record

    record = None
    if get_pool():
        record = await fetch_one(
            "SELECT * FROM whatsapp_accounts WHERE slug = $1 LIMIT 1",
            DEFAULT_ACCOUNT_SLUG,
        )
        if record:
            record = dict(record)
    else:
        existing = await supabase_execute(
            supabase.table("whatsapp_accounts").select("*").eq("slug", DEFAULT_ACCOUNT_SLUG).limit(1)
        )
        if existing.data:
            record = existing.data[0]

    if record:
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

        if updates and get_pool():
            # Build dynamic UPDATE
            set_parts = []
            args = []
            for i, (k, v) in enumerate(updates.items(), 1):
                set_parts.append(f"{k} = ${i}")
                args.append(v)
            args.append(record["id"])
            q = "UPDATE whatsapp_accounts SET " + ", ".join(set_parts) + f" WHERE id = ${len(args)}::uuid"
            await pg_execute(q, *args)
            record.update(updates)
        elif updates:
            await supabase_execute(
                supabase.table("whatsapp_accounts").update(updates).eq("id", record["id"])
            )
            record.update(updates)
        _default_account_synced = True
        _default_account_record = record
        _cache_set(_account_cache, record["id"], record)
        if record.get("phone_number_id"):
            _cache_set(_phone_cache, record["phone_number_id"], record)
        if record.get("verify_token"):
            _cache_set(_verify_cache, record["verify_token"], record)
        return record

    if get_pool():
        row = await fetch_one(
            """
            INSERT INTO whatsapp_accounts (name, slug, phone_number, phone_number_id, access_token, verify_token, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, true)
            RETURNING *
            """,
            "Compte par défaut",
            DEFAULT_ACCOUNT_SLUG,
            settings.WHATSAPP_PHONE_NUMBER,
            settings.WHATSAPP_PHONE_ID,
            settings.WHATSAPP_TOKEN,
            settings.WHATSAPP_VERIFY_TOKEN,
        )
        if row:
            record = dict(row)
            _default_account_synced = True
            _default_account_record = record
            _cache_set(_account_cache, record["id"], record)
            if record.get("phone_number_id"):
                _cache_set(_phone_cache, record["phone_number_id"], record)
            if record.get("verify_token"):
                _cache_set(_verify_cache, record["verify_token"], record)
            return record
        return None
    payload = {
        "name": "Compte par défaut",
        "slug": DEFAULT_ACCOUNT_SLUG,
        "phone_number": settings.WHATSAPP_PHONE_NUMBER,
        "phone_number_id": settings.WHATSAPP_PHONE_ID,
        "access_token": settings.WHATSAPP_TOKEN,
        "verify_token": settings.WHATSAPP_VERIFY_TOKEN,
        "is_active": True,
    }
    inserted = await supabase_execute(supabase.table("whatsapp_accounts").insert(payload))
    if inserted.data:
        record = inserted.data[0]
        _default_account_synced = True
        _default_account_record = record
        _cache_set(_account_cache, record["id"], record)
        if record.get("phone_number_id"):
            _cache_set(_phone_cache, record["phone_number_id"], record)
        if record.get("verify_token"):
            _cache_set(_verify_cache, record["verify_token"], record)
        return record
    return None


async def expose_accounts_public() -> Sequence[Dict[str, Any]]:
    """Utility used by API routes to avoid leaking credentials."""
    accounts = await get_all_accounts()
    return [_sanitize_account(acc) for acc in accounts]


async def expose_accounts_limited(account_ids: Optional[Sequence[str]]) -> Sequence[Dict[str, Any]]:
    if account_ids is None:
        return await expose_accounts_public()
    accounts = await get_all_accounts(account_ids)
    return [_sanitize_account(acc) for acc in accounts]


async def create_account(payload: Dict[str, Any]) -> Dict[str, Any]:
    await ensure_default_account()
    if get_pool():
        if not payload:
            raise ValueError("Empty payload")
        cols = list(payload.keys())
        vals = [payload[k] for k in cols]
        placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
        col_list = ", ".join(cols)
        row = await fetch_one(
            f"INSERT INTO whatsapp_accounts ({col_list}) VALUES ({placeholders}) RETURNING *",
            *vals,
        )
        if not row:
            raise ValueError("Failed to create account")
        record = dict(row)
    else:
        result = await supabase_execute(supabase.table("whatsapp_accounts").insert(payload))
        record = result.data[0]
    _cache_set(_account_cache, record["id"], record)
    if record.get("phone_number_id"):
        _cache_set(_phone_cache, record["phone_number_id"], record)
    if record.get("verify_token"):
        _cache_set(_verify_cache, record["verify_token"], record)
    return _sanitize_account(record)


async def update_account(account_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Met à jour un compte WhatsApp"""
    if get_pool() and updates:
        set_parts = []
        args = []
        for i, (k, v) in enumerate(updates.items(), 1):
            set_parts.append(f"{k} = ${i}")
            args.append(v)
        args.append(account_id)
        await pg_execute(
            "UPDATE whatsapp_accounts SET " + ", ".join(set_parts) + f" WHERE id = ${len(args)}::uuid",
            *args,
        )
    elif not get_pool():
        await supabase_execute(
            supabase.table("whatsapp_accounts").update(updates).eq("id", account_id)
        )
    _cache_pop(_account_cache, account_id)
    for cache in (_phone_cache, _verify_cache):
        keys_to_purge = [key for key, (_, record) in cache.items() if record.get("id") == account_id]
        for key in keys_to_purge:
            cache.pop(key, None)
    return await get_account_by_id(account_id)


async def delete_account(account_id: str) -> bool:
    if get_pool():
        await pg_execute("DELETE FROM whatsapp_accounts WHERE id = $1::uuid", account_id)
    else:
        await supabase_execute(supabase.table("whatsapp_accounts").delete().eq("id", account_id))
    _cache_pop(_account_cache, account_id)
    for cache in (_phone_cache, _verify_cache):
        keys_to_purge = [key for key, (_, record) in cache.items() if record.get("id") == account_id]
        for key in keys_to_purge:
            cache.pop(key, None)
    return True
