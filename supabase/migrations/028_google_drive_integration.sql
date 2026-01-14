-- Ajouter les colonnes pour Google Drive OAuth2
alter table whatsapp_accounts
  add column if not exists google_drive_enabled boolean default false,
  add column if not exists google_drive_folder_id text,
  add column if not exists google_drive_access_token text,
  add column if not exists google_drive_refresh_token text,
  add column if not exists google_drive_token_expiry timestamp;

-- Commentaire pour documenter
comment on column whatsapp_accounts.google_drive_enabled is 'Activer/désactiver l''upload automatique vers Google Drive';
comment on column whatsapp_accounts.google_drive_folder_id is 'ID du dossier Google Drive racine pour ce compte WhatsApp (optionnel)';
comment on column whatsapp_accounts.google_drive_access_token is 'Token d''accès OAuth2 Google Drive (chiffré)';
comment on column whatsapp_accounts.google_drive_refresh_token is 'Token de rafraîchissement OAuth2 Google Drive (chiffré)';
comment on column whatsapp_accounts.google_drive_token_expiry is 'Date d''expiration du token d''accès';

