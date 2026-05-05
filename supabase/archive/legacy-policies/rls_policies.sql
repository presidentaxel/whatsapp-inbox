-- ============================================
-- POLITIQUES RLS (Row Level Security)
-- Protection des données multi-tenant avec RBAC
-- ============================================
-- 
-- Stratégie:
-- 1. Le backend (service_role) peut tout faire (bypass RLS)
-- 2. Les utilisateurs authentifiés accèdent aux données selon leur RBAC
-- 3. Protection multi-tenant basée sur account_id
-- 4. Utilisation des permissions existantes (app_permissions, app_roles, etc.)
--
-- IMPORTANT: Ces politiques ne cassent pas le backend car il utilise service_role
-- ============================================

-- ============================================
-- FONCTIONS HELPER
-- ============================================

-- Fonction pour vérifier si l'utilisateur a une permission globale
CREATE OR REPLACE FUNCTION user_has_global_permission(permission_code text)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
AS $$
DECLARE
  has_perm boolean;
BEGIN
  -- Service role peut tout faire
  IF auth.role() = 'service_role' THEN
    RETURN true;
  END IF;

  -- Vérifier si l'utilisateur a la permission globalement
  SELECT EXISTS (
    SELECT 1
    FROM app_user_roles aur
    JOIN role_permissions rp ON rp.role_id = aur.role_id
    WHERE aur.user_id = auth.uid()
      AND aur.account_id IS NULL
      AND rp.permission_code = user_has_global_permission.permission_code
  ) INTO has_perm;

  -- Vérifier aussi les overrides
  IF has_perm IS NULL OR NOT has_perm THEN
    SELECT EXISTS (
      SELECT 1
      FROM app_user_overrides auo
      WHERE auo.user_id = auth.uid()
        AND auo.account_id IS NULL
        AND auo.permission_code = user_has_global_permission.permission_code
        AND auo.is_allowed = true
    ) INTO has_perm;
  END IF;

  RETURN COALESCE(has_perm, false);
END;
$$;

-- Fonction pour vérifier si l'utilisateur a une permission pour un account spécifique
CREATE OR REPLACE FUNCTION user_has_account_permission(permission_code text, target_account_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
AS $$
DECLARE
  has_perm boolean;
BEGIN
  -- Service role peut tout faire
  IF auth.role() = 'service_role' THEN
    RETURN true;
  END IF;

  -- Vérifier permission globale d'abord
  IF user_has_global_permission(permission_code) THEN
    RETURN true;
  END IF;

  -- Vérifier permission spécifique à l'account
  SELECT EXISTS (
    SELECT 1
    FROM app_user_roles aur
    JOIN role_permissions rp ON rp.role_id = aur.role_id
    WHERE aur.user_id = auth.uid()
      AND (aur.account_id = target_account_id OR aur.account_id IS NULL)
      AND rp.permission_code = user_has_account_permission.permission_code
  ) INTO has_perm;

  -- Vérifier aussi les overrides
  IF has_perm IS NULL OR NOT has_perm THEN
    SELECT EXISTS (
      SELECT 1
      FROM app_user_overrides auo
      WHERE auo.user_id = auth.uid()
        AND (auo.account_id = target_account_id OR auo.account_id IS NULL)
        AND auo.permission_code = user_has_account_permission.permission_code
        AND auo.is_allowed = true
    ) INTO has_perm;
  END IF;

  RETURN COALESCE(has_perm, false);
END;
$$;

-- Fonction pour vérifier si l'utilisateur est actif
CREATE OR REPLACE FUNCTION is_user_active()
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
AS $$
BEGIN
  -- Service role peut tout faire
  IF auth.role() = 'service_role' THEN
    RETURN true;
  END IF;

  -- Vérifier si l'utilisateur existe et est actif
  RETURN EXISTS (
    SELECT 1
    FROM app_users
    WHERE user_id = auth.uid()
      AND is_active = true
  );
END;
$$;

-- Fonction pour obtenir les account_ids auxquels l'utilisateur a accès
CREATE OR REPLACE FUNCTION user_accessible_account_ids()
RETURNS setof uuid
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
AS $$
BEGIN
  -- Service role peut tout voir
  IF auth.role() = 'service_role' THEN
    RETURN QUERY SELECT id FROM whatsapp_accounts;
    RETURN;
  END IF;

  -- Retourner les accounts où l'utilisateur a au moins une permission
  RETURN QUERY
  SELECT DISTINCT wa.id
  FROM whatsapp_accounts wa
  WHERE EXISTS (
    SELECT 1
    FROM app_user_roles aur
    JOIN role_permissions rp ON rp.role_id = aur.role_id
    WHERE aur.user_id = auth.uid()
      AND (aur.account_id = wa.id OR aur.account_id IS NULL)
  )
  OR EXISTS (
    SELECT 1
    FROM app_user_overrides auo
    WHERE auo.user_id = auth.uid()
      AND (auo.account_id = wa.id OR auo.account_id IS NULL)
      AND auo.is_allowed = true
  );
END;
$$;

-- ============================================
-- ACTIVATION RLS SUR TOUTES LES TABLES
-- ============================================

ALTER TABLE whatsapp_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE role_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_user_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE bot_profiles ENABLE ROW LEVEL SECURITY;

-- ============================================
-- POLITIQUES: WHATSAPP_ACCOUNTS
-- ============================================

-- SELECT: Voir les accounts si on a accounts.view
DROP POLICY IF EXISTS "accounts_select" ON whatsapp_accounts;
CREATE POLICY "accounts_select" ON whatsapp_accounts
  FOR SELECT
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('accounts.view'))
  );

-- INSERT: Créer des accounts si on a accounts.manage
DROP POLICY IF EXISTS "accounts_insert" ON whatsapp_accounts;
CREATE POLICY "accounts_insert" ON whatsapp_accounts
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('accounts.manage'))
  );

-- UPDATE: Modifier des accounts si on a accounts.manage
DROP POLICY IF EXISTS "accounts_update" ON whatsapp_accounts;
CREATE POLICY "accounts_update" ON whatsapp_accounts
  FOR UPDATE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('accounts.manage'))
  );

-- DELETE: Supprimer des accounts si on a accounts.manage
DROP POLICY IF EXISTS "accounts_delete" ON whatsapp_accounts;
CREATE POLICY "accounts_delete" ON whatsapp_accounts
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('accounts.manage'))
  );

-- ============================================
-- POLITIQUES: CONTACTS
-- ============================================

-- SELECT: Voir les contacts si on a contacts.view
DROP POLICY IF EXISTS "contacts_select" ON contacts;
CREATE POLICY "contacts_select" ON contacts
  FOR SELECT
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('contacts.view'))
  );

-- INSERT: Créer des contacts (via backend/webhooks principalement)
DROP POLICY IF EXISTS "contacts_insert" ON contacts;
CREATE POLICY "contacts_insert" ON contacts
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    is_user_active()
  );

-- UPDATE: Modifier des contacts
DROP POLICY IF EXISTS "contacts_update" ON contacts;
CREATE POLICY "contacts_update" ON contacts
  FOR UPDATE
  USING (
    auth.role() = 'service_role' OR
    is_user_active()
  );

-- DELETE: Supprimer des contacts (rare, mais possible)
DROP POLICY IF EXISTS "contacts_delete" ON contacts;
CREATE POLICY "contacts_delete" ON contacts
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('accounts.manage'))
  );

-- ============================================
-- POLITIQUES: CONVERSATIONS
-- ============================================

-- SELECT: Voir les conversations si on a conversations.view pour l'account
DROP POLICY IF EXISTS "conversations_select" ON conversations;
CREATE POLICY "conversations_select" ON conversations
  FOR SELECT
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      (
        user_has_global_permission('conversations.view') OR
        user_has_account_permission('conversations.view', account_id)
      )
    )
  );

-- INSERT: Créer des conversations (via backend/webhooks)
DROP POLICY IF EXISTS "conversations_insert" ON conversations;
CREATE POLICY "conversations_insert" ON conversations
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      (
        user_has_global_permission('conversations.view') OR
        user_has_account_permission('conversations.view', account_id)
      )
    )
  );

-- UPDATE: Modifier des conversations (favorite, unread_count, etc.)
DROP POLICY IF EXISTS "conversations_update" ON conversations;
CREATE POLICY "conversations_update" ON conversations
  FOR UPDATE
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      (
        user_has_global_permission('conversations.view') OR
        user_has_account_permission('conversations.view', account_id)
      )
    )
  );

-- DELETE: Supprimer des conversations (rare)
DROP POLICY IF EXISTS "conversations_delete" ON conversations;
CREATE POLICY "conversations_delete" ON conversations
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('accounts.manage'))
  );

-- ============================================
-- POLITIQUES: MESSAGES
-- ============================================

-- SELECT: Voir les messages si on a messages.view pour l'account de la conversation
DROP POLICY IF EXISTS "messages_select" ON messages;
CREATE POLICY "messages_select" ON messages
  FOR SELECT
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      EXISTS (
        SELECT 1
        FROM conversations c
        WHERE c.id = messages.conversation_id
          AND (
            user_has_global_permission('messages.view') OR
            user_has_account_permission('messages.view', c.account_id)
          )
      )
    )
  );

-- INSERT: Créer des messages si on a messages.send
DROP POLICY IF EXISTS "messages_insert" ON messages;
CREATE POLICY "messages_insert" ON messages
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      EXISTS (
        SELECT 1
        FROM conversations c
        WHERE c.id = messages.conversation_id
          AND (
            user_has_global_permission('messages.send') OR
            user_has_account_permission('messages.send', c.account_id)
          )
      )
    )
  );

-- UPDATE: Modifier des messages (status, etc.)
DROP POLICY IF EXISTS "messages_update" ON messages;
CREATE POLICY "messages_update" ON messages
  FOR UPDATE
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      EXISTS (
        SELECT 1
        FROM conversations c
        WHERE c.id = messages.conversation_id
          AND (
            user_has_global_permission('messages.view') OR
            user_has_account_permission('messages.view', c.account_id)
          )
      )
    )
  );

-- DELETE: Supprimer des messages (rare, admin seulement)
DROP POLICY IF EXISTS "messages_delete" ON messages;
CREATE POLICY "messages_delete" ON messages
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('accounts.manage'))
  );

-- ============================================
-- POLITIQUES: APP_USERS
-- ============================================

-- SELECT: Voir son propre profil ou si on a users.manage
DROP POLICY IF EXISTS "app_users_select" ON app_users;
CREATE POLICY "app_users_select" ON app_users
  FOR SELECT
  USING (
    auth.role() = 'service_role' OR
    user_id = auth.uid() OR
    (is_user_active() AND user_has_global_permission('users.manage'))
  );

-- INSERT: Créer des profils (auto-création lors de la première connexion)
DROP POLICY IF EXISTS "app_users_insert" ON app_users;
CREATE POLICY "app_users_insert" ON app_users
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    user_id = auth.uid() OR
    (is_user_active() AND user_has_global_permission('users.manage'))
  );

-- UPDATE: Modifier son propre profil ou si on a users.manage
DROP POLICY IF EXISTS "app_users_update" ON app_users;
CREATE POLICY "app_users_update" ON app_users
  FOR UPDATE
  USING (
    auth.role() = 'service_role' OR
    user_id = auth.uid() OR
    (is_user_active() AND user_has_global_permission('users.manage'))
  );

-- DELETE: Supprimer des profils (admin seulement)
DROP POLICY IF EXISTS "app_users_delete" ON app_users;
CREATE POLICY "app_users_delete" ON app_users
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('users.manage'))
  );

-- ============================================
-- POLITIQUES: APP_ROLES
-- ============================================

-- SELECT: Voir les rôles si on a roles.manage
DROP POLICY IF EXISTS "app_roles_select" ON app_roles;
CREATE POLICY "app_roles_select" ON app_roles
  FOR SELECT
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('roles.manage'))
  );

-- INSERT/UPDATE/DELETE: Gérer les rôles si on a roles.manage
DROP POLICY IF EXISTS "app_roles_insert" ON app_roles;
CREATE POLICY "app_roles_insert" ON app_roles
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('roles.manage'))
  );

DROP POLICY IF EXISTS "app_roles_update" ON app_roles;
CREATE POLICY "app_roles_update" ON app_roles
  FOR UPDATE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('roles.manage'))
  );

DROP POLICY IF EXISTS "app_roles_delete" ON app_roles;
CREATE POLICY "app_roles_delete" ON app_roles
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('roles.manage'))
  );

-- ============================================
-- POLITIQUES: APP_PERMISSIONS
-- ============================================

-- SELECT: Voir les permissions si on a roles.manage
DROP POLICY IF EXISTS "app_permissions_select" ON app_permissions;
CREATE POLICY "app_permissions_select" ON app_permissions
  FOR SELECT
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('roles.manage'))
  );

-- INSERT/UPDATE/DELETE: Gérer les permissions (admin seulement, généralement en lecture seule)
DROP POLICY IF EXISTS "app_permissions_insert" ON app_permissions;
CREATE POLICY "app_permissions_insert" ON app_permissions
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('roles.manage'))
  );

DROP POLICY IF EXISTS "app_permissions_update" ON app_permissions;
CREATE POLICY "app_permissions_update" ON app_permissions
  FOR UPDATE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('roles.manage'))
  );

DROP POLICY IF EXISTS "app_permissions_delete" ON app_permissions;
CREATE POLICY "app_permissions_delete" ON app_permissions
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('roles.manage'))
  );

-- ============================================
-- POLITIQUES: ROLE_PERMISSIONS
-- ============================================

-- SELECT: Voir les permissions des rôles si on a roles.manage
DROP POLICY IF EXISTS "role_permissions_select" ON role_permissions;
CREATE POLICY "role_permissions_select" ON role_permissions
  FOR SELECT
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('roles.manage'))
  );

-- INSERT/UPDATE/DELETE: Gérer les permissions des rôles
DROP POLICY IF EXISTS "role_permissions_insert" ON role_permissions;
CREATE POLICY "role_permissions_insert" ON role_permissions
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('roles.manage'))
  );

DROP POLICY IF EXISTS "role_permissions_update" ON role_permissions;
CREATE POLICY "role_permissions_update" ON role_permissions
  FOR UPDATE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('roles.manage'))
  );

DROP POLICY IF EXISTS "role_permissions_delete" ON role_permissions;
CREATE POLICY "role_permissions_delete" ON role_permissions
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('roles.manage'))
  );

-- ============================================
-- POLITIQUES: APP_USER_ROLES
-- ============================================

-- SELECT: Voir ses propres rôles ou si on a users.manage
DROP POLICY IF EXISTS "app_user_roles_select" ON app_user_roles;
CREATE POLICY "app_user_roles_select" ON app_user_roles
  FOR SELECT
  USING (
    auth.role() = 'service_role' OR
    user_id = auth.uid() OR
    (is_user_active() AND user_has_global_permission('users.manage'))
  );

-- INSERT: Assigner des rôles si on a users.manage ou accounts.assign
DROP POLICY IF EXISTS "app_user_roles_insert" ON app_user_roles;
CREATE POLICY "app_user_roles_insert" ON app_user_roles
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      (
        user_has_global_permission('users.manage') OR
        (account_id IS NOT NULL AND user_has_global_permission('accounts.assign'))
      )
    )
  );

-- UPDATE: Modifier des rôles si on a users.manage
DROP POLICY IF EXISTS "app_user_roles_update" ON app_user_roles;
CREATE POLICY "app_user_roles_update" ON app_user_roles
  FOR UPDATE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('users.manage'))
  );

-- DELETE: Supprimer des rôles si on a users.manage
DROP POLICY IF EXISTS "app_user_roles_delete" ON app_user_roles;
CREATE POLICY "app_user_roles_delete" ON app_user_roles
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('users.manage'))
  );

-- ============================================
-- POLITIQUES: APP_USER_OVERRIDES
-- ============================================

-- SELECT: Voir ses propres overrides ou si on a users.manage
DROP POLICY IF EXISTS "app_user_overrides_select" ON app_user_overrides;
CREATE POLICY "app_user_overrides_select" ON app_user_overrides
  FOR SELECT
  USING (
    auth.role() = 'service_role' OR
    user_id = auth.uid() OR
    (is_user_active() AND user_has_global_permission('users.manage'))
  );

-- INSERT/UPDATE/DELETE: Gérer les overrides si on a users.manage
DROP POLICY IF EXISTS "app_user_overrides_insert" ON app_user_overrides;
CREATE POLICY "app_user_overrides_insert" ON app_user_overrides
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('users.manage'))
  );

DROP POLICY IF EXISTS "app_user_overrides_update" ON app_user_overrides;
CREATE POLICY "app_user_overrides_update" ON app_user_overrides
  FOR UPDATE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('users.manage'))
  );

DROP POLICY IF EXISTS "app_user_overrides_delete" ON app_user_overrides;
CREATE POLICY "app_user_overrides_delete" ON app_user_overrides
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('users.manage'))
  );

-- ============================================
-- POLITIQUES: BOT_PROFILES
-- ============================================

-- SELECT: Voir les profils bot si on a accès à l'account
DROP POLICY IF EXISTS "bot_profiles_select" ON bot_profiles;
CREATE POLICY "bot_profiles_select" ON bot_profiles
  FOR SELECT
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      (
        user_has_global_permission('accounts.view') OR
        user_has_account_permission('accounts.view', account_id)
      )
    )
  );

-- INSERT: Créer des profils bot si on a accounts.manage
DROP POLICY IF EXISTS "bot_profiles_insert" ON bot_profiles;
CREATE POLICY "bot_profiles_insert" ON bot_profiles
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      (
        user_has_global_permission('accounts.manage') OR
        user_has_account_permission('accounts.manage', account_id)
      )
    )
  );

-- UPDATE: Modifier des profils bot si on a accounts.manage
DROP POLICY IF EXISTS "bot_profiles_update" ON bot_profiles;
CREATE POLICY "bot_profiles_update" ON bot_profiles
  FOR UPDATE
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      (
        user_has_global_permission('accounts.manage') OR
        user_has_account_permission('accounts.manage', account_id)
      )
    )
  );

-- DELETE: Supprimer des profils bot si on a accounts.manage
DROP POLICY IF EXISTS "bot_profiles_delete" ON bot_profiles;
CREATE POLICY "bot_profiles_delete" ON bot_profiles
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      (
        user_has_global_permission('accounts.manage') OR
        user_has_account_permission('accounts.manage', account_id)
      )
    )
  );

-- ============================================
-- FONCTION HELPER: Vérifier si l'utilisateur a un accès valide à un compte
-- (exclut les comptes avec access_level = 'aucun')
-- ============================================
CREATE OR REPLACE FUNCTION user_has_account_access(target_account_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
AS $$
DECLARE
  access_level_val text;
BEGIN
  -- Service role peut tout faire
  IF auth.role() = 'service_role' THEN
    RETURN true;
  END IF;

  -- Vérifier si l'utilisateur a un accès explicite au compte
  SELECT uaa.access_level INTO access_level_val
  FROM user_account_access uaa
  WHERE uaa.user_id = auth.uid()
    AND uaa.account_id = target_account_id
  LIMIT 1;

  -- Si access_level = 'aucun', pas d'accès (même avec permission globale)
  IF access_level_val = 'aucun' THEN
    RETURN false;
  END IF;

  -- Si pas d'enregistrement dans user_account_access, vérifier les permissions classiques
  -- (permissions via rôles/overrides, y compris les permissions globales)
  IF access_level_val IS NULL THEN
    RETURN user_has_account_permission('accounts.view', target_account_id);
  END IF;

  -- Si access_level = 'full' ou 'lecture', l'utilisateur a accès
  RETURN true;
END;
$$;

-- ============================================
-- ACTIVATION RLS SUR LES NOUVELLES TABLES
-- ============================================

ALTER TABLE user_account_access ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_chat_settings ENABLE ROW LEVEL SECURITY;

-- ============================================
-- POLITIQUES: USER_ACCOUNT_ACCESS
-- ============================================

-- SELECT: Voir ses propres accès ou si on a permissions.manage
DROP POLICY IF EXISTS "user_account_access_select" ON user_account_access;
CREATE POLICY "user_account_access_select" ON user_account_access
  FOR SELECT
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      (
        user_id = auth.uid() OR
        user_has_global_permission('permissions.manage')
      )
    )
  );

-- INSERT: Créer des accès si on a permissions.manage
DROP POLICY IF EXISTS "user_account_access_insert" ON user_account_access;
CREATE POLICY "user_account_access_insert" ON user_account_access
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      user_has_global_permission('permissions.manage')
    )
  );

-- UPDATE: Modifier des accès si on a permissions.manage
DROP POLICY IF EXISTS "user_account_access_update" ON user_account_access;
CREATE POLICY "user_account_access_update" ON user_account_access
  FOR UPDATE
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      user_has_global_permission('permissions.manage')
    )
  );

-- DELETE: Supprimer des accès si on a permissions.manage
DROP POLICY IF EXISTS "user_account_access_delete" ON user_account_access;
CREATE POLICY "user_account_access_delete" ON user_account_access
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      user_has_global_permission('permissions.manage')
    )
  );

-- ============================================
-- POLITIQUES: USER_CHAT_SETTINGS
-- ============================================

-- SELECT: Voir uniquement ses propres paramètres
DROP POLICY IF EXISTS "user_chat_settings_select" ON user_chat_settings;
CREATE POLICY "user_chat_settings_select" ON user_chat_settings
  FOR SELECT
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      user_id = auth.uid()
    )
  );

-- INSERT: Créer ses propres paramètres
DROP POLICY IF EXISTS "user_chat_settings_insert" ON user_chat_settings;
CREATE POLICY "user_chat_settings_insert" ON user_chat_settings
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      user_id = auth.uid()
    )
  );

-- UPDATE: Modifier uniquement ses propres paramètres
DROP POLICY IF EXISTS "user_chat_settings_update" ON user_chat_settings;
CREATE POLICY "user_chat_settings_update" ON user_chat_settings
  FOR UPDATE
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      user_id = auth.uid()
    )
  );

-- DELETE: Supprimer uniquement ses propres paramètres
DROP POLICY IF EXISTS "user_chat_settings_delete" ON user_chat_settings;
CREATE POLICY "user_chat_settings_delete" ON user_chat_settings
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      user_id = auth.uid()
    )
  );

-- ============================================
-- FONCTIONS SÉCURISÉES: VUES MESSAGE_COSTS_WEEKLY
-- ============================================
-- Note: Les vues ne peuvent pas avoir de politiques RLS directement dans Supabase
-- (sauf si elles sont matérialisées). On crée donc des fonctions sécurisées
-- pour accéder aux données des vues avec les bonnes permissions.
--
-- Utilisation:
-- - Pour accéder aux coûts globaux: SELECT * FROM get_message_costs_weekly_secure();
-- - Pour accéder aux coûts par compte: SELECT * FROM get_message_costs_weekly_by_account_secure();
--
-- Ces fonctions respectent les permissions et les niveaux d'accès (access_level)
-- définis dans user_account_access.

-- Fonction pour obtenir les coûts hebdomadaires globaux (tous comptes confondus)
-- Retourne seulement les données pour les comptes auxquels l'utilisateur a accès
CREATE OR REPLACE FUNCTION get_message_costs_weekly_secure()
RETURNS TABLE (
  week_start date,
  year double precision,
  week_number double precision,
  total_messages_sent bigint,
  paid_messages_count bigint,
  total_cost numeric,
  avg_cost_per_message numeric,
  min_cost numeric,
  max_cost numeric
)
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
AS $$
BEGIN
  -- Service role peut tout voir
  IF auth.role() = 'service_role' THEN
    RETURN QUERY
    SELECT *
    FROM message_costs_weekly;
    RETURN;
  END IF;

  -- Pour les utilisateurs authentifiés, retourner les coûts agrégés
  -- seulement pour les comptes auxquels ils ont accès
  RETURN QUERY
  WITH filtered_costs AS (
    SELECT mcwa.*
    FROM message_costs_weekly_by_account mcwa
    WHERE is_user_active()
      AND user_has_account_access(mcwa.account_id)
  )
  SELECT
    fc.week_start,
    fc.year,
    fc.week_number,
    SUM(fc.total_messages_sent)::bigint as total_messages_sent,
    SUM(fc.paid_messages_count)::bigint as paid_messages_count,
    SUM(fc.total_cost) as total_cost,
    CASE 
      WHEN SUM(fc.paid_messages_count) > 0 
      THEN SUM(fc.total_cost) / SUM(fc.paid_messages_count)
      ELSE 0::numeric
    END as avg_cost_per_message,
    MIN(fc.avg_cost_per_message) FILTER (WHERE fc.paid_messages_count > 0) as min_cost,
    MAX(fc.avg_cost_per_message) FILTER (WHERE fc.paid_messages_count > 0) as max_cost
  FROM filtered_costs fc
  GROUP BY fc.week_start, fc.year, fc.week_number
  ORDER BY fc.week_start DESC;
END;
$$;

-- Fonction pour obtenir les coûts hebdomadaires par compte
-- Retourne seulement les comptes auxquels l'utilisateur a accès
CREATE OR REPLACE FUNCTION get_message_costs_weekly_by_account_secure()
RETURNS TABLE (
  account_id uuid,
  account_name text,
  week_start date,
  year double precision,
  week_number double precision,
  total_messages_sent bigint,
  paid_messages_count bigint,
  total_cost numeric,
  avg_cost_per_message numeric
)
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
AS $$
BEGIN
  -- Service role peut tout voir
  IF auth.role() = 'service_role' THEN
    RETURN QUERY
    SELECT *
    FROM message_costs_weekly_by_account;
    RETURN;
  END IF;

  -- Pour les utilisateurs authentifiés, retourner seulement les comptes
  -- auxquels ils ont accès (user_has_account_access gère déjà access_level = 'aucun')
  RETURN QUERY
  SELECT mcwa.*
  FROM message_costs_weekly_by_account mcwa
  WHERE is_user_active()
    AND user_has_account_access(mcwa.account_id)
  ORDER BY mcwa.week_start DESC, mcwa.account_name;
END;
$$;

-- ============================================
-- NOTES IMPORTANTES
-- ============================================
--
-- 1. Le backend utilise service_role qui bypass toutes les politiques RLS
--    → Aucun impact sur le fonctionnement actuel
--
-- 2. Le frontend utilise anon key et sera soumis à ces politiques
--    → Protection automatique des données côté client
--
-- 3. Les webhooks utilisent service_role via le backend
--    → Continuent de fonctionner normalement
--
-- 4. Les utilisateurs doivent avoir des rôles assignés pour accéder aux données
--    → Le système auto-assigne "viewer" par défaut (voir permissions.py)
--
-- 5. Les permissions sont vérifiées à deux niveaux:
--    - Global: permission sur tous les accounts
--    - Par account: permission spécifique à un account
--
-- 6. Pour tester les politiques:
--    - Connectez-vous avec un utilisateur normal (anon key)
--    - Vérifiez que vous ne voyez que les données autorisées
--    - Le backend continue de fonctionner normalement (service_role)
--
-- ============================================

