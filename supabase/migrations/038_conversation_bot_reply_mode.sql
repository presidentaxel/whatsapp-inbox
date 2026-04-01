-- Mode de réponse auto par conversation : playbook Gemini vs graphe Playground
ALTER TABLE conversations
  ADD COLUMN IF NOT EXISTS bot_reply_mode text NOT NULL DEFAULT 'gemini';

COMMENT ON COLUMN conversations.bot_reply_mode IS
  'gemini | playground — utilisé seulement lorsque bot_enabled = true';
