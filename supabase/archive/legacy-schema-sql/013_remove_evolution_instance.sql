-- Supprimer le champ evolution_instance (plus utilisé)
-- Le système utilise maintenant directement Graph API

ALTER TABLE whatsapp_accounts
  DROP COLUMN IF EXISTS evolution_instance;

