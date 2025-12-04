-- Ajouter le champ evolution_instance à la table whatsapp_accounts
-- Ce champ permet de stocker l'ID d'instance Evolution API pour chaque compte
-- (optionnel - seulement si vous utilisez Evolution API)

ALTER TABLE whatsapp_accounts
  ADD COLUMN IF NOT EXISTS evolution_instance TEXT;

-- Commentaire pour expliquer l'utilisation
COMMENT ON COLUMN whatsapp_accounts.evolution_instance IS 
  'ID de l''instance Evolution API associée à ce compte (optionnel). Utilisé pour récupérer les images de profil via Evolution API.';

