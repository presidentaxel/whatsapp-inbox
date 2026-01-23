-- Migration: Ajouter le champ is_system pour masquer les messages système dans l'interface
-- Les messages système (notifications d'épinglage, etc.) sont envoyés mais ne doivent pas être visibles côté utilisateur

ALTER TABLE messages
ADD COLUMN IF NOT EXISTS is_system BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_messages_is_system ON messages(conversation_id, is_system) WHERE is_system = TRUE;

COMMENT ON COLUMN messages.is_system IS 
  'Indique si le message est un message système (notifications d''épinglage, etc.) qui ne doit pas être affiché dans l''interface';

