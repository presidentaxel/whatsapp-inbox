from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

from fastapi import HTTPException, status

from app.core.db import supabase


class PermissionCodes:
    ACCOUNTS_VIEW = "accounts.view"
    ACCOUNTS_MANAGE = "accounts.manage"
    ACCOUNTS_ASSIGN = "accounts.assign"
    CONVERSATIONS_VIEW = "conversations.view"
    MESSAGES_VIEW = "messages.view"
    MESSAGES_SEND = "messages.send"
    CONTACTS_VIEW = "contacts.view"
    USERS_MANAGE = "users.manage"
    ROLES_MANAGE = "roles.manage"
    SETTINGS_MANAGE = "settings.manage"


ALL_PERMISSION_CODES = {
    PermissionCodes.ACCOUNTS_VIEW,
    PermissionCodes.ACCOUNTS_MANAGE,
    PermissionCodes.ACCOUNTS_ASSIGN,
    PermissionCodes.CONVERSATIONS_VIEW,
    PermissionCodes.MESSAGES_VIEW,
    PermissionCodes.MESSAGES_SEND,
    PermissionCodes.CONTACTS_VIEW,
    PermissionCodes.USERS_MANAGE,
    PermissionCodes.ROLES_MANAGE,
    PermissionCodes.SETTINGS_MANAGE,
}


@dataclass
class PermissionMatrix:
    global_permissions: Set[str] = field(default_factory=set)
    account_permissions: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))

    def has(self, permission: str, account_id: Optional[str] = None) -> bool:
        if permission not in ALL_PERMISSION_CODES:
            return False
        if permission in self.global_permissions:
            return True
        if account_id and permission in self.account_permissions.get(account_id, set()):
            return True
        return False

    def accounts_with(self, permission: str) -> Optional[Set[str]]:
        if permission in self.global_permissions:
            return None
        scoped = {
            acc_id
            for acc_id, perms in self.account_permissions.items()
            if permission in perms
        }
        return scoped

    def grant(self, permission: str, account_id: Optional[str] = None):
        if permission not in ALL_PERMISSION_CODES:
            return
        if account_id:
            self.account_permissions[account_id].add(permission)
        else:
            self.global_permissions.add(permission)

    def revoke(self, permission: str, account_id: Optional[str] = None):
        target = (
            self.account_permissions.get(account_id)
            if account_id
            else self.global_permissions
        )
        if target and permission in target:
            target.remove(permission)


@dataclass
class CurrentUser:
    id: str
    email: Optional[str]
    is_active: bool
    app_profile: Dict[str, Any]
    permissions: PermissionMatrix
    supabase_user: Any
    role_assignments: list[Dict[str, Any]] = field(default_factory=list)
    overrides: list[Dict[str, Any]] = field(default_factory=list)

    def require(self, permission: str, account_id: Optional[str] = None):
        if not self.permissions.has(permission, account_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="permission_denied",
            )

    def accounts_for(self, permission: str) -> Optional[Set[str]]:
        return self.permissions.accounts_with(permission)


def _ensure_app_user_record(user: Any) -> Dict[str, Any]:
    res = (
        supabase.table("app_users")
        .select("*")
        .eq("user_id", user.id)
        .limit(1)
        .execute()
    )
    if res.data:
        record = res.data[0]
    else:
        payload = {
            "user_id": user.id,
            "email": user.email,
            "display_name": user.user_metadata.get("full_name") if user.user_metadata else None,
        }
        inserted = supabase.table("app_users").insert(payload).execute()
        record = inserted.data[0]

    if not record.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user_disabled")
    return record


def _assign_bootstrap_admin(user_id: str):
    existing_roles = (
        supabase.table("app_user_roles").select("id").limit(1).execute()
    )
    if existing_roles.data:
        return

    admin_role = (
        supabase.table("app_roles").select("id").eq("slug", "admin").limit(1).execute()
    )
    if not admin_role.data:
        return

    supabase.table("app_user_roles").insert(
        {"user_id": user_id, "role_id": admin_role.data[0]["id"]}
    ).execute()


def _assign_default_viewer(user_id: str):
    """
    Ensure every newly invited user has at least the viewer role so they can load the app.
    """
    existing = (
        supabase.table("app_user_roles").select("id").eq("user_id", user_id).limit(1).execute()
    )
    if existing.data:
        return

    viewer_role = (
        supabase.table("app_roles").select("id").eq("slug", "viewer").limit(1).execute()
    )
    if not viewer_role.data:
        return

    supabase.table("app_user_roles").insert(
        {"user_id": user_id, "role_id": viewer_role.data[0]["id"]}
    ).execute()


def load_current_user(supabase_user: Any) -> CurrentUser:
    app_profile = _ensure_app_user_record(supabase_user)
    _assign_bootstrap_admin(supabase_user.id)
    _assign_default_viewer(supabase_user.id)
    permissions = PermissionMatrix()

    role_rows_raw = (
        supabase.table("app_user_roles")
        .select("id, role_id, account_id")
        .eq("user_id", supabase_user.id)
        .execute()
    ).data

    role_ids = [row["role_id"] for row in role_rows_raw]
    role_map: Dict[str, Dict[str, Any]] = {}
    if role_ids:
        fetched_roles = (
            supabase.table("app_roles").select("id, slug, name").in_("id", role_ids).execute()
        ).data
        role_map = {r["id"]: r for r in fetched_roles}
        role_perms = (
            supabase.table("role_permissions")
            .select("role_id, permission_code")
            .in_("role_id", role_ids)
            .execute()
        ).data

        perms_by_role: Dict[str, Set[str]] = defaultdict(set)
        for item in role_perms:
            perms_by_role[item["role_id"]].add(item["permission_code"])

        for row in role_rows_raw:
            role_id = row["role_id"]
            scope = row.get("account_id")
            for perm in perms_by_role.get(role_id, set()):
                permissions.grant(perm, scope)

    role_assignments = []
    for row in role_rows_raw:
        role_meta = role_map.get(row["role_id"], {})
        role_assignments.append(
            {
                "id": row["id"],
                "role_id": row["role_id"],
                "role_slug": role_meta.get("slug"),
                "role_name": role_meta.get("name"),
                "account_id": row.get("account_id"),
            }
        )

    overrides_raw = (
        supabase.table("app_user_overrides")
        .select("id, permission_code, account_id, is_allowed")
        .eq("user_id", supabase_user.id)
        .execute()
    ).data

    for override in overrides_raw:
        perm = override["permission_code"]
        scope = override.get("account_id")
        if override.get("is_allowed"):
            permissions.grant(perm, scope)
        else:
            permissions.revoke(perm, scope)

    return CurrentUser(
        id=supabase_user.id,
        email=supabase_user.email,
        is_active=app_profile.get("is_active", True),
        app_profile=app_profile,
        permissions=permissions,
        supabase_user=supabase_user,
        role_assignments=role_assignments,
        overrides=overrides_raw,
    )


