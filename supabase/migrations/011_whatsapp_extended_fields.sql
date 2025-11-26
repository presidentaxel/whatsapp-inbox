-- Migration pour ajouter les champs étendus de l'API WhatsApp Business
-- Ces champs permettent d'utiliser toutes les fonctionnalités de l'API Cloud

-- Ajouter les nouveaux champs à la table whatsapp_accounts
ALTER TABLE whatsapp_accounts
  ADD COLUMN IF NOT EXISTS waba_id TEXT,
  ADD COLUMN IF NOT EXISTS business_id TEXT,
  ADD COLUMN IF NOT EXISTS app_id TEXT,
  ADD COLUMN IF NOT EXISTS app_secret TEXT;

-- Ajouter des commentaires pour documenter les champs
COMMENT ON COLUMN whatsapp_accounts.waba_id IS 'WhatsApp Business Account ID - nécessaire pour gérer les templates et les webhooks';
COMMENT ON COLUMN whatsapp_accounts.business_id IS 'Meta Business Manager ID - nécessaire pour lister les WABAs';
COMMENT ON COLUMN whatsapp_accounts.app_id IS 'Meta App ID - optionnel, surcharge META_APP_ID global';
COMMENT ON COLUMN whatsapp_accounts.app_secret IS 'Meta App Secret - optionnel, surcharge META_APP_SECRET global';

-- Créer un index sur waba_id pour les recherches rapides
CREATE INDEX IF NOT EXISTS idx_whatsapp_accounts_waba_id ON whatsapp_accounts(waba_id);

-- Note: Ces champs sont optionnels et peuvent être remplis plus tard
-- Si non remplis, l'application utilisera les valeurs globales de la configuration

