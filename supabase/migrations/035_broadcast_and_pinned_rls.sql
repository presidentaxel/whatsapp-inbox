-- ============================================
-- Migration: RLS pour les tables broadcast et pinned_message_notifications
-- Date: 2025-01-XX
-- Description: Active Row Level Security sur les tables de broadcast et pinned notifications
--              avec des politiques basées sur l'accès aux accounts (conversations.view/messages.send)
-- ============================================

-- ============================================
-- ACTIVATION RLS SUR LES TABLES
-- ============================================

ALTER TABLE broadcast_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE broadcast_group_recipients ENABLE ROW LEVEL SECURITY;
ALTER TABLE broadcast_campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE broadcast_recipient_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE pinned_message_notifications ENABLE ROW LEVEL SECURITY;

-- ============================================
-- POLITIQUES: BROADCAST_GROUPS
-- ============================================

-- SELECT: Voir les groupes si on a conversations.view pour l'account
DROP POLICY IF EXISTS "broadcast_groups_select" ON broadcast_groups;
CREATE POLICY "broadcast_groups_select" ON broadcast_groups
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

-- INSERT: Créer des groupes si on a messages.send pour l'account
DROP POLICY IF EXISTS "broadcast_groups_insert" ON broadcast_groups;
CREATE POLICY "broadcast_groups_insert" ON broadcast_groups
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      (
        user_has_global_permission('messages.send') OR
        user_has_account_permission('messages.send', account_id)
      )
    )
  );

-- UPDATE: Modifier des groupes si on a messages.send pour l'account
DROP POLICY IF EXISTS "broadcast_groups_update" ON broadcast_groups;
CREATE POLICY "broadcast_groups_update" ON broadcast_groups
  FOR UPDATE
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      (
        user_has_global_permission('messages.send') OR
        user_has_account_permission('messages.send', account_id)
      )
    )
  );

-- DELETE: Supprimer des groupes si on a messages.send pour l'account
DROP POLICY IF EXISTS "broadcast_groups_delete" ON broadcast_groups;
CREATE POLICY "broadcast_groups_delete" ON broadcast_groups
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      (
        user_has_global_permission('messages.send') OR
        user_has_account_permission('messages.send', account_id)
      )
    )
  );

-- ============================================
-- POLITIQUES: BROADCAST_GROUP_RECIPIENTS
-- ============================================

-- SELECT: Voir les destinataires si on a conversations.view pour l'account du groupe
DROP POLICY IF EXISTS "broadcast_group_recipients_select" ON broadcast_group_recipients;
CREATE POLICY "broadcast_group_recipients_select" ON broadcast_group_recipients
  FOR SELECT
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      EXISTS (
        SELECT 1
        FROM broadcast_groups bg
        WHERE bg.id = broadcast_group_recipients.group_id
          AND (
            user_has_global_permission('conversations.view') OR
            user_has_account_permission('conversations.view', bg.account_id)
          )
      )
    )
  );

-- INSERT: Ajouter des destinataires si on a messages.send pour l'account du groupe
DROP POLICY IF EXISTS "broadcast_group_recipients_insert" ON broadcast_group_recipients;
CREATE POLICY "broadcast_group_recipients_insert" ON broadcast_group_recipients
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      EXISTS (
        SELECT 1
        FROM broadcast_groups bg
        WHERE bg.id = broadcast_group_recipients.group_id
          AND (
            user_has_global_permission('messages.send') OR
            user_has_account_permission('messages.send', bg.account_id)
          )
      )
    )
  );

-- UPDATE: Modifier des destinataires si on a messages.send pour l'account du groupe
DROP POLICY IF EXISTS "broadcast_group_recipients_update" ON broadcast_group_recipients;
CREATE POLICY "broadcast_group_recipients_update" ON broadcast_group_recipients
  FOR UPDATE
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      EXISTS (
        SELECT 1
        FROM broadcast_groups bg
        WHERE bg.id = broadcast_group_recipients.group_id
          AND (
            user_has_global_permission('messages.send') OR
            user_has_account_permission('messages.send', bg.account_id)
          )
      )
    )
  );

-- DELETE: Retirer des destinataires si on a messages.send pour l'account du groupe
DROP POLICY IF EXISTS "broadcast_group_recipients_delete" ON broadcast_group_recipients;
CREATE POLICY "broadcast_group_recipients_delete" ON broadcast_group_recipients
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      EXISTS (
        SELECT 1
        FROM broadcast_groups bg
        WHERE bg.id = broadcast_group_recipients.group_id
          AND (
            user_has_global_permission('messages.send') OR
            user_has_account_permission('messages.send', bg.account_id)
          )
      )
    )
  );

-- ============================================
-- POLITIQUES: BROADCAST_CAMPAIGNS
-- ============================================

-- SELECT: Voir les campagnes si on a conversations.view pour l'account
DROP POLICY IF EXISTS "broadcast_campaigns_select" ON broadcast_campaigns;
CREATE POLICY "broadcast_campaigns_select" ON broadcast_campaigns
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

-- INSERT: Créer des campagnes si on a messages.send pour l'account
DROP POLICY IF EXISTS "broadcast_campaigns_insert" ON broadcast_campaigns;
CREATE POLICY "broadcast_campaigns_insert" ON broadcast_campaigns
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      (
        user_has_global_permission('messages.send') OR
        user_has_account_permission('messages.send', account_id)
      )
    )
  );

-- UPDATE: Modifier des campagnes si on a conversations.view pour l'account
-- (pour mettre à jour les compteurs, etc.)
DROP POLICY IF EXISTS "broadcast_campaigns_update" ON broadcast_campaigns;
CREATE POLICY "broadcast_campaigns_update" ON broadcast_campaigns
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

-- DELETE: Supprimer des campagnes (admin seulement, comme messages.delete)
DROP POLICY IF EXISTS "broadcast_campaigns_delete" ON broadcast_campaigns;
CREATE POLICY "broadcast_campaigns_delete" ON broadcast_campaigns
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('accounts.manage'))
  );

-- ============================================
-- POLITIQUES: BROADCAST_RECIPIENT_STATS
-- ============================================

-- SELECT: Voir les stats si on a conversations.view pour l'account de la campagne
DROP POLICY IF EXISTS "broadcast_recipient_stats_select" ON broadcast_recipient_stats;
CREATE POLICY "broadcast_recipient_stats_select" ON broadcast_recipient_stats
  FOR SELECT
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      EXISTS (
        SELECT 1
        FROM broadcast_campaigns bc
        WHERE bc.id = broadcast_recipient_stats.campaign_id
          AND (
            user_has_global_permission('conversations.view') OR
            user_has_account_permission('conversations.view', bc.account_id)
          )
      )
    )
  );

-- INSERT: Créer des stats si on a messages.send pour l'account de la campagne
-- (généralement fait par le backend lors de l'envoi)
DROP POLICY IF EXISTS "broadcast_recipient_stats_insert" ON broadcast_recipient_stats;
CREATE POLICY "broadcast_recipient_stats_insert" ON broadcast_recipient_stats
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      EXISTS (
        SELECT 1
        FROM broadcast_campaigns bc
        WHERE bc.id = broadcast_recipient_stats.campaign_id
          AND (
            user_has_global_permission('messages.send') OR
            user_has_account_permission('messages.send', bc.account_id)
          )
      )
    )
  );

-- UPDATE: Modifier des stats si on a conversations.view pour l'account de la campagne
-- (pour mettre à jour les statuts delivered, read, replied, etc.)
DROP POLICY IF EXISTS "broadcast_recipient_stats_update" ON broadcast_recipient_stats;
CREATE POLICY "broadcast_recipient_stats_update" ON broadcast_recipient_stats
  FOR UPDATE
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      EXISTS (
        SELECT 1
        FROM broadcast_campaigns bc
        WHERE bc.id = broadcast_recipient_stats.campaign_id
          AND (
            user_has_global_permission('conversations.view') OR
            user_has_account_permission('conversations.view', bc.account_id)
          )
      )
    )
  );

-- DELETE: Supprimer des stats (admin seulement)
DROP POLICY IF EXISTS "broadcast_recipient_stats_delete" ON broadcast_recipient_stats;
CREATE POLICY "broadcast_recipient_stats_delete" ON broadcast_recipient_stats
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('accounts.manage'))
  );

-- ============================================
-- POLITIQUES: PINNED_MESSAGE_NOTIFICATIONS
-- ============================================

-- SELECT: Voir les notifications si on a messages.view pour l'account de la conversation
DROP POLICY IF EXISTS "pinned_message_notifications_select" ON pinned_message_notifications;
CREATE POLICY "pinned_message_notifications_select" ON pinned_message_notifications
  FOR SELECT
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      EXISTS (
        SELECT 1
        FROM conversations c
        WHERE c.id = pinned_message_notifications.conversation_id
          AND (
            user_has_global_permission('messages.view') OR
            user_has_account_permission('messages.view', c.account_id)
          )
      )
    )
  );

-- INSERT: Créer des notifications si on a messages.send pour l'account de la conversation
DROP POLICY IF EXISTS "pinned_message_notifications_insert" ON pinned_message_notifications;
CREATE POLICY "pinned_message_notifications_insert" ON pinned_message_notifications
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      EXISTS (
        SELECT 1
        FROM conversations c
        WHERE c.id = pinned_message_notifications.conversation_id
          AND (
            user_has_global_permission('messages.send') OR
            user_has_account_permission('messages.send', c.account_id)
          )
      )
    )
  );

-- UPDATE: Modifier des notifications si on a messages.view pour l'account de la conversation
-- (pour mettre à jour le statut, sent_at, etc.)
DROP POLICY IF EXISTS "pinned_message_notifications_update" ON pinned_message_notifications;
CREATE POLICY "pinned_message_notifications_update" ON pinned_message_notifications
  FOR UPDATE
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      EXISTS (
        SELECT 1
        FROM conversations c
        WHERE c.id = pinned_message_notifications.conversation_id
          AND (
            user_has_global_permission('messages.view') OR
            user_has_account_permission('messages.view', c.account_id)
          )
      )
    )
  );

-- DELETE: Supprimer des notifications (admin seulement)
DROP POLICY IF EXISTS "pinned_message_notifications_delete" ON pinned_message_notifications;
CREATE POLICY "pinned_message_notifications_delete" ON pinned_message_notifications
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('accounts.manage'))
  );

-- ============================================
-- NOTES
-- ============================================
-- 
-- 1. Les politiques suivent le même pattern que les autres tables (messages, conversations)
-- 2. Le backend (service_role) peut tout faire (bypass RLS)
-- 3. Les utilisateurs authentifiés accèdent selon leurs permissions RBAC
-- 4. Protection multi-tenant basée sur account_id
-- 5. Pour les tables broadcast:
--    - SELECT/UPDATE: conversations.view (pour voir les données)
--    - INSERT/DELETE: messages.send (pour créer/supprimer)
-- 6. Pour pinned_message_notifications:
--    - Accès via conversation_id (comme pour messages)
--    - SELECT/UPDATE: messages.view
--    - INSERT: messages.send
-- 7. Les DELETE sont généralement réservés aux admins (accounts.manage)
--
-- ============================================

