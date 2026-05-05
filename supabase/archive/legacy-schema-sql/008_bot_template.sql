alter table bot_profiles
  add column if not exists template_config jsonb default '{}'::jsonb;

