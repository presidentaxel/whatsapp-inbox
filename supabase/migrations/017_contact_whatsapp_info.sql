-- Ajout de champs pour stocker les informations WhatsApp des contacts
alter table contacts
  add column if not exists whatsapp_name text,
  add column if not exists whatsapp_info_fetched_at timestamptz;

-- Index pour les recherches
create index if not exists idx_contacts_whatsapp_name 
  on contacts(whatsapp_name) 
  where whatsapp_name is not null;

create index if not exists idx_contacts_whatsapp_info_fetched 
  on contacts(whatsapp_info_fetched_at) 
  where whatsapp_info_fetched_at is not null;

