-- Baseline: schéma historique auparavant dans supabase/schema/ uniquement.
-- Les copies des anciens scripts schema/*.sql sont archivées sous supabase/archive/legacy-schema-sql/.
-- Sans ce fichier, supabase db reset n’applique que supabase/migrations/ et
-- la première migration (010_…) suppose que conversations, messages, etc. existent.
--
-- Contenu fusionné (ordre) : schema/001 … schema/015 + évolution add/remove.
-- Les index dupliquent en partie 009_perf_indexes.sql et 010_performance_indexes.sql
-- (CREATE INDEX IF NOT EXISTS - idempotent).

-- ========== schema/001_init_whatsapp_inbox.sql ==========
create table whatsapp_accounts (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text unique not null,
  phone_number text,
  phone_number_id text unique not null,
  access_token text not null,
  verify_token text not null,
  is_active boolean default true,
  created_at timestamp default now()
);

create table contacts (
  id uuid primary key default gen_random_uuid(),
  whatsapp_number text unique not null,
  display_name text,
  created_at timestamp default now()
);

create table conversations (
  id uuid primary key default gen_random_uuid(),
  contact_id uuid references contacts(id),
  account_id uuid references whatsapp_accounts(id),
  client_number text not null,
  is_group boolean default false,
  is_favorite boolean default false,
  unread_count int default 0,
  status text default 'open',
  updated_at timestamp default now()
);
create unique index conversations_account_client_unique on conversations(account_id, client_number);

create table messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid references conversations(id),
  direction text not null,
  content_text text,
  timestamp timestamp default now(),
  wa_message_id text unique,
  message_type text,
  status text
);

-- ========== schema/002_update_contacts_messages.sql ==========
alter table contacts
  add column if not exists display_name text;

alter table messages
  add column if not exists wa_message_id text unique,
  add column if not exists message_type text,
  add column if not exists status text;

-- ========== schema/003_multitenant_accounts.sql ==========
create table if not exists whatsapp_accounts (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text unique not null,
  phone_number text,
  phone_number_id text unique not null,
  access_token text not null,
  verify_token text not null,
  is_active boolean default true,
  created_at timestamp default now()
);

alter table conversations
  add column if not exists account_id uuid references whatsapp_accounts(id);

do $$
declare
  default_account uuid;
begin
  select id into default_account from whatsapp_accounts
  order by created_at
  limit 1;

  if default_account is null then
    insert into whatsapp_accounts (name, slug, phone_number, phone_number_id, access_token, verify_token)
    values ('Legacy account', 'legacy-migration', null, 'legacy-phone-id', 'legacy-token', 'legacy-verify')
    returning id into default_account;
  end if;

  update conversations
  set account_id = default_account
  where account_id is null;
end $$;

alter table conversations
  alter column account_id set not null;

do $$
begin
  if exists (
    select 1 from information_schema.table_constraints
    where constraint_name = 'conversations_client_number_key'
  ) then
    alter table conversations
      drop constraint conversations_client_number_key;
  end if;
end $$;

create unique index if not exists conversations_account_client_unique
  on conversations(account_id, client_number);

-- ========== schema/004_conversation_flags.sql ==========
alter table conversations
  add column if not exists is_group boolean default false,
  add column if not exists is_favorite boolean default false,
  add column if not exists unread_count int default 0;

update conversations
set unread_count = coalesce(unread_count, 0);

-- ========== schema/005_rbac.sql ==========
create table if not exists app_permissions (
  code text primary key,
  label text,
  description text
);

create table if not exists app_roles (
  id uuid primary key default gen_random_uuid(),
  slug text unique not null,
  name text not null,
  description text,
  created_at timestamptz default now()
);

create table if not exists role_permissions (
  role_id uuid references app_roles(id) on delete cascade,
  permission_code text references app_permissions(code) on delete cascade,
  created_at timestamptz default now(),
  primary key (role_id, permission_code)
);

create table if not exists app_users (
  user_id uuid primary key,
  email text,
  display_name text,
  is_active boolean default true,
  created_at timestamptz default now()
);

create table if not exists app_user_roles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references app_users(user_id) on delete cascade,
  role_id uuid references app_roles(id) on delete cascade,
  account_id uuid references whatsapp_accounts(id),
  created_at timestamptz default now(),
  unique (user_id, role_id, account_id)
);

create table if not exists app_user_overrides (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references app_users(user_id) on delete cascade,
  permission_code text references app_permissions(code) on delete cascade,
  account_id uuid references whatsapp_accounts(id),
  is_allowed boolean not null,
  created_at timestamptz default now()
);

create index if not exists idx_app_user_roles_user on app_user_roles(user_id);
create index if not exists idx_app_user_roles_account on app_user_roles(account_id);
create index if not exists idx_app_user_overrides_user on app_user_overrides(user_id);
create index if not exists idx_app_user_overrides_account on app_user_overrides(account_id);

insert into app_permissions (code, label, description) values
  ('accounts.view', 'Voir les comptes', 'Afficher la liste des comptes WhatsApp'),
  ('accounts.manage', 'Gérer les comptes', 'Créer / modifier / supprimer des comptes WhatsApp'),
  ('accounts.assign', 'Assigner des comptes', 'Attribuer des comptes aux membres'),
  ('conversations.view', 'Voir les conversations', 'Consulter les conversations et leurs métadonnées'),
  ('messages.view', 'Voir les messages', 'Afficher le contenu des messages'),
  ('messages.send', 'Envoyer des messages', 'Répondre ou envoyer des messages sortants'),
  ('contacts.view', 'Voir les contacts', 'Accéder à la liste des contacts'),
  ('users.manage', 'Gérer les utilisateurs', 'Activer/Désactiver les membres et gérer leurs accès'),
  ('roles.manage', 'Gérer les rôles', 'Créer/éditer les rôles et affecter les permissions'),
  ('settings.manage', 'Gérer les réglages', 'Modifier les paramètres généraux de l’application')
on conflict (code) do update set
  label = excluded.label,
  description = excluded.description;

insert into app_roles (slug, name, description) values
  ('admin', 'Administrateur', 'Accès complet à toutes les fonctions'),
  ('manager', 'Manager', 'Gestion opérationnelle : conversations et réponses'),
  ('viewer', 'Lecteur', 'Lecture seule des conversations et contacts')
on conflict (slug) do update set
  name = excluded.name,
  description = excluded.description;

with admin_role as (
  select id from app_roles where slug = 'admin'
)
insert into role_permissions (role_id, permission_code)
select admin_role.id, perm
from admin_role, unnest(array[
  'accounts.view',
  'accounts.manage',
  'accounts.assign',
  'conversations.view',
  'messages.view',
  'messages.send',
  'contacts.view',
  'users.manage',
  'roles.manage',
  'settings.manage'
]) as perm
on conflict do nothing;

with manager_role as (
  select id from app_roles where slug = 'manager'
)
insert into role_permissions (role_id, permission_code)
select manager_role.id, perm
from manager_role, unnest(array[
  'accounts.view',
  'conversations.view',
  'messages.view',
  'messages.send',
  'contacts.view'
]) as perm
on conflict do nothing;

with viewer_role as (
  select id from app_roles where slug = 'viewer'
)
insert into role_permissions (role_id, permission_code)
select viewer_role.id, perm
from viewer_role, unnest(array[
  'accounts.view',
  'conversations.view',
  'messages.view',
  'contacts.view'
]) as perm
on conflict do nothing;

-- ========== schema/006_message_media.sql ==========
alter table messages
  add column if not exists media_id text,
  add column if not exists media_mime_type text,
  add column if not exists media_filename text;

-- ========== schema/007_gemini_bot.sql ==========
alter table conversations
  add column if not exists bot_enabled boolean default false,
  add column if not exists bot_last_reply_at timestamptz;

create table if not exists bot_profiles (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references whatsapp_accounts (id) on delete cascade,
  business_name text,
  description text,
  address text,
  hours text,
  knowledge_base text,
  custom_fields jsonb default '[]'::jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create unique index if not exists bot_profiles_account_id_idx on bot_profiles (account_id);

create or replace function bot_profiles_set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_bot_profiles_updated_at on bot_profiles;
create trigger trg_bot_profiles_updated_at
before update on bot_profiles
for each row execute function bot_profiles_set_updated_at();

alter table whatsapp_accounts add column if not exists bot_auto_on boolean default false;

-- ========== schema/008_bot_template.sql ==========
alter table bot_profiles
  add column if not exists template_config jsonb default '{}'::jsonb;

-- ========== schema/009_perf_indexes.sql ==========
create index if not exists idx_conversations_account_updated
  on conversations (account_id, updated_at desc);

create index if not exists idx_messages_conversation_timestamp
  on messages (conversation_id, timestamp desc);

-- ========== schema/010_contacts_profile_picture.sql ==========
alter table contacts
  add column if not exists profile_picture_url text;

create index if not exists idx_contacts_profile_picture
  on contacts(profile_picture_url)
  where profile_picture_url is not null;

-- ========== schema/011_create_profile_pictures_bucket.sql (policies storage) ==========
DROP POLICY IF EXISTS "Public read access for profile pictures" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated users can upload profile pictures" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated users can update profile pictures" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated users can delete profile pictures" ON storage.objects;

CREATE POLICY "Public read access for profile pictures"
ON storage.objects FOR SELECT
USING (bucket_id = 'profile-pictures');

CREATE POLICY "Authenticated users can upload profile pictures"
ON storage.objects FOR INSERT
WITH CHECK (
  bucket_id = 'profile-pictures'
  AND auth.role() = 'authenticated'
);

CREATE POLICY "Authenticated users can update profile pictures"
ON storage.objects FOR UPDATE
USING (
  bucket_id = 'profile-pictures'
  AND auth.role() = 'authenticated'
);

CREATE POLICY "Authenticated users can delete profile pictures"
ON storage.objects FOR DELETE
USING (
  bucket_id = 'profile-pictures'
  AND auth.role() = 'authenticated'
);

-- ========== schema/012_add_evolution_instance.sql ==========
ALTER TABLE whatsapp_accounts
  ADD COLUMN IF NOT EXISTS evolution_instance TEXT;

COMMENT ON COLUMN whatsapp_accounts.evolution_instance IS
  'ID de l''instance Evolution API associée à ce compte (optionnel). Utilisé pour récupérer les images de profil via Evolution API.';

-- ========== schema/012_new_permission_system.sql ==========
insert into app_permissions (code, label, description) values
  ('accounts.view', 'Voir les comptes', 'Afficher la liste des comptes WhatsApp'),
  ('accounts.manage', 'Gérer les comptes', 'Créer / modifier / supprimer des comptes WhatsApp'),
  ('accounts.assign', 'Assigner des comptes', 'Attribuer des comptes aux membres'),
  ('conversations.view', 'Voir les conversations', 'Consulter les conversations et leurs métadonnées'),
  ('messages.view', 'Voir les messages', 'Afficher le contenu des messages'),
  ('messages.send', 'Envoyer des messages', 'Répondre ou envoyer des messages sortants'),
  ('contacts.view', 'Voir les contacts', 'Accéder à la liste des contacts'),
  ('users.manage', 'Gérer les utilisateurs', 'Activer/Désactiver les membres et gérer leurs accès'),
  ('roles.manage', 'Gérer les rôles', 'Créer/éditer les rôles et affecter les permissions'),
  ('settings.manage', 'Gérer les réglages', 'Modifier les paramètres généraux de l''application'),
  ('permissions.view', 'Voir les permissions', 'Consulter les permissions et accès'),
  ('permissions.manage', 'Gérer les permissions', 'Modifier les permissions et accès par compte')
on conflict (code) do update set
  label = excluded.label,
  description = excluded.description;

delete from app_user_roles where role_id in (
  select id from app_roles where slug not in ('admin', 'dev', 'manager')
);
delete from role_permissions where role_id in (
  select id from app_roles where slug not in ('admin', 'dev', 'manager')
);
delete from app_roles where slug not in ('admin', 'dev', 'manager');

insert into app_roles (slug, name, description) values
  ('admin', 'Administrateur', 'Peut changer les permissions et accès'),
  ('dev', 'Développeur', 'Peut voir les permissions mais ne pas les changer'),
  ('manager', 'Manager', 'Ne peut rien voir des autorisations')
on conflict (slug) do update set
  name = excluded.name,
  description = excluded.description;

create table if not exists user_account_access (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references app_users(user_id) on delete cascade not null,
  account_id uuid references whatsapp_accounts(id) on delete cascade not null,
  access_level text not null check (access_level in ('full', 'lecture', 'aucun')),
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  unique (user_id, account_id)
);

create index if not exists idx_user_account_access_user on user_account_access(user_id);
create index if not exists idx_user_account_access_account on user_account_access(account_id);

delete from role_permissions;

with admin_role as (
  select id from app_roles where slug = 'admin'
)
insert into role_permissions (role_id, permission_code)
select admin_role.id, perm
from admin_role, unnest(array[
  'accounts.view',
  'accounts.manage',
  'accounts.assign',
  'conversations.view',
  'messages.view',
  'messages.send',
  'contacts.view',
  'users.manage',
  'roles.manage',
  'settings.manage',
  'permissions.view',
  'permissions.manage'
]) as perm
on conflict do nothing;

with dev_role as (
  select id from app_roles where slug = 'dev'
)
insert into role_permissions (role_id, permission_code)
select dev_role.id, perm
from dev_role, unnest(array[
  'accounts.view',
  'conversations.view',
  'messages.view',
  'messages.send',
  'contacts.view',
  'permissions.view'
]) as perm
on conflict do nothing;

with manager_role as (
  select id from app_roles where slug = 'manager'
)
insert into role_permissions (role_id, permission_code)
select manager_role.id, perm
from manager_role, unnest(array[
  'accounts.view',
  'conversations.view',
  'messages.view',
  'messages.send',
  'contacts.view'
]) as perm
on conflict do nothing;

create or replace function update_user_account_access_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trigger_update_user_account_access_updated_at on user_account_access;
create trigger trigger_update_user_account_access_updated_at
  before update on user_account_access
  for each row
  execute function update_user_account_access_updated_at();

-- ========== schema/013_remove_evolution_instance.sql ==========
ALTER TABLE whatsapp_accounts
  DROP COLUMN IF EXISTS evolution_instance;

-- ========== schema/014_add_message_error.sql ==========
alter table messages
  add column if not exists error_message text;

-- ========== schema/015_add_reply_to_message.sql ==========
alter table messages
  add column if not exists reply_to_message_id uuid references messages(id) on delete set null;

create index if not exists idx_messages_reply_to_message_id on messages(reply_to_message_id);
