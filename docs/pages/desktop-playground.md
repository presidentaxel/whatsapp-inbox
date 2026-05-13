# Page Desktop Playground

- Route: `/playground`.
- Container: `InboxPage` (mode `assistant`).
- Permission: `playground.access`.
- Composant: `AssistantPanel`.
- Verification:
  - page visible si permission active;
  - changement de compte remonte via `onAccountChange`.
