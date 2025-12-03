-- ============================================
-- Migration: Table pour les réactions aux messages
-- Date: 2025-01-XX
-- Description: Permet de stocker les réactions (emoji) sur les messages
-- ============================================

-- Table pour stocker les réactions
CREATE TABLE IF NOT EXISTS message_reactions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  wa_message_id text UNIQUE, -- ID du message de réaction WhatsApp
  emoji text NOT NULL,
  from_number text NOT NULL, -- Numéro WhatsApp de la personne qui a réagi
  created_at timestamptz DEFAULT now(),
  UNIQUE(message_id, from_number, emoji) -- Une personne ne peut réagir qu'une fois avec le même emoji
);

-- Index pour les performances
CREATE INDEX IF NOT EXISTS idx_message_reactions_message_id ON message_reactions(message_id);
CREATE INDEX IF NOT EXISTS idx_message_reactions_wa_message_id ON message_reactions(wa_message_id);

-- Commentaires
COMMENT ON TABLE message_reactions IS 'Réactions (emoji) sur les messages WhatsApp';
COMMENT ON COLUMN message_reactions.message_id IS 'Message auquel la réaction est attachée';
COMMENT ON COLUMN message_reactions.wa_message_id IS 'ID du message de réaction reçu de WhatsApp';
COMMENT ON COLUMN message_reactions.emoji IS 'Emoji de la réaction';
COMMENT ON COLUMN message_reactions.from_number IS 'Numéro WhatsApp de la personne qui a réagi';

-- Activer RLS
ALTER TABLE message_reactions ENABLE ROW LEVEL SECURITY;

-- Politique RLS: Les utilisateurs peuvent voir les réactions des messages qu'ils peuvent voir
CREATE POLICY "message_reactions_select" ON message_reactions
  FOR SELECT
  USING (
    auth.role() = 'service_role' OR
    EXISTS (
      SELECT 1
      FROM messages m
      JOIN conversations c ON c.id = m.conversation_id
      WHERE m.id = message_reactions.message_id
        AND (
          user_has_global_permission('messages.view') OR
          user_has_account_permission('messages.view', c.account_id)
        )
    )
  );

-- Politique RLS: Les utilisateurs peuvent ajouter des réactions aux messages qu'ils peuvent voir
CREATE POLICY "message_reactions_insert" ON message_reactions
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role' OR
    EXISTS (
      SELECT 1
      FROM messages m
      JOIN conversations c ON c.id = m.conversation_id
      WHERE m.id = message_reactions.message_id
        AND (
          user_has_global_permission('messages.view') OR
          user_has_account_permission('messages.view', c.account_id)
        )
    )
  );

-- Politique RLS: Les utilisateurs peuvent supprimer leurs propres réactions ou si admin
CREATE POLICY "message_reactions_delete" ON message_reactions
  FOR DELETE
  USING (
    auth.role() = 'service_role' OR
    user_has_global_permission('accounts.manage') OR
    -- Note: On ne peut pas facilement vérifier si c'est l'utilisateur actuel car from_number
    -- n'est pas lié à auth.uid(). Pour l'instant, on permet la suppression si on peut voir le message.
    EXISTS (
      SELECT 1
      FROM messages m
      JOIN conversations c ON c.id = m.conversation_id
      WHERE m.id = message_reactions.message_id
        AND (
          user_has_global_permission('messages.view') OR
          user_has_account_permission('messages.view', c.account_id)
        )
    )
  );

