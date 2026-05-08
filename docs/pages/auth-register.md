# Page Register

- Route: `/register` (et flow invite via query `type=invite`).
- Containers: `DesktopApp` et `MobileApp`.
- Permission: depend du token d'invitation / backend.
- Verification:
  - page accessible meme pendant un chargement auth;
  - retour post-inscription coherent (session ou login).
