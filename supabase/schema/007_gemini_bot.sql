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