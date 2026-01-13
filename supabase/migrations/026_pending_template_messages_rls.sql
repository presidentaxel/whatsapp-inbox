-- ============================================
-- Migration: RLS pour pending_template_messages
-- Date: 2025-01-XX
-- Description: Active Row Level Security sur pending_template_messages
--              avec des politiques basées sur l'accès aux messages/conversations
-- ============================================

-- Activation RLS sur la table
ALTER TABLE pending_template_messages ENABLE ROW LEVEL SECURITY;

-- ============================================
-- POLITIQUES: PENDING_TEMPLATE_MESSAGES
-- ============================================

-- SELECT: Voir les pending_template_messages si on a messages.view pour l'account
-- On vérifie l'accès via la conversation associée (comme pour messages)
DROP POLICY IF EXISTS "pending_template_messages_select" ON pending_template_messages;
CREATE POLICY "pending_template_messages_select" ON pending_template_messages
  FOR SELECT
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      (
        -- Vérifier l'accès via la conversation
        EXISTS (
          SELECT 1
          FROM conversations c
          WHERE c.id = pending_template_messages.conversation_id
            AND (
              user_has_global_permission('messages.view') OR
              user_has_account_permission('messages.view', c.account_id)
            )
        )
        -- Ou vérifier l'accès via le message directement
        OR EXISTS (
          SELECT 1
          FROM messages m
          JOIN conversations c ON c.id = m.conversation_id
          WHERE m.id = pending_template_messages.message_id
            AND (
              user_has_global_permission('messages.view') OR
              user_has_account_permission('messages.view', c.account_id)
            )
        )
        -- Ou vérifier l'accès via l'account directement
        OR (
          pending_template_messages.account_id IS NOT NULL AND
          (
            user_has_global_permission('messages.view') OR
            user_has_account_permission('messages.view', pending_template_messages.account_id)
          )
        )
      )
    )
  );

-- INSERT: Créer des pending_template_messages si on peut envoyer des messages
-- (même logique que messages.insert)
DROP POLICY IF EXISTS "pending_template_messages_insert" ON pending_template_messages;
CREATE POLICY "pending_template_messages_insert" ON pending_template_messages
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      (
        -- Vérifier l'accès via la conversation
        EXISTS (
          SELECT 1
          FROM conversations c
          WHERE c.id = pending_template_messages.conversation_id
            AND (
              user_has_global_permission('messages.send') OR
              user_has_account_permission('messages.send', c.account_id)
            )
        )
        -- Ou vérifier l'accès via le message directement
        OR EXISTS (
          SELECT 1
          FROM messages m
          JOIN conversations c ON c.id = m.conversation_id
          WHERE m.id = pending_template_messages.message_id
            AND (
              user_has_global_permission('messages.send') OR
              user_has_account_permission('messages.send', c.account_id)
            )
        )
        -- Ou vérifier l'accès via l'account directement
        OR (
          pending_template_messages.account_id IS NOT NULL AND
          (
            user_has_global_permission('messages.send') OR
            user_has_account_permission('messages.send', pending_template_messages.account_id)
          )
        )
      )
    )
  );

-- UPDATE: Modifier des pending_template_messages si on a messages.view pour l'account
-- (même logique que messages.update)
DROP POLICY IF EXISTS "pending_template_messages_update" ON pending_template_messages;
CREATE POLICY "pending_template_messages_update" ON pending_template_messages
  FOR UPDATE
  USING (
    auth.role() = 'service_role' OR
    (
      is_user_active() AND
      (
        -- Vérifier l'accès via la conversation
        EXISTS (
          SELECT 1
          FROM conversations c
          WHERE c.id = pending_template_messages.conversation_id
            AND (
              user_has_global_permission('messages.view') OR
              user_has_account_permission('messages.view', c.account_id)
            )
        )
        -- Ou vérifier l'accès via le message directement
        OR EXISTS (
          SELECT 1
          FROM messages m
          JOIN conversations c ON c.id = m.conversation_id
          WHERE m.id = pending_template_messages.message_id
            AND (
              user_has_global_permission('messages.view') OR
              user_has_account_permission('messages.view', c.account_id)
            )
        )
        -- Ou vérifier l'accès via l'account directement
        OR (
          pending_template_messages.account_id IS NOT NULL AND
          (
            user_has_global_permission('messages.view') OR
            user_has_account_permission('messages.view', pending_template_messages.account_id)
          )
        )
      )
    )
  );

-- DELETE: Supprimer des pending_template_messages (admin seulement, comme messages.delete)
DROP POLICY IF EXISTS "pending_template_messages_delete" ON pending_template_messages;
CREATE POLICY "pending_template_messages_delete" ON pending_template_messages
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    (is_user_active() AND user_has_global_permission('accounts.manage'))
  );

-- ============================================
-- NOTES
-- ============================================
-- 
-- 1. Les politiques suivent le même pattern que les messages
-- 2. Le backend (service_role) peut tout faire (bypass RLS)
-- 3. Les utilisateurs authentifiés accèdent selon leurs permissions RBAC
-- 4. Protection multi-tenant basée sur account_id via conversations
-- 5. Les vérifications se font via conversation_id, message_id ou account_id
--    pour couvrir tous les cas d'usage
--
-- ============================================

