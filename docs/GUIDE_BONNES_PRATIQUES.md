# Guide de bonnes pratiques - WhatsApp Inbox

Document interne pour coder de façon cohérente, sûre et maintenable sur ce dépôt.

En cas de doute, ce guide prime sur les habitudes legacy. Si un dossier ancien ne suit pas encore ces règles, aligner progressivement le code lors des PR.

---

## 1. Carte du projet


| Zone                   | Rôle                                                                             |
| ---------------------- | -------------------------------------------------------------------------------- |
| `frontend/`            | SPA React 18 + Vite 6, appels HTTP via Axios, client Supabase (anon), temps réel |
| `backend/`             | API FastAPI, logique métier, webhooks Meta, clé **service_role** (hors RLS)      |
| `backend/app/services/agent_outbound/` | Noyau **inbox Agent Studio** (boucle Gemini + outils lecture v1, séparé d’Axelia) - voir `docs/AGENT_STUDIO_RUNBOOK.md` |
| `supabase/migrations/` | Source de vérité du schéma Postgres et des politiques RLS                        |
| `supabase/functions/`  | Edge Functions (Deno), ex. webhook WhatsApp                                      |
| `supabase/archive/`    | Anciens scripts conservés pour mémoire - **ne plus exécuter**                    |


Avant de modifier du code : identifier **où** vit la règle (UI, API, SQL, edge) pour ne pas dupliquer ni contredire la sécurité.

---

## 2. Style et outillage (frontend)

### 2.1 Outils

- **Node** ≥ 20 (`engines` dans `frontend/package.json`).
- **Prettier** : configuration dans `frontend/.prettierrc.json` (guillemets doubles, point-virgule, `printWidth` 100, fin de ligne LF). Lancer `npm run format` / `format:check` avant une PR si besoin.
- **ESLint** : `frontend/eslint.config.mjs` - respecter l’esprit du fichier : règles orientées **bugs réels** (hooks, undefined), pas une chasse aux micro-style.

### 2.2 React

- **Hooks** : respecter les règles des hooks ; traiter `exhaustive-deps` sérieusement (dépendances manquantes = bugs subtils ou fuites).
- **Clés en liste** : fournir des clés stables quand c’est possible (éviter l’index seul si l’ordre change).
- **Effets** : un effet = une intention claire ; éviter les effets « fourre-tout » difficiles à raisonner.
- **État** : préférer remonter l’état ou des hooks dédiés plutôt que des globals implicites, sauf pattern déjà établi (ex. événements auth documentés dans le code).

### 2.3 Modules et chemins

- Imports explicites, chemins cohérents avec l’arborescence `src/` (`api/`, `components/`, `hooks/`, `utils/`).
- Fichiers **ignorés du lint** (service worker, bundles minifiés dans `public/`) : ne pas y mettre de logique métier à maintenir à la main.

### 2.4 Variables d’environnement (Vite)

- Préfixe obligatoire `VITE_` pour exposer une variable au bundle navigateur.
- Ne jamais y mettre de secrets serveur : tout ce qui est `VITE_`* est **public** une fois buildé.

### 2.5 Tests

- **Vitest** : `npm run test` ; ajouter des tests ciblés pour la logique fragile (utilitaires, parsing, règles métier isolables).

---

## 3. API HTTP et auth (frontend ↔ backend)

- Le client Axios (`frontend/src/api/axiosClient.js`) attache le **JWT Supabase** ; ne pas court-circuiter ce mécanisme sans bonne raison documentée.
- En dev, le proxy `/api` est piloté par `VITE_DEV_PROXY` : à connaître pour le débogage réseau.
- Sur **401**, l’app s’appuie sur un événement global (`auth:unauthorized`) : toute évolution doit rester cohérente avec `AuthContext` / la navigation login.

---

## 4. Supabase côté client

- **Clé anon** + **RLS** : le navigateur ne doit pas supposer l’accès à des données sensibles ; toute nouvelle table exposée au client doit avoir des politiques alignées multi-tenant (`account_id`, RBAC).
- **Realtime** : paramètres déjà tunés dans `supabaseClient.js` ; éviter de multiplier les abonnements identiques (coût et charge).
- Ne pas utiliser la **service_role** dans le frontend.

---

## 5. Backend Python (FastAPI)

### 5.1 Structure

- Routes sous `app/api/`, logique dans `app/services/`, schémas Pydantic dans `app/schemas/`, configuration dans `app/core/`.
- Garder les routes **minces** : validation, appel service, réponse ; la complexité vit dans les services testables.

### 5.2 Qualité

- Respecter **PEP 8** et la lisibilité (noms explicites, fonctions courtes).
- Préférer les **types** (hints) sur les signatures publiques et les modèles exposés.
- Gérer les erreurs de façon **explicite** : codes HTTP cohérents, messages utiles côté opérateur sans fuite de secrets.
- Outillage recommandé sur les nouvelles contributions backend : `ruff` (lint + format) et `pytest` pour éviter des revues purement stylistiques.
- Si une règle d'outillage n'est pas encore codifiée dans le dépôt, garder les changements minimaux et cohérents avec les fichiers voisins.

### 5.3 Tests backend

- Lancer les tests backend touchés via `pytest backend/tests/` (ou un sous-ensemble ciblé).
- Pour une logique sensible (permissions, webhook security, parsing média, retries), ajouter au moins un test de non-régression.

### 5.4 Secrets et configuration

- Variables d’environnement documentées (voir README / `.env.example` si présent).
- Jamais de clés en dur dans le dépôt ; les scripts locaux doivent rester compatibles avec des valeurs mock (comme en CI).

### 5.5 Base de données

- Le backend utilise en général la clé **service_role** : il **contourne RLS**. Toute vérification d’accès (compte, rôle) doit donc être faite **dans l’API** si la donnée est sensible.

### 5.6 Intégrations externes (WhatsApp, stockage, IA)

- Timeouts, retries et idempotence : réutiliser les modules existants (`app/core/http_client.py`, `app/core/retry.py`, `app/core/circuit_breaker.py`, `app/core/rate_limit.py`) plutôt que réinventer par route.
- Webhooks : toujours valider **signature** / **tokens** comme dans le code existant ; ne pas faire confiance au corps brut.

---

## 6. SQL, migrations et RLS

### 6.1 Migrations

- Une migration = une intention claire (nom de fichier explicite).
- Le préfixe numérique d'une migration doit être **unique** (ne jamais réutiliser un numéro déjà pris).
- Éviter les migrations destructives sans plan de données (backup, étapes en plusieurs PR si nécessaire).
- Index : nommer et documenter quand l’index sert un chemin de requête précis (cf. migrations perf existantes).

### 6.2 RLS

- Toute table lue depuis le client avec la clé **anon** doit avoir RLS **activé** et des politiques **complètes** (SELECT / INSERT / UPDATE / DELETE selon les besoins réels).
- Rappel architecture : **RLS protège le client**, pas le backend service_role.
- Après changement RLS : livrer toujours via une migration dans `supabase/migrations/`. C'est l'unique source de vérité, donc rien à dupliquer ailleurs.

---

## 7. Edge Functions (Deno / TypeScript)

- Environnement **Deno** : imports `npm:` / URLs stables, pas de APIs Node supposées.
- Secrets via `supabase secrets set` ; ne pas préfixer avec `SUPABASE_` les noms réservés (voir commentaires dans `whatsapp-webhook`).
- Réutiliser les mêmes principes **crypto** que le backend (HMAC, comparaisons **timing-safe** quand on compare des secrets ou signatures).
- Réponses HTTP : statuts et corps prévisibles pour Meta et pour le debugging (sans exposer d’informations internes inutiles).

---

## 8. Sécurité (rappels transverses)

- **Principe du moindre privilège** : anon côté navigateur, service_role côté serveur contrôlé uniquement.
- **CORS** : configuration stricte côté API ; ne pas élargir « pour débloquer vite ».
- **Stockage** : buckets et chemins cohérents avec les politiques ; pas de fichiers publics sensibles par erreur.
- **Journalisation** : éviter de logger tokens, payloads complets de webhooks contenant des données personnelles, ou clés.
- **Dépendances** : mettre à jour prudemment ; surveiller les advisories ; utiliser `npm ci` en CI.

---

## 9. Git, PR et revue

- **Branches** : courtes, ciblées ; une PR = une intention principale (fonctionnalité, correctif, refacto limité).
- **Messages de commit** : utiliser Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`) en français ou en anglais, mais rester cohérent dans une PR.
- **Revue** : expliquer le « pourquoi » dans la description de PR ; lier ticket ou contexte si l’équipe en utilise.
- **Avant merge** : build frontend, lint raisonnable, tests impactés verts ; pour le SQL, valider sur une base de dev ou via CLI Supabase selon le flux de l’équipe.

### 9.1 Pull Request

- Suivre le template de PR du dépôt et expliciter : contexte, impact utilisateur, risques, et plan de test.
- Si la PR touche auth/RLS/permissions, ajouter un paragraphe "sécurité" décrivant le périmètre d'accès attendu.

---

## 10. Déploiement et configuration

- Fichiers sous `deploy/` (Caddy, Docker) : ne pas casser les routes `/api` et `/webhook` attendues par l’infra (validées en CI).
- Variables `BACKEND_URL` et équivalentes : alignées entre compose, Caddy et scripts de déploiement.

### 10.1 Ajouter une variable d'environnement (checklist)

1. Ajouter la variable dans le ou les `.env.example` concernés.
2. Documenter la variable dans `README.md` (valeur attendue, exemple, impact sécurité).
3. Vérifier son câblage runtime (`deploy/docker-compose*.yml`, `deploy/Caddy`*, scripts de déploiement, CI).
4. Côté frontend, n'exposer au navigateur que les variables `VITE_`*.

---

## 11. Checklist rapide avant une PR

1. Changement limité au besoin (pas de refacto gratuit hors sujet).
2. Pas de secret ou donnée de prod dans le diff.
3. Si table / colonne exposée au client : **RLS** revue.
4. Si route API : auth / périmètre compte revus.
5. Hooks React et deps d’effets revus.
6. `npm run lint` / `npm run test` (frontend) ; tests ou compile Python (backend) selon la zone touchée.
7. Si migration SQL: numéro unique, test local, et synchronisation de la référence RLS si concernée.

---

## 12. En cas de doute

- S’aligner sur un fichier **proche** déjà mergé (même dossier, même style).
- Pour le produit Supabase (Auth, RLS, migrations), se référer à la doc officielle et aux fichiers `README` du dossier `supabase/`.
- En cas de conflit entre deux pratiques, privilégier la sécurité des accès et la source de vérité (`supabase/migrations/` pour le SQL).

---

*Dernière mise à jour : guide aligné sur la structure du dépôt (React/Vite, FastAPI, Supabase). À faire évoluer avec les décisions d’équipe.*