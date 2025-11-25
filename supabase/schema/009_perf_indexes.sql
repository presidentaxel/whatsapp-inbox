-- Performance indexes for high-traffic queries

create index if not exists idx_conversations_account_updated
  on conversations (account_id, updated_at desc);

create index if not exists idx_messages_conversation_timestamp
  on messages (conversation_id, timestamp desc);

