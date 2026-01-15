-- Migration: Ajouter le champ is_pinned pour épingler des messages
-- Date: 2024

ALTER TABLE messages
  ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN DEFAULT FALSE;

-- Créer un index pour améliorer les performances lors de la récupération des messages épinglés
CREATE INDEX IF NOT EXISTS idx_messages_is_pinned ON messages(conversation_id, is_pinned) WHERE is_pinned = TRUE;

-- Commentaire pour documenter le champ
COMMENT ON COLUMN messages.is_pinned IS 'Indique si le message est épinglé dans la conversation';

