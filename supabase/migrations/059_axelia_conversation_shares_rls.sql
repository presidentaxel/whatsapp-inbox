-- ============================================
-- Migration 059 : RLS pour axelia_conversation_shares
-- ============================================
-- Objectif :
-- - owner voit et gère ses partages
-- - destinataire voit uniquement les partages qui le concernent
-- - service_role conserve le bypass opérationnel backend

ALTER TABLE axelia_conversation_shares ENABLE ROW LEVEL SECURITY;

-- Lecture : owner OU destinataire (ou service_role)
DROP POLICY IF EXISTS "axelia_shares_select" ON axelia_conversation_shares;
CREATE POLICY "axelia_shares_select" ON axelia_conversation_shares
  FOR SELECT
  USING (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND (
        owner_user_id = auth.uid()
        OR shared_with_user_id = auth.uid()
      )
    )
  );

-- Insertion : owner uniquement (ou service_role)
-- Défense en profondeur : owner doit aussi être propriétaire de la conversation.
DROP POLICY IF EXISTS "axelia_shares_insert" ON axelia_conversation_shares;
CREATE POLICY "axelia_shares_insert" ON axelia_conversation_shares
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND owner_user_id = auth.uid()
      AND EXISTS (
        SELECT 1
        FROM axelia_conversations c
        WHERE c.id = conversation_id
          AND c.user_id = auth.uid()
      )
    )
  );

-- Update : owner uniquement (ou service_role)
DROP POLICY IF EXISTS "axelia_shares_update" ON axelia_conversation_shares;
CREATE POLICY "axelia_shares_update" ON axelia_conversation_shares
  FOR UPDATE
  USING (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND owner_user_id = auth.uid()
    )
  )
  WITH CHECK (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND owner_user_id = auth.uid()
      AND EXISTS (
        SELECT 1
        FROM axelia_conversations c
        WHERE c.id = conversation_id
          AND c.user_id = auth.uid()
      )
    )
  );

-- Suppression : owner uniquement (ou service_role)
DROP POLICY IF EXISTS "axelia_shares_delete" ON axelia_conversation_shares;
CREATE POLICY "axelia_shares_delete" ON axelia_conversation_shares
  FOR DELETE
  USING (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND owner_user_id = auth.uid()
    )
  );
