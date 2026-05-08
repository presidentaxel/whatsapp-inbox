# Page Desktop Discussions

- Route: `/discussions`.
- Container: `InboxPage` (mode `chat`).
- Composants: `AccountSelector`, `ConversationList`, `ChatWindow`.
- APIs: `getAccounts`, `getConversations`, `markConversationRead`, `findOrCreateConversation`.
- Realtime: notifications globales + channel Supabase `conversations:{accountId}`.
- Verification:
  - changement de compte recharge la liste;
  - unread passe a 0 a l'ouverture;
  - recherche numero -> conversation creee/ouverte.
