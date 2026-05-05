-- Migration pour ajouter le support de déduplication des templates
-- Permet de réutiliser les templates existants au lieu d'en créer de nouveaux

-- Ajouter une colonne pour stocker le hash normalisé du template (pour comparaison rapide)
ALTER TABLE pending_template_messages 
  ADD COLUMN IF NOT EXISTS template_hash TEXT;

-- Ajouter une colonne pour référencer le template original si celui-ci est réutilisé
ALTER TABLE pending_template_messages 
  ADD COLUMN IF NOT EXISTS reused_from_template UUID REFERENCES pending_template_messages(id) ON DELETE SET NULL;

-- Ajouter une colonne campaign_id si elle n'existe pas déjà (utilisée pour les broadcasts)
ALTER TABLE pending_template_messages 
  ADD COLUMN IF NOT EXISTS campaign_id UUID;

-- Index pour accélérer la recherche de templates similaires par hash
CREATE INDEX IF NOT EXISTS idx_pending_templates_hash 
ON pending_template_messages(template_hash, account_id)
WHERE template_hash IS NOT NULL;

-- Index pour la recherche par account_id et status (déjà peut-être présent, mais on s'assure)
CREATE INDEX IF NOT EXISTS idx_pending_templates_account_status 
ON pending_template_messages(account_id, template_status);

-- Index pour la recherche par campaign_id
CREATE INDEX IF NOT EXISTS idx_pending_templates_campaign 
ON pending_template_messages(campaign_id)
WHERE campaign_id IS NOT NULL;

-- Commentaires pour la documentation
COMMENT ON COLUMN pending_template_messages.template_hash IS 'Hash MD5 du texte normalisé du template pour détecter les doublons';
COMMENT ON COLUMN pending_template_messages.reused_from_template IS 'Référence au template original si ce template est une réutilisation';
COMMENT ON COLUMN pending_template_messages.campaign_id IS 'ID de la campagne broadcast si ce template est utilisé pour une campagne';

