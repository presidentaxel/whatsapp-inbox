from __future__ import annotations

from typing import Any, Dict, List, Sequence
import logging

from fastapi import HTTPException

from app.core.db import supabase, supabase_execute
from app.core.cache import invalidate_cache_pattern
from app.core.permissions import PermissionCodes
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
    res = await supabase_execute(supabase.table("app_roles").insert(payload))
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

    def _merge_role_overrides(
        uid: str,
        defaults_by_uid: Dict[str, bool],
        overrides_seq_by_uid: Dict[str, List[bool]],
    ) -> tuple[bool, bool]:
        ov = overrides_seq_by_uid.get(uid, [])
        eff = defaults_by_uid.get(uid, False)
        for flag in ov:
            eff = bool(flag)
        return defaults_by_uid.get(uid, False), eff

    async def _collect_global_perm(
        permission_code: str,
    ) -> tuple[Dict[str, bool], Dict[str, List[bool]]]:
        defaults_by_uid: Dict[str, bool] = {}
        overrides_seq_by_uid: Dict[str, List[bool]] = {}
        for u in users:
            defaults_by_uid[u["user_id"]] = False

        if pool:
            grant_rows = await fetch_all(
                """
                SELECT DISTINCT aur.user_id
                FROM app_user_roles aur
                INNER JOIN role_permissions rp ON rp.role_id = aur.role_id
                WHERE rp.permission_code = $1 AND aur.user_id = ANY($2::uuid[])
                """,
                permission_code,
                user_ids,
            )
            for r in grant_rows:
                defaults_by_uid[r["user_id"]] = True
            ov_rows = await fetch_all(
                """
                SELECT user_id, is_allowed
                FROM app_user_overrides
                WHERE permission_code = $1
                  AND account_id IS NULL
                  AND user_id = ANY($2::uuid[])
                ORDER BY user_id,
                         COALESCE(created_at, '-infinity'::timestamptz),
                         id
                """,
                permission_code,
                user_ids,
            )
            for r in ov_rows:
                uid = r["user_id"]
                overrides_seq_by_uid.setdefault(uid, []).append(bool(r.get("is_allowed")))
        else:
            rp_res = await supabase_execute(
                supabase.table("role_permissions")
                .select("role_id")
                .eq("permission_code", permission_code)
            )
            role_ids_perm = {str(r["role_id"]) for r in (rp_res.data or [])}
            for row in role_rows:
                if str(row["role_id"]) in role_ids_perm:
                    defaults_by_uid[row["user_id"]] = True
            ax_ov_res = await supabase_execute(
                supabase.table("app_user_overrides")
                .select("user_id, is_allowed, created_at, id")
                .eq("permission_code", permission_code)
                .is_("account_id", None)
                .in_("user_id", user_ids)
            )
            ov_rows = ax_ov_res.data or []
            ov_rows.sort(
                key=lambda x: (
                    x["user_id"],
                    x.get("created_at") or "",
                    str(x.get("id") or ""),
                )
            )
            for r in ov_rows:
                uid = r["user_id"]
                overrides_seq_by_uid.setdefault(uid, []).append(bool(r.get("is_allowed")))
        return defaults_by_uid, overrides_seq_by_uid

    ax_def, ax_ov = await _collect_global_perm(PermissionCodes.AXELIA_ACCESS)
    pg_def, pg_ov = await _collect_global_perm(PermissionCodes.PLAYGROUND_ACCESS)

    for user in users:
        uid = user["user_id"]
        user["role_slug"] = roles_by_user.get(uid, {}).get("role_slug")
        user["role_name"] = roles_by_user.get(uid, {}).get("role_name")
        user["account_access"] = access_by_user.get(uid, [])
        role_def, eff = _merge_role_overrides(uid, ax_def, ax_ov)
        user["axelia_access_role_default"] = role_def
        user["axelia_access_effective"] = eff
        pg_role_def, pg_eff = _merge_role_overrides(uid, pg_def, pg_ov)
        user["playground_access_role_default"] = pg_role_def
        user["playground_access_effective"] = pg_eff

    return users


async def user_role_grants_permission(user_id: str, permission_code: str) -> bool:
    """True si au moins un rôle utilisateur attribue la permission globale donnée (hors overrides)."""
    pool = get_pool()
    if pool:
        row = await fetch_one(
            """
            SELECT EXISTS (
              SELECT 1
              FROM app_user_roles aur
              INNER JOIN role_permissions rp ON rp.role_id = aur.role_id
              WHERE aur.user_id = $1::uuid AND rp.permission_code = $2
            ) AS e
            """,
            user_id,
            permission_code,
        )
        return bool(row and row["e"])
    role_rows_res = await supabase_execute(
        supabase.table("app_user_roles").select("role_id").eq("user_id", user_id)
    )
    r_ids = [r["role_id"] for r in (role_rows_res.data or [])]
    if not r_ids:
        return False
    rp_res = await supabase_execute(
        supabase.table("role_permissions")
        .select("role_id")
        .eq("permission_code", permission_code)
        .in_("role_id", r_ids)
    )
    return bool(rp_res.data)


async def user_role_grants_axelia(user_id: str) -> bool:
    """True si au moins un rôle utilisateur attribue axelia.access (hors overrides)."""
    return await user_role_grants_permission(user_id, PermissionCodes.AXELIA_ACCESS)


async def set_user_global_permission_override(user_id: str, permission_code: str, allowed: bool) -> None:
    """Override global (account_id NULL) pour une permission ; supprimé si aligné sur le défaut des rôles."""
    role_grants = await user_role_grants_permission(user_id, permission_code)
    pool = get_pool()
    if pool:
        await execute(
            "DELETE FROM app_user_overrides WHERE user_id = $1::uuid AND permission_code = $2 AND account_id IS NULL",
            user_id,
            permission_code,
        )
        if allowed != role_grants:
            await execute(
                """
                INSERT INTO app_user_overrides (user_id, permission_code, account_id, is_allowed)
                VALUES ($1::uuid, $2, NULL, $3)
                """,
                user_id,
                permission_code,
                allowed,
            )
    else:
        await supabase_execute(
            supabase.table("app_user_overrides")
            .delete()
            .eq("user_id", user_id)
            .eq("permission_code", permission_code)
            .is_("account_id", None)
        )
        if allowed != role_grants:
            await supabase_execute(
                supabase.table("app_user_overrides").insert(
                    {
                        "user_id": user_id,
                        "permission_code": permission_code,
                        "account_id": None,
                        "is_allowed": allowed,
                    }
                )
            )
    await invalidate_cache_pattern("auth_user:*")
    logger.info("Cache invalidated after %s access update for user %s", permission_code, user_id)


async def set_user_axelia_access(user_id: str, allowed: bool) -> None:
    """Accès Axelia : overrides globaux uniquement ; alignés sur defaults de rôle quand aucun override requis."""
    await set_user_global_permission_override(user_id, PermissionCodes.AXELIA_ACCESS, allowed)


async def set_user_playground_access(user_id: str, allowed: bool) -> None:
    """Accès Playground (/playground) : même modèle qu’Axelia."""
    await set_user_global_permission_override(user_id, PermissionCodes.PLAYGROUND_ACCESS, allowed)


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
