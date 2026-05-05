-- RBAC schema for application-level roles/permissions

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


