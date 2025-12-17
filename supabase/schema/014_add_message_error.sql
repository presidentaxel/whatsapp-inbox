-- Ajouter le champ error_message pour stocker les détails d'erreur des messages
alter table messages
  add column if not exists error_message text;

