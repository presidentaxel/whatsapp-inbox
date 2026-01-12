-- Migration pour gérer les templates en attente de validation Meta
-- Permet de créer automatiquement des templates et d'attendre leur validation

-- Table pour suivre les templates en attente
CREATE TABLE IF NOT EXISTS pending_template_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id UUID REFERENCES messages(id) ON DELETE CASCADE,
  conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
  account_id UUID REFERENCES whatsapp_accounts(id) ON DELETE CASCADE,
  template_name TEXT NOT NULL,
  template_status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING, APPROVED, REJECTED
  text_content TEXT NOT NULL,
  meta_template_id TEXT, -- ID retourné par Meta
  rejection_reason TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Index pour les recherches fréquentes
CREATE INDEX IF NOT EXISTS idx_pending_templates_status 
ON pending_template_messages(template_status) 
WHERE template_status = 'PENDING';

CREATE INDEX IF NOT EXISTS idx_pending_templates_message 
ON pending_template_messages(message_id);

CREATE INDEX IF NOT EXISTS idx_pending_templates_meta_id 
ON pending_template_messages(meta_template_id) 
WHERE meta_template_id IS NOT NULL;

-- S'assurer que error_message existe dans messages (au cas où la migration 014 n'a pas été appliquée)
ALTER TABLE messages
  ADD COLUMN IF NOT EXISTS error_message TEXT;

-- Commentaires pour la documentation
COMMENT ON TABLE pending_template_messages IS 'Table pour suivre les templates créés automatiquement en attente de validation Meta';
COMMENT ON COLUMN pending_template_messages.template_status IS 'Statut du template: PENDING (en attente), APPROVED (approuvé), REJECTED (rejeté)';
COMMENT ON COLUMN pending_template_messages.meta_template_id IS 'ID du template retourné par l''API Meta';
COMMENT ON COLUMN pending_template_messages.rejection_reason IS 'Raison du rejet si le template est rejeté par Meta';

