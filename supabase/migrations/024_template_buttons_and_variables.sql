-- Migration pour ajouter le support des boutons et variables des templates
-- Permet de stocker les boutons des templates et les variables remplies

-- Ajouter une colonne pour stocker les variables remplies dans le template
-- Format JSON: {"1": "valeur1", "2": "valeur2", ...}
ALTER TABLE messages
  ADD COLUMN IF NOT EXISTS template_variables jsonb;

-- Ajouter une colonne pour stocker le nom du template utilisé
ALTER TABLE messages
  ADD COLUMN IF NOT EXISTS template_name text;

-- Ajouter une colonne pour stocker la langue du template
ALTER TABLE IF EXISTS messages
  ADD COLUMN IF NOT EXISTS template_language text;

-- S'assurer que interactive_data peut stocker les boutons des templates
-- (La colonne existe déjà depuis la migration 012, on ajoute juste un commentaire)
COMMENT ON COLUMN messages.interactive_data IS 'Données interactives (boutons, listes) au format JSON. Pour les templates: {"type": "button", "buttons": [{"type": "QUICK_REPLY", "text": "..."}, ...]}';

COMMENT ON COLUMN messages.template_variables IS 'Variables remplies du template au format JSON: {"1": "valeur1", "2": "valeur2"}. Les clés sont les numéros de variables ({{1}}, {{2}}, etc.)';

COMMENT ON COLUMN messages.template_name IS 'Nom du template WhatsApp utilisé pour ce message';

COMMENT ON COLUMN messages.template_language IS 'Code langue du template (ex: "fr", "en")';

-- Créer un index pour faciliter les recherches par template
CREATE INDEX IF NOT EXISTS idx_messages_template_name 
ON messages (template_name) 
WHERE template_name IS NOT NULL;

