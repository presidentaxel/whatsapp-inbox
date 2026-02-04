-- Migration: Traçabilité - qui a envoyé un message, qui a créé un template, journal d'audit
-- Permet de savoir qui a envoyé un message depuis l'app, source d'envoi, et journaliser les actions

-- 1. Messages: qui a envoyé (depuis l'app) et via quel canal
ALTER TABLE messages
  ADD COLUMN IF NOT EXISTS sent_by_user_id UUID REFERENCES app_users(user_id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS sent_via TEXT;

CREATE INDEX IF NOT EXISTS idx_messages_sent_by_user_id ON messages(sent_by_user_id) WHERE sent_by_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_messages_sent_via ON messages(sent_via) WHERE sent_via IS NOT NULL;

COMMENT ON COLUMN messages.sent_by_user_id IS 'Utilisateur ayant envoyé le message depuis l''app (NULL = webhook, bot, système)';
COMMENT ON COLUMN messages.sent_via IS 'Canal d''envoi: ui, api, broadcast, bot, system';

-- 2. Pending template messages: qui a demandé la création du template
ALTER TABLE pending_template_messages
  ADD COLUMN IF NOT EXISTS created_by_user_id UUID REFERENCES app_users(user_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_pending_template_messages_created_by ON pending_template_messages(created_by_user_id) WHERE created_by_user_id IS NOT NULL;

COMMENT ON COLUMN pending_template_messages.created_by_user_id IS 'Utilisateur ayant demandé l''envoi (template en attente)';

-- 3. Table d'audit pour les actions importantes
CREATE TABLE IF NOT EXISTS audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ DEFAULT now(),
  user_id UUID REFERENCES app_users(user_id) ON DELETE SET NULL,
  account_id UUID REFERENCES whatsapp_accounts(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT,
  details JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_log_account_id ON audit_log(account_id) WHERE account_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource ON audit_log(resource_type, resource_id);

COMMENT ON TABLE audit_log IS 'Journal des actions pour traçabilité (envoi, édition, suppression de messages, etc.)';
