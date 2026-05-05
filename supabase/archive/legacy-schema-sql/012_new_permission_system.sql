-- Nouveau système de permissions avec 3 rôles fixes et accès par compte

-- 1. D'abord s'assurer que TOUTES les permissions existent (y compris les nouvelles)
-- Insérer toutes les permissions de base + les nouvelles
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

-- 2. Mettre à jour les rôles existants (Admin, DEV, Manager)
-- Supprimer les rôles qui ne sont pas dans la liste des 3 rôles fixes
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

-- 3. Créer une table pour les accès utilisateur par compte WhatsApp
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

-- 4. Supprimer les anciennes permissions de rôles avant de les recréer
delete from role_permissions;

-- 5. Mettre à jour les permissions pour les nouveaux rôles

-- Admin : toutes les permissions
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

-- DEV : peut voir les permissions mais pas les modifier
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

-- Manager : pas d'accès aux permissions
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

-- 6. Trigger pour mettre à jour updated_at
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

