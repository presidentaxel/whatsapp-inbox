-- Ajouter le champ pour tracker les fichiers uploadés vers Google Drive
alter table messages
  add column if not exists google_drive_file_id text;

-- Commentaire pour documenter
comment on column messages.google_drive_file_id is 'ID du fichier dans Google Drive après upload';

-- Index pour faciliter les requêtes de backfill
create index if not exists idx_messages_google_drive_backfill 
  on messages(conversation_id, google_drive_file_id) 
  where storage_url is not null and google_drive_file_id is null;

