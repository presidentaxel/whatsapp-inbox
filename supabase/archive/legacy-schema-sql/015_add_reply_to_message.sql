-- Ajouter le champ reply_to_message_id pour référencer le message original
-- lors d'une réponse (via bouton interactif ou citation)
alter table messages
  add column if not exists reply_to_message_id uuid references messages(id) on delete set null;

-- Index pour améliorer les performances lors de la recherche du message référencé
create index if not exists idx_messages_reply_to_message_id on messages(reply_to_message_id);

