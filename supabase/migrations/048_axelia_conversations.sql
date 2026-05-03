-- Conversations Axelia (hub IA interne) - historique par utilisateur
-- hidden_at : la conv n’apparaît plus pour l’utilisateur (données conservées)

CREATE TABLE IF NOT EXISTS axelia_conversations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
  account_context text NOT NULL DEFAULT '__all__',
  title text NOT NULL DEFAULT 'Nouvelle discussion',
  pinned boolean NOT NULL DEFAULT false,
  hidden_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_axelia_conversations_user_active
  ON axelia_conversations(user_id, updated_at DESC)
  WHERE hidden_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_axelia_conversations_user_pinned
  ON axelia_conversations(user_id, pinned DESC, updated_at DESC)
  WHERE hidden_at IS NULL;

CREATE TABLE IF NOT EXISTS axelia_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid NOT NULL REFERENCES axelia_conversations(id) ON DELETE CASCADE,
  role text NOT NULL CHECK (role IN ('user', 'model')),
  content_text text NOT NULL DEFAULT '',
  rating smallint CHECK (rating IS NULL OR rating IN (-1, 1)),
  model_used text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_axelia_messages_conversation
  ON axelia_messages(conversation_id, created_at);

COMMENT ON TABLE axelia_conversations IS 'Fils Axelia par utilisateur ; hidden_at = masqué côté UI';
COMMENT ON COLUMN axelia_messages.rating IS '1 = pouce haut, -1 = pouce bas, NULL = pas de vote';
