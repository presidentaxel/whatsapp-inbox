-- Tag d’orientation (secteur / skills) sur les messages utilisateur Axelia - affichage UI uniquement

ALTER TABLE axelia_messages ADD COLUMN IF NOT EXISTS focus_tag text;

COMMENT ON COLUMN axelia_messages.focus_tag IS 'Orientation IA (ex. templates, broadcast) ; affichée comme tag sur le message';
