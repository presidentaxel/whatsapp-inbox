-- Ajouter la colonne storage_url pour stocker l'URL Supabase Storage des médias
alter table messages
add column if not exists storage_url text;

-- Index pour les requêtes de nettoyage (médias de plus de 60 jours)
create index if not exists idx_messages_storage_url_timestamp 
on messages(storage_url, timestamp) 
where storage_url is not null;

