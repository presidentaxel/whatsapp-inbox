alter table conversations
  add column if not exists is_group boolean default false,
  add column if not exists is_favorite boolean default false,
  add column if not exists unread_count int default 0;

update conversations
set unread_count = coalesce(unread_count, 0);

