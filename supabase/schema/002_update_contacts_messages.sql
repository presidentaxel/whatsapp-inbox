alter table contacts
  add column if not exists display_name text;

alter table messages
  add column if not exists wa_message_id text unique,
  add column if not exists message_type text,
  add column if not exists status text;

