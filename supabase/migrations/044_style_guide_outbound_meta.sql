-- Guide de style global pour l’IA + métadonnées de provenance des messages sortants

ALTER TABLE bot_profiles
  ADD COLUMN IF NOT EXISTS style_guide TEXT;

COMMENT ON COLUMN bot_profiles.style_guide IS
  'Consignes de ton / longueur / interdits appliquées aux réponses Gemini (assistant et nœuds flux).';

ALTER TABLE messages
  ADD COLUMN IF NOT EXISTS outbound_meta JSONB;

COMMENT ON COLUMN messages.outbound_meta IS
  'Détails source envoi sortant (scénario, nœud, type IA) pour l’affichage dans l’inbox.';

CREATE INDEX IF NOT EXISTS idx_messages_outbound_meta
  ON messages USING gin (outbound_meta jsonb_path_ops)
  WHERE outbound_meta IS NOT NULL;
