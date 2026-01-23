-- Ajouter une colonne pour stocker le media_id des templates avec image en HEADER
ALTER TABLE pending_template_messages
ADD COLUMN IF NOT EXISTS header_media_id TEXT;

COMMENT ON COLUMN pending_template_messages.header_media_id IS 'Media ID WhatsApp pour les templates avec HEADER IMAGE';

