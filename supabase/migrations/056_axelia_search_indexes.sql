-- Index pour accélérer les recherches Axelia / inbox (ILIKE, recherche contact)
-- Nécessite pg_trgm (généralement disponible sur Supabase / Postgres 12+).

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Messages texte : filtres ILIKE sur content_text (mot au milieu du texte)
CREATE INDEX IF NOT EXISTS idx_messages_content_text_trgm
ON messages
USING gin (content_text gin_trgm_ops)
WHERE message_type = 'text' AND COALESCE(content_text, '') <> '';

COMMENT ON INDEX idx_messages_content_text_trgm IS
  'Axelia search_inbox_messages : ILIKE sur body texte';

-- Contacts : recherche par nom / pseudo WhatsApp / numéro (substring)
CREATE INDEX IF NOT EXISTS idx_contacts_display_name_trgm
ON contacts USING gin (display_name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_contacts_whatsapp_name_trgm
ON contacts USING gin (whatsapp_name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_contacts_whatsapp_number_trgm
ON contacts USING gin (whatsapp_number gin_trgm_ops);

-- Conversations : client_number pour summarize_contact_inbox (ILIKE)
CREATE INDEX IF NOT EXISTS idx_conversations_client_number_trgm
ON conversations USING gin (client_number gin_trgm_ops);

ANALYZE messages;
ANALYZE contacts;
ANALYZE conversations;
