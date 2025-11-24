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