from __future__ import annotations

from typing import Any, Dict, List, Sequence
import logging

from fastapi import HTTPException

from app.core.db import supabase, supabase_execute
from app.core.cache import invalidate_cache_pattern
from app.core.pg import get_pool, fetch_all, fetch_one, execute

logger = logging.getLogger(__name__)


async def list_permissions() -> Sequence[Dict[str, Any]]:
    pool = get_pool()
    if pool:
        rows = await fetch_all("SELECT * FROM app_permissions ORDER BY code")
        return [dict(r) for r in rows]
    res = await supabase_execute(
        supabase.table("app_permissions").select("*").order("code")
    )
    return res.data


async def list_roles() -> Sequence[Dict[str, Any]]:
    pool = get_pool()
    if pool:
        roles = [dict(r) for r in await fetch_all("SELECT * FROM app_roles ORDER BY name")]
        if not roles:
            return []
        role_ids = [role["id"] for role in roles]
        placeholders = ", ".join(f"${i+1}::uuid" for i in range(len(role_ids)))
        perms = await fetch_all(
            f"SELECT role_id, permission_code FROM role_permissions WHERE role_id IN ({placeholders})",
            *role_ids,
        )
        perms_by_role: Dict[str, List[str]] = {}
        for item in perms:
            perms_by_role.setdefault(str(item["role_id"]), []).append(item["permission_code"])
        for role in roles:
            role["permissions"] = sorted(perms_by_role.get(str(role["id"]), []))
        return roles

    roles_res = await supabase_execute(
        supabase.table("app_roles").select("*").order("name")
    )
    roles = roles_res.data
    if not roles:
        return []

    role_ids = [role["id"] for role in roles]
    perms_res = await supabase_execute(
        supabase.table("role_permissions")
        .select("role_id, permission_code")
        .in_("role_id", role_ids)
    )
    perms = perms_res.data
    perms_by_role: Dict[str, List[str]] = {}
    for item in perms:
        perms_by_role.setdefault(item["role_id"], []).append(item["permission_code"])

    for role in roles:
        role["permissions"] = sorted(perms_by_role.get(role["id"], []))
    return roles


async def create_role(payload: Dict[str, Any]) -> Dict[str, Any]:
    permissions = payload.pop("permissions", [])
    res = await supabase_execute(
        supabase.table("app_roles").insert(payload).select()
    )
    role = res.data[0]
    if permissions:
        await supabase_execute(
            supabase.table("role_permissions").upsert(
                [{"role_id": role["id"], "permission_code": perm} for perm in permissions]
            )
        )
    role["permissions"] = permissions
    return role


async def update_role(role_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    permissions = payload.pop("permissions", None)
    await supabase_execute(
        supabase.table("app_roles").update(payload).eq("id", role_id)
    )
    if permissions is not None:
        await supabase_execute(
            supabase.table("role_permissions").delete().eq("role_id", role_id)
        )
        if permissions:
            await supabase_execute(
                supabase.table("role_permissions").upsert(
                    [{"role_id": role_id, "permission_code": perm} for perm in permissions]
                )
            )
    role_res = await supabase_execute(
        supabase.table("app_roles").select("*").eq("id", role_id).limit(1)
    )
    role = role_res.data[0]
    if permissions is None:
        perms_res = await supabase_execute(
            supabase.table("role_permissions")
            .select("permission_code")
            .eq("role_id", role_id)
        )
        role["permissions"] = sorted([p["permission_code"] for p in perms_res.data])
    else:
        role["permissions"] = permissions
    return role


async def delete_role(role_id: str):
    role_res = await supabase_execute(
        supabase.table("app_roles").select("slug").eq("id", role_id).limit(1)
    )
    if not role_res.data:
        raise HTTPException(status_code=404, detail="role_not_found")
    if role_res.data[0]["slug"] == "admin":
        raise HTTPException(status_code=400, detail="cannot_delete_admin_role")
    await supabase_execute(
        supabase.table("app_roles").delete().eq("id", role_id)
    )


async def list_app_users() -> Sequence[Dict[str, Any]]:
    pool = get_pool()
    if pool:
        users = [dict(r) for r in await fetch_all("SELECT * FROM app_users ORDER BY created_at")]
        if not users:
            return []
        user_ids = [u["user_id"] for u in users]
        placeholders = ", ".join(f"${i+1}" for i in range(len(user_ids)))
        role_rows = [dict(r) for r in await fetch_all(
            f"SELECT id, user_id, role_id, account_id FROM app_user_roles WHERE user_id IN ({placeholders})",
            *user_ids,
        )]
        role_ids = list({row["role_id"] for row in role_rows})
        role_map = {}
        if role_ids:
            rp = ", ".join(f"${i+1}::uuid" for i in range(len(role_ids)))
            roles = [dict(r) for r in await fetch_all(
                f"SELECT id, slug, name FROM app_roles WHERE id IN ({rp})", *role_ids
            )]
            role_map = {str(r["id"]): r for r in roles}
        overrides = [dict(r) for r in await fetch_all(
            f"SELECT id, user_id, permission_code, account_id, is_allowed FROM app_user_overrides WHERE user_id IN ({placeholders})",
            *user_ids,
        )]
    else:
        users_res = await supabase_execute(
            supabase.table("app_users").select("*").order("created_at")
        )
        users = users_res.data
        if not users:
            return []
        user_ids = [u["user_id"] for u in users]
        role_rows_res = await supabase_execute(
            supabase.table("app_user_roles")
            .select("id, user_id, role_id, account_id")
            .in_("user_id", user_ids)
        )
        role_rows = role_rows_res.data
        role_ids = list({row["role_id"] for row in role_rows})
        role_map = {}
        if role_ids:
            roles_res = await supabase_execute(
                supabase.table("app_roles").select("id, slug, name").in_("id", role_ids)
            )
            role_map = {r["id"]: r for r in roles_res.data}
        overrides_res = await supabase_execute(
            supabase.table("app_user_overrides")
            .select("id, user_id, permission_code, account_id, is_allowed")
            .in_("user_id", user_ids)
        )
        overrides = overrides_res.data

    roles_by_user: Dict[str, List[Dict[str, Any]]] = {}
    for row in role_rows:
        role_info = role_map.get(str(row["role_id"]), {})
        roles_by_user.setdefault(row["user_id"], []).append(
            {
                "id": row["id"],
                "role_id": row["role_id"],
                "role_slug": role_info.get("slug"),
                "role_name": role_info.get("name"),
                "account_id": row.get("account_id"),
            }
        )

    overrides_by_user: Dict[str, List[Dict[str, Any]]] = {}
    for item in overrides:
        overrides_by_user.setdefault(item["user_id"], []).append(item)

    for user in users:
        user["roles"] = roles_by_user.get(user["user_id"], [])
        user["overrides"] = overrides_by_user.get(user["user_id"], [])

    return users


async def set_user_status(user_id: str, is_active: bool):
    await supabase_execute(
        supabase.table("app_users").update({"is_active": is_active}).eq("user_id", user_id)
    )


async def set_user_roles(user_id: str, assignments: Sequence[Dict[str, Any]]):
    await supabase_execute(
        supabase.table("app_user_roles").delete().eq("user_id", user_id)
    )
    if assignments:
        payload = [
            {
                "user_id": user_id,
                "role_id": item["role_id"],
                "account_id": item.get("account_id"),
            }
            for item in assignments
        ]
        await supabase_execute(
            supabase.table("app_user_roles").upsert(payload)
        )
    await invalidate_cache_pattern("auth_user:*")
    logger.info(f"Cache invalidated for all users after permission change for user {user_id}")


async def set_user_overrides(user_id: str, overrides: Sequence[Dict[str, Any]]):
    await supabase_execute(
        supabase.table("app_user_overrides").delete().eq("user_id", user_id)
    )
    if overrides:
        payload = [
            {
                "user_id": user_id,
                "permission_code": item["permission_code"],
                "account_id": item.get("account_id"),
                "is_allowed": bool(item.get("is_allowed", True)),
            }
            for item in overrides
        ]
        await supabase_execute(
            supabase.table("app_user_overrides").upsert(payload)
        )


async def list_users_with_access() -> Sequence[Dict[str, Any]]:
    """Liste tous les utilisateurs avec leurs rôles et accès par compte"""
    pool = get_pool()
    if pool:
        users = [dict(r) for r in await fetch_all("SELECT * FROM app_users ORDER BY created_at")]
    else:
        users_res = await supabase_execute(
            supabase.table("app_users").select("*").order("created_at")
        )
        users = users_res.data
    if not users:
        return []

    user_ids = [u["user_id"] for u in users]

    if pool:
        placeholders = ", ".join(f"${i+1}" for i in range(len(user_ids)))
        role_rows = [dict(r) for r in await fetch_all(
            f"SELECT id, user_id, role_id, account_id FROM app_user_roles WHERE user_id IN ({placeholders})",
            *user_ids,
        )]
        role_ids = list({row["role_id"] for row in role_rows})
        role_map = {}
        if role_ids:
            rp = ", ".join(f"${i+1}::uuid" for i in range(len(role_ids)))
            roles = [dict(r) for r in await fetch_all(
                f"SELECT id, slug, name FROM app_roles WHERE id IN ({rp})", *role_ids
            )]
            role_map = {str(r["id"]): r for r in roles}
        access_rows = [dict(r) for r in await fetch_all(
            f"SELECT id, user_id, account_id, access_level FROM user_account_access WHERE user_id IN ({placeholders})",
            *user_ids,
        )]
    else:
        role_rows_res = await supabase_execute(
            supabase.table("app_user_roles")
            .select("id, user_id, role_id, account_id")
            .in_("user_id", user_ids)
        )
        role_rows = role_rows_res.data
        role_ids = list({row["role_id"] for row in role_rows})
        role_map = {}
        if role_ids:
            roles_res = await supabase_execute(
                supabase.table("app_roles").select("id, slug, name").in_("id", role_ids)
            )
            role_map = {r["id"]: r for r in roles_res.data}
        access_res = await supabase_execute(
            supabase.table("user_account_access")
            .select("id, user_id, account_id, access_level")
            .in_("user_id", user_ids)
        )
        access_rows = access_res.data

    role_priority = {"admin": 3, "dev": 2, "manager": 1}
    roles_by_user: Dict[str, Dict[str, Any]] = {}
    for row in role_rows:
        role_info = role_map.get(str(row["role_id"]), {})
        uid = row["user_id"]
        role_slug = role_info.get("slug")
        current_priority = role_priority.get(role_slug, 0)

        if uid not in roles_by_user:
            roles_by_user[uid] = {
                "role_id": row["role_id"],
                "role_slug": role_slug,
                "role_name": role_info.get("name"),
            }
        else:
            existing_slug = roles_by_user[uid].get("role_slug")
            existing_priority = role_priority.get(existing_slug, 0)
            if current_priority > existing_priority:
                roles_by_user[uid] = {
                    "role_id": row["role_id"],
                    "role_slug": role_slug,
                    "role_name": role_info.get("name"),
                }

    access_by_user: Dict[str, List[Dict[str, Any]]] = {}
    for row in access_rows:
        access_by_user.setdefault(row["user_id"], []).append({
            "account_id": row["account_id"],
            "access_level": row["access_level"],
        })

    for user in users:
        user["role_slug"] = roles_by_user.get(user["user_id"], {}).get("role_slug")
        user["role_name"] = roles_by_user.get(user["user_id"], {}).get("role_name")
        user["account_access"] = access_by_user.get(user["user_id"], [])

    return users


async def set_user_account_access(user_id: str, account_id: str, access_level: str):
    """Définit l'accès d'un utilisateur à un compte WhatsApp"""
    if access_level not in ["full", "lecture", "aucun"]:
        raise HTTPException(status_code=400, detail="invalid_access_level")

    await supabase_execute(
        supabase.table("user_account_access").upsert(
            {
                "user_id": user_id,
                "account_id": account_id,
                "access_level": access_level,
            },
            on_conflict="user_id,account_id",
        )
    )

    await invalidate_cache_pattern("auth_user:*")
    logger.info(f"Cache invalidated for all users after access change for user {user_id}")
