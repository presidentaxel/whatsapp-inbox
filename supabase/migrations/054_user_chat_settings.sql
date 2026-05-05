-- Table pour stocker les paramètres de chat de l'utilisateur
create table if not exists user_chat_settings (
  user_id uuid primary key references app_users(user_id) on delete cascade,
  theme text default 'default',
  wallpaper text default 'default',
  enter_key_sends boolean default true,
  media_visibility boolean default true,
  font_size text default 'medium',
  updated_at timestamptz default now()
);

-- Index pour les recherches
create index if not exists idx_user_chat_settings_user on user_chat_settings(user_id);

