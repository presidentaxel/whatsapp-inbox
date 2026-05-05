alter table messages
  add column if not exists media_id text,
  add column if not exists media_mime_type text,
  add column if not exists media_filename text;

