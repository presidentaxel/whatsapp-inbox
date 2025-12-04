-- Ajout du champ profile_picture_url à la table app_users
alter table app_users
  add column if not exists profile_picture_url text;

-- Index pour les recherches
create index if not exists idx_app_users_profile_picture 
  on app_users(profile_picture_url) 
  where profile_picture_url is not null;

