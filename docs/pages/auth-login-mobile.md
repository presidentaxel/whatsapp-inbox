# Page Login (Mobile)

- Route: ecran non authentifie mobile (render `MobileLoginPage`).
- Container: `frontend/src/App.jsx` -> `MobileApp`.
- Permission: aucune (pre-auth).
- APIs auth: `supabaseClient.auth.setSession`, `getSession`, `onAuthStateChange`.
- Verification:
  - session locale restauree si valide;
  - fallback login si session invalide.
