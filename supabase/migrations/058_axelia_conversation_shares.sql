-- Partage de discussions Axelia (lecture seule)
-- Permet de partager un fil à un collègue sans lui donner le droit d'écrire.

CREATE TABLE IF NOT EXISTS axelia_conversation_shares (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid NOT NULL REFERENCES axelia_conversations(id) ON DELETE CASCADE,
  owner_user_id uuid NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
  shared_with_user_id uuid NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
  warning_message text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (conversation_id, shared_with_user_id)
);

CREATE INDEX IF NOT EXISTS idx_axelia_shares_shared_with
  ON axelia_conversation_shares(shared_with_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_axelia_shares_owner_conv
  ON axelia_conversation_shares(owner_user_id, conversation_id);

COMMENT ON TABLE axelia_conversation_shares IS 'Partages de conversations Axelia en lecture seule.';
