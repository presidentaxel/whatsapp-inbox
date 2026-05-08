# Page Desktop Contacts

- Route: `/contacts`.
- Container: `InboxPage` (mode `contacts`).
- Permission: `contacts.view`.
- Composants: `ContactsPanel`, `MetaBlockAccountModal`.
- APIs: `getContacts`, `getMetaBlockedWaIdsBatch`, `metaBlockContact`, `metaUnblockContact`.
- Verification:
  - recherche contacts OK;
  - blocage/deblocage WhatsApp met a jour l'etat local.
