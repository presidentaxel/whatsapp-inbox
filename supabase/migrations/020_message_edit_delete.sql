-- Ajout des colonnes pour édition et suppression des messages

alter table messages
  add column if not exists edited_at timestamptz,
  add column if not exists edited_by uuid,
  add column if not exists edited_original_content text,
  add column if not exists deleted_for_all_at timestamptz,
  add column if not exists deleted_for_user_ids jsonb default '[]'::jsonb;


