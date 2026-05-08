# Page Login (Desktop)

- Route: ecran non authentifie desktop (render `LoginPage`).
- Container: `frontend/src/App.jsx` -> `DesktopApp`.
- Permission: aucune (pre-auth).
- Flux principal: connexion via Supabase auth context.
- Verification:
  - utilisateur non connecte voit la page;
  - utilisateur connecte arrive sur `/discussions`.
