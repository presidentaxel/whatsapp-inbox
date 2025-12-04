-- Ajout du champ profile_picture_url à la table contacts
alter table contacts
  add column if not exists profile_picture_url text;

-- Index pour améliorer les performances des requêtes
create index if not exists idx_contacts_profile_picture 
  on contacts(profile_picture_url) 
  where profile_picture_url is not null;

