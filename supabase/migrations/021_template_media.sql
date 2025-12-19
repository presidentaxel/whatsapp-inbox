-- Créer la table pour stocker les métadonnées des images de templates
CREATE TABLE IF NOT EXISTS template_media (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_name TEXT NOT NULL,
    template_language TEXT NOT NULL,
    account_id UUID NOT NULL REFERENCES whatsapp_accounts(id) ON DELETE CASCADE,
    media_type TEXT NOT NULL CHECK (media_type IN ('IMAGE', 'VIDEO', 'DOCUMENT')),
    storage_url TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    mime_type TEXT,
    file_size BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(template_name, template_language, account_id, media_type)
);

-- Index pour recherche rapide
CREATE INDEX IF NOT EXISTS idx_template_media_template ON template_media(template_name, template_language, account_id);
CREATE INDEX IF NOT EXISTS idx_template_media_account ON template_media(account_id);

-- Trigger pour mettre à jour updated_at
CREATE OR REPLACE FUNCTION update_template_media_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_template_media_updated_at
    BEFORE UPDATE ON template_media
    FOR EACH ROW
    EXECUTE FUNCTION update_template_media_updated_at();

-- RLS Policies
ALTER TABLE template_media ENABLE ROW LEVEL SECURITY;

-- Permettre la lecture pour les utilisateurs authentifiés
CREATE POLICY "Authenticated users can read template media"
ON template_media FOR SELECT
USING (auth.role() = 'authenticated');

-- Permettre l'insertion pour les utilisateurs authentifiés
CREATE POLICY "Authenticated users can insert template media"
ON template_media FOR INSERT
WITH CHECK (auth.role() = 'authenticated');

-- Permettre la mise à jour pour les utilisateurs authentifiés
CREATE POLICY "Authenticated users can update template media"
ON template_media FOR UPDATE
USING (auth.role() = 'authenticated');

-- Permettre la suppression pour les utilisateurs authentifiés
CREATE POLICY "Authenticated users can delete template media"
ON template_media FOR DELETE
USING (auth.role() = 'authenticated');

