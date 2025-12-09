from __future__ import annotations

from typing import Any, Dict, List, Sequence
from collections import defaultdict

from fastapi import HTTPException

from app.core.db import supabase


def list_permissions() -> Sequence[Dict[str, Any]]:
    res = supabase.table("app_permissions").select("*").order("code").execute()
    return res.data


def list_roles() -> Sequence[Dict[str, Any]]:
    roles = supabase.table("app_roles").select("*").order("name").execute().data
    if not roles:
        return []

    role_ids = [role["id"] for role in roles]
    perms = (
        supabase.table("role_permissions")
        .select("role_id, permission_code")
        .in_("role_id", role_ids)
        .execute()
        .data
    )
    perms_by_role: Dict[str, List[str]] = {}
    for item in perms:
        perms_by_role.setdefault(item["role_id"], []).append(item["permission_code"])

    for role in roles:
        role["permissions"] = sorted(perms_by_role.get(role["id"], []))
    return roles


def create_role(payload: Dict[str, Any]) -> Dict[str, Any]:
    permissions = payload.pop("permissions", [])
    inserted = supabase.table("app_roles").insert(payload).execute()
    role = inserted.data[0]
    if permissions:
        supabase.table("role_permissions").upsert(
            [{"role_id": role["id"], "permission_code": perm} for perm in permissions]
        ).execute()
    role["permissions"] = permissions
    return role


def update_role(role_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    permissions = payload.pop("permissions", None)
    supabase.table("app_roles").update(payload).eq("id", role_id).execute()
    if permissions is not None:
        supabase.table("role_permissions").delete().eq("role_id", role_id).execute()
        if permissions:
            supabase.table("role_permissions").upsert(
                [{"role_id": role_id, "permission_code": perm} for perm in permissions]
            ).execute()
    role = (
        supabase.table("app_roles").select("*").eq("id", role_id).limit(1).execute().data[0]
    )
    if permissions is None:
        perms = (
            supabase.table("role_permissions")
            .select("permission_code")
            .eq("role_id", role_id)
            .execute()
            .data
        )
        role["permissions"] = sorted([p["permission_code"] for p in perms])
    else:
        role["permissions"] = permissions
    return role


def delete_role(role_id: str):
    role = (
        supabase.table("app_roles").select("slug").eq("id", role_id).limit(1).execute()
    )
    if not role.data:
        raise HTTPException(status_code=404, detail="role_not_found")
    if role.data[0]["slug"] == "admin":
        raise HTTPException(status_code=400, detail="cannot_delete_admin_role")
    supabase.table("app_roles").delete().eq("id", role_id).execute()


def list_app_users() -> Sequence[Dict[str, Any]]:
    users = supabase.table("app_users").select("*").order("created_at").execute().data
    if not users:
        return []

    user_ids = [u["user_id"] for u in users]
    role_rows = (
        supabase.table("app_user_roles")
        .select("id, user_id, role_id, account_id")
        .in_("user_id", user_ids)
        .execute()
        .data
    )
    role_ids = list({row["role_id"] for row in role_rows})
    role_map = {}
    if role_ids:
        roles = (
            supabase.table("app_roles").select("id, slug, name").in_("id", role_ids).execute()
        ).data
        role_map = {r["id"]: r for r in roles}

    overrides = (
        supabase.table("app_user_overrides")
        .select("id, user_id, permission_code, account_id, is_allowed")
        .in_("user_id", user_ids)
        .execute()
        .data
    )

    roles_by_user: Dict[str, List[Dict[str, Any]]] = {}
    for row in role_rows:
        role_info = role_map.get(row["role_id"], {})
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


def set_user_status(user_id: str, is_active: bool):
    supabase.table("app_users").update({"is_active": is_active}).eq("user_id", user_id).execute()


def set_user_roles(user_id: str, assignments: Sequence[Dict[str, Any]]):
    supabase.table("app_user_roles").delete().eq("user_id", user_id).execute()
    if assignments:
        payload = []
        for item in assignments:
            payload.append(
                {
                    "user_id": user_id,
                    "role_id": item["role_id"],
                    "account_id": item.get("account_id"),
                }
            )
        supabase.table("app_user_roles").upsert(payload).execute()


def set_user_overrides(user_id: str, overrides: Sequence[Dict[str, Any]]):
    supabase.table("app_user_overrides").delete().eq("user_id", user_id).execute()
    if overrides:
        payload = []
        for item in overrides:
            payload.append(
                {
                    "user_id": user_id,
                    "permission_code": item["permission_code"],
                    "account_id": item.get("account_id"),
                    "is_allowed": bool(item.get("is_allowed", True)),
                }
            )
        supabase.table("app_user_overrides").upsert(payload).execute()


def list_users_with_access() -> Sequence[Dict[str, Any]]:
    """Liste tous les utilisateurs avec leurs rôles et accès par compte"""
    users = supabase.table("app_users").select("*").order("created_at").execute().data
    if not users:
        return []

    user_ids = [u["user_id"] for u in users]
    
    # Récupérer les rôles
    role_rows = (
        supabase.table("app_user_roles")
        .select("id, user_id, role_id, account_id")
        .in_("user_id", user_ids)
        .execute()
        .data
    )
    
    role_ids = list({row["role_id"] for row in role_rows})
    role_map = {}
    if role_ids:
        roles = (
            supabase.table("app_roles").select("id, slug, name").in_("id", role_ids).execute()
        ).data
        role_map = {r["id"]: r for r in roles}

    # Récupérer les accès par compte
    access_rows = (
        supabase.table("user_account_access")
        .select("id, user_id, account_id, access_level")
        .in_("user_id", user_ids)
        .execute()
        .data
    )

    # Grouper les données par utilisateur - prendre le rôle le plus élevé
    roles_by_user: Dict[str, Dict[str, Any]] = {}
    role_priority = {"admin": 3, "dev": 2, "manager": 1}  # Plus élevé = plus de permissions
    
    for row in role_rows:
        role_info = role_map.get(row["role_id"], {})
        user_id = row["user_id"]
        role_slug = role_info.get("slug")
        current_priority = role_priority.get(role_slug, 0)
        
        if user_id not in roles_by_user:
            roles_by_user[user_id] = {
                "role_id": row["role_id"],
                "role_slug": role_slug,
                "role_name": role_info.get("name"),
            }
        else:
            # Garder le rôle avec la priorité la plus élevée
            existing_slug = roles_by_user[user_id].get("role_slug")
            existing_priority = role_priority.get(existing_slug, 0)
            if current_priority > existing_priority:
                roles_by_user[user_id] = {
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


def set_user_account_access(user_id: str, account_id: str, access_level: str):
    """Définit l'accès d'un utilisateur à un compte WhatsApp"""
    if access_level not in ["full", "lecture", "aucun"]:
        raise HTTPException(status_code=400, detail="invalid_access_level")
    
    # Vérifier si l'enregistrement existe déjà
    existing = (
        supabase.table("user_account_access")
        .select("id")
        .eq("user_id", user_id)
        .eq("account_id", account_id)
        .limit(1)
        .execute()
    )
    
    if existing.data:
        # Mise à jour de l'enregistrement existant
        supabase.table("user_account_access").update({
            "access_level": access_level,
        }).eq("user_id", user_id).eq("account_id", account_id).execute()
    else:
        # Insertion d'un nouvel enregistrement
        supabase.table("user_account_access").insert({
            "user_id": user_id,
            "account_id": account_id,
            "access_level": access_level,
        }).execute()


