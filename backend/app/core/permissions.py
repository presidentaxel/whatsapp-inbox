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
    PERMISSIONS_VIEW = "permissions.view"
    PERMISSIONS_MANAGE = "permissions.manage"


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
    PermissionCodes.PERMISSIONS_VIEW,
    PermissionCodes.PERMISSIONS_MANAGE,
}


@dataclass
class PermissionMatrix:
    global_permissions: Set[str] = field(default_factory=set)
    account_permissions: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    account_access_levels: Dict[str, str] = field(default_factory=dict)  # account_id -> 'full'|'lecture'|'aucun'

    def has(self, permission: str, account_id: Optional[str] = None) -> bool:
        if permission not in ALL_PERMISSION_CODES:
            return False
        
        # Exception spéciale : les permissions de gestion des permissions (permissions.view et permissions.manage)
        # ne sont PAS bloquées par access_level = 'aucun' car elles permettent de gérer les accès
        # même si l'admin a mis "aucun" pour lui-même
        admin_permissions = {
            PermissionCodes.PERMISSIONS_VIEW,
            PermissionCodes.PERMISSIONS_MANAGE,
        }
        if permission in admin_permissions:
            # Pour ces permissions, on ignore le access_level du compte
            # On vérifie seulement si l'utilisateur a la permission globale ou spécifique
            if permission in self.global_permissions:
                return True
            if account_id and permission in self.account_permissions.get(account_id, set()):
                return True
            # Même si pas de permission spécifique, si on a la permission globale, on l'a
            return False
        
        # Si un compte a access_level = 'aucun', aucune permission pour ce compte
        if account_id and self.account_access_levels.get(account_id) == "aucun":
            return False
        
        # Si access_level = 'lecture', bloquer les permissions d'écriture
        if account_id and self.account_access_levels.get(account_id) == "lecture":
            write_permissions = {
                PermissionCodes.MESSAGES_SEND,
                PermissionCodes.ACCOUNTS_MANAGE,
                PermissionCodes.ACCOUNTS_ASSIGN,
                PermissionCodes.USERS_MANAGE,
                PermissionCodes.ROLES_MANAGE,
                PermissionCodes.SETTINGS_MANAGE,
                PermissionCodes.PERMISSIONS_MANAGE,
            }
            if permission in write_permissions:
                return False
        
        if permission in self.global_permissions:
            # Si permission globale, vérifier que le compte n'est pas en 'aucun'
            if account_id and self.account_access_levels.get(account_id) == "aucun":
                return False
            return True
        
        if account_id and permission in self.account_permissions.get(account_id, set()):
            # Vérifier aussi que le compte n'est pas en 'aucun'
            if self.account_access_levels.get(account_id) == "aucun":
                return False
            return True
        return False

    def accounts_with(self, permission: str) -> Optional[Set[str]]:
        # Si permission globale, retourner tous les comptes sauf ceux en 'aucun'
        if permission in self.global_permissions:
            # Récupérer tous les comptes depuis account_access_levels ou account_permissions
            all_accounts = set(self.account_access_levels.keys())
            # Exclure les comptes en 'aucun'
            excluded = {acc_id for acc_id, level in self.account_access_levels.items() if level == "aucun"}
            accessible_accounts = all_accounts - excluded
            # Si on a des comptes accessibles, les retourner, sinon None (accès global)
            return accessible_accounts if accessible_accounts else None
        
        scoped = {
            acc_id
            for acc_id, perms in self.account_permissions.items()
            if permission in perms and self.account_access_levels.get(acc_id) != "aucun"
        }
        
        # Ajouter aussi les comptes avec accès 'full' ou 'lecture' selon la permission
        view_permissions = {
            PermissionCodes.ACCOUNTS_VIEW,
            PermissionCodes.CONVERSATIONS_VIEW,
            PermissionCodes.MESSAGES_VIEW,
            PermissionCodes.CONTACTS_VIEW,
            PermissionCodes.PERMISSIONS_VIEW,
        }
        if permission in view_permissions:
            for acc_id, level in self.account_access_levels.items():
                if level in ("full", "lecture"):
                    scoped.add(acc_id)
        
        return scoped if scoped else None

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


def _assign_default_manager(user_id: str):
    """
    Ensure every newly invited user has at least the manager role so they can load the app.
    """
    existing = (
        supabase.table("app_user_roles").select("id").eq("user_id", user_id).limit(1).execute()
    )
    if existing.data:
        return

    manager_role = (
        supabase.table("app_roles").select("id").eq("slug", "manager").limit(1).execute()
    )
    if not manager_role.data:
        return

    supabase.table("app_user_roles").insert(
        {"user_id": user_id, "role_id": manager_role.data[0]["id"]}
    ).execute()


def load_current_user(supabase_user: Any) -> CurrentUser:
    """
    Charge les permissions et rôles d'un utilisateur depuis Supabase.
    Cette fonction est exécutée dans un thread pool, donc elle est synchrone.
    """
    import logging
    import time
    logger = logging.getLogger(__name__)
    max_retries = 2
    
    # Retry en cas d'erreur réseau
    last_error = None
    role_rows_raw = []
    app_profile = None
    permissions = None
    
    for attempt in range(max_retries + 1):
        try:
            app_profile = _ensure_app_user_record(supabase_user)
            _assign_bootstrap_admin(supabase_user.id)
            _assign_default_manager(supabase_user.id)
            permissions = PermissionMatrix()

            role_rows_raw = (
                supabase.table("app_user_roles")
                .select("id, role_id, account_id")
                .eq("user_id", supabase_user.id)
                .execute()
            ).data
            break  # Succès, sortir de la boucle
            
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            is_network_error = any(keyword in error_str for keyword in [
                "readerror", "connecterror", "timeout", "10035", "socket", "connection"
            ])
            
            if is_network_error and attempt < max_retries:
                logger.warning(f"Network error loading user permissions (attempt {attempt + 1}/{max_retries + 1}): {e}")
                time.sleep(0.5 * (attempt + 1))  # Backoff exponentiel
                continue
            elif attempt < max_retries:
                logger.warning(f"Error loading user permissions (attempt {attempt + 1}/{max_retries + 1}): {e}")
                time.sleep(0.5 * (attempt + 1))
                continue
            else:
                logger.error(f"Error loading user permissions after all retries: {e}", exc_info=True)
                # Retourner un utilisateur avec permissions minimales plutôt que de faire échouer
                role_rows_raw = []
                permissions = PermissionMatrix()
                break
    
    if not app_profile:
        app_profile = _ensure_app_user_record(supabase_user)
    if not permissions:
        permissions = PermissionMatrix()

    role_ids = [row["role_id"] for row in role_rows_raw]
    role_map: Dict[str, Dict[str, Any]] = {}
    if role_ids:
        # Retry pour les appels suivants
        for attempt in range(max_retries + 1):
            try:
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
                break
            except Exception as e:
                if attempt < max_retries:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                else:
                    logger.error(f"Error fetching roles/permissions after retries: {e}")
                    role_perms = []
                    break

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

    # Retry pour les overrides
    overrides_raw = []
    for attempt in range(max_retries + 1):
        try:
            overrides_raw = (
                supabase.table("app_user_overrides")
                .select("id, permission_code, account_id, is_allowed")
                .eq("user_id", supabase_user.id)
                .execute()
            ).data
            break
        except Exception as e:
            if attempt < max_retries:
                time.sleep(0.5 * (attempt + 1))
                continue
            else:
                logger.error(f"Error fetching user overrides after retries: {e}")
                overrides_raw = []
                break

    for override in overrides_raw:
        perm = override["permission_code"]
        scope = override.get("account_id")
        if override.get("is_allowed"):
            permissions.grant(perm, scope)
        else:
            permissions.revoke(perm, scope)

    # Charger les accès par compte depuis user_account_access
    account_access_raw = []
    for attempt in range(max_retries + 1):
        try:
            account_access_raw = (
                supabase.table("user_account_access")
                .select("account_id, access_level")
                .eq("user_id", supabase_user.id)
                .execute()
            ).data
            break
        except Exception as e:
            if attempt < max_retries:
                time.sleep(0.5 * (attempt + 1))
                continue
            else:
                logger.error(f"Error fetching user account access after retries: {e}")
                account_access_raw = []
                break

    # Stocker les niveaux d'accès par compte pour les utiliser dans has() et accounts_with()
    # Ces niveaux prennent le dessus sur les permissions basées sur les rôles
    for access in account_access_raw:
        account_id = access.get("account_id")
        access_level = access.get("access_level")
        if account_id and access_level:
            permissions.account_access_levels[account_id] = access_level
    
    # Appliquer les restrictions d'accès par compte
    # Si access_level = 'aucun' → retirer toutes les permissions pour ce compte (même les globales)
    # Si access_level = 'lecture' → garder seulement les permissions de lecture (pas messages.send)
    # Si access_level = 'full' → garder toutes les permissions
    for access in account_access_raw:
        account_id = access.get("account_id")
        access_level = access.get("access_level")
        
        if access_level == "aucun":
            # Retirer toutes les permissions pour ce compte (même si permission globale)
            # On marque juste le niveau, la méthode has() gère le reste
            permissions.account_permissions.pop(account_id, None)
        elif access_level == "lecture":
            # Garder seulement les permissions de lecture, retirer messages.send et autres permissions d'écriture
            # Même si la permission est globale, on restreint pour ce compte spécifique
            if account_id in permissions.account_permissions:
                perms = permissions.account_permissions[account_id]
                # Retirer les permissions d'écriture/modification
                perms.discard(PermissionCodes.MESSAGES_SEND)
                perms.discard(PermissionCodes.ACCOUNTS_MANAGE)
                perms.discard(PermissionCodes.ACCOUNTS_ASSIGN)
                perms.discard(PermissionCodes.USERS_MANAGE)
                perms.discard(PermissionCodes.ROLES_MANAGE)
                perms.discard(PermissionCodes.SETTINGS_MANAGE)
                perms.discard(PermissionCodes.PERMISSIONS_MANAGE)
                # Garder seulement : accounts.view, conversations.view, messages.view, contacts.view, permissions.view
                allowed_read_perms = {
                    PermissionCodes.ACCOUNTS_VIEW,
                    PermissionCodes.CONVERSATIONS_VIEW,
                    PermissionCodes.MESSAGES_VIEW,
                    PermissionCodes.CONTACTS_VIEW,
                    PermissionCodes.PERMISSIONS_VIEW,
                }
                perms_to_remove = [p for p in list(perms) if p not in allowed_read_perms]
                for perm in perms_to_remove:
                    perms.discard(perm)
        # Si access_level == "full", on garde toutes les permissions existantes

    return CurrentUser(
        id=supabase_user.id,
        email=supabase_user.email,
        is_active=app_profile.get("is_active", True),
        app_profile={
            **app_profile,
            "display_name": app_profile.get("display_name"),
            "profile_picture_url": app_profile.get("profile_picture_url"),
        },
        permissions=permissions,
        supabase_user=supabase_user,
        role_assignments=role_assignments,
        overrides=overrides_raw,
    )


