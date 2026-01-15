-- Migration pour ajouter le support des campagnes broadcast dans pending_template_messages
-- Permet de créer un seul template pour une campagne et de l'envoyer à tous les destinataires

-- Ajouter campaign_id à pending_template_messages
ALTER TABLE pending_template_messages
  ADD COLUMN IF NOT EXISTS campaign_id UUID REFERENCES broadcast_campaigns(id) ON DELETE CASCADE;

-- Index pour les recherches par campagne
CREATE INDEX IF NOT EXISTS idx_pending_templates_campaign 
ON pending_template_messages(campaign_id) 
WHERE campaign_id IS NOT NULL;

-- Commentaire
COMMENT ON COLUMN pending_template_messages.campaign_id IS 'ID de la campagne broadcast si ce template est pour un envoi groupé';

