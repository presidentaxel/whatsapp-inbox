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

