# WhatsApp Inbox

Petite boîte de réception temps réel basée sur WhatsApp Cloud API + Supabase.

## Prérequis

- Compte [Meta for Developers](https://developers.facebook.com/)
- Numéro WhatsApp Business relié au compte ou numéro de test
- Projet Supabase avec les scripts SQL du dossier `supabase/schema`
- Python 3.11+, Node 18+

## Variables d'environnement

### Backend (`backend/.env`)
```
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=service_role_où_anon_selon_besoin
WHATSAPP_TOKEN=EAAG....
WHATSAPP_PHONE_ID=1234567890
WHATSAPP_VERIFY_TOKEN=mon_token_webhook
WHATSAPP_PHONE_NUMBER=+15551234567
META_APP_ID=1234567890
META_APP_SECRET=votre_app_secret
```

### Frontend (`frontend/.env`)
```
VITE_BACKEND_URL=https://mon-backend-en-production.example.com
VITE_SUPABASE_URL=https://xxxxx.supabase.co
VITE_SUPABASE_ANON_KEY=public-anon-key
# (optionnel en dev)
VITE_DEV_BACKEND_URL=http://localhost:8000
VITE_DEV_PROXY=true
```

> En local, laisse `VITE_BACKEND_URL` vide pour t'appuyer sur le proxy `/api` de Vite (il redirige vers `VITE_DEV_BACKEND_URL`). Positionne `VITE_DEV_PROXY=false` si tu préfères cibler l'URL explicite même en mode dev.

### Docker
`docker-compose.yml` charge automatiquement les fichiers `.env` ci-dessus.

## Base de données

1. Appliquer `supabase/schema/001_init_whatsapp_inbox.sql`
2. Pour les instances existantes, exécuter également `002_update_contacts_messages.sql`
3. Pour activer le multi-compte, lancer `003_multitenant_accounts.sql` (il crée un compte “Legacy account” temporaire puis assigne toutes les conversations dessus ; il sera automatiquement synchronisé avec tes variables `.env` dès que le backend redémarre)
4. Pour les filtres (favoris, non lues, groupes), appliquer `004_conversation_flags.sql` qui ajoute `is_favorite`, `is_group`, `unread_count`
5. **RBAC / permissions** : exécuter `005_rbac.sql` pour créer les tables `app_users`, `app_roles`, `app_permissions`, etc. La première personne qui se connecte obtient automatiquement le rôle `admin`.
6. **Médias** : appliquer `006_message_media.sql` qui ajoute `media_id`, `media_mime_type`, `media_filename` aux messages pour pouvoir diffuser audio / images côté interface.

### Table `whatsapp_accounts`

| Colonne            | Description                                    |
|--------------------|------------------------------------------------|
| `name`, `slug`     | Nom lisible + identifiant unique                |
| `phone_number`     | Numéro affiché (facultatif)                     |
| `phone_number_id`  | ID fourni par Meta                             |
| `access_token`     | Token d’accès au Graph API                     |
| `verify_token`     | Token utilisé lors du handshake webhook        |

Le backend synchronise automatiquement un compte “par défaut” à partir des variables d’environnement ci-dessus. Pour ajouter d’autres comptes, insère de nouvelles lignes dans `whatsapp_accounts` (via Supabase SQL ou l’UI) avec leurs tokens respectifs. L’interface affiche ensuite un sélecteur pour passer d’un compte à l’autre.

## Lancer l'app

```bash
# backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# frontend (Vite gère déjà --host 0.0.0.0 + proxy /api → backend local)
cd frontend
npm install
npm run dev
```

### Workflow quotidien

1. **Backend (terminal 1)**
   ```bash
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
2. **Webhook + ngrok (terminal 2)**
   ```powershell
   cd backend
   powershell -ExecutionPolicy Bypass -File scripts/start_webhook.ps1 --force
   ```
   - utilise `-ForceToken` si tu veux régénérer la valeur
   - laisse la fenêtre ouverte tant que tu as besoin du tunnel
3. **Frontend (terminal 3)**
   ```bash
   cd frontend
   npm run dev -- --host
   ```

## Webhook WhatsApp

Configurer dans le dashboard Meta :

- URL : `https://<ton-backend>/webhook/whatsapp`
- Vérification : utiliser `WHATSAPP_VERIFY_TOKEN`
- Abonnements : `messages`

Les messages entrants sont stockés dans Supabase, les statuts (sent/delivered/read) mettent à jour la colonne `status`.

### Générer le token automatiquement

```
cd backend
python scripts/generate_verify_token.py          # crée un token si absent
python scripts/generate_verify_token.py --force  # régénère le token
```

La commande écrit/ajoute `WHATSAPP_VERIFY_TOKEN` dans `backend/.env` et affiche sa valeur pour que tu la recopies dans le formulaire “Vérifier le token”.

### Script assisté (ngrok + token)

Pré-requis : [ngrok](https://ngrok.com/download) installé et authentifié (`ngrok config add-authtoken ...`).

```
cd backend
powershell -ExecutionPolicy Bypass -File scripts/start_webhook.ps1
```

Le script :

- lance un tunnel HTTPS ngrok sur le port 8000
- génère (ou réutilise) `WHATSAPP_VERIFY_TOKEN` et synchronise le compte par défaut
- affiche l’URL publique et le token à saisir dans Meta

Option `-ForceToken` possible pour régénérer le token avant chaque session.

### Validation pas à pas

1. Lancer ton backend (`uvicorn app.main:app --reload`) + ouvrir un tunnel HTTPS (ex. `ngrok http 8000`).
2. Copier l’URL exposée vers `/webhook/whatsapp` dans Meta.
3. Exécuter `python scripts/generate_verify_token.py` et coller la valeur affichée dans “Vérifier le token”.
4. Cliquer sur “Vérifier et enregistrer”. Meta effectue un `GET` et reçoit le `hub.challenge` renvoyé par l’API.
5. Dans “Gérer les abonnements”, activer `messages` et utiliser “Envoyer un test” pour valider la réception.

## Authentification Supabase

L’accès à l’UI est maintenant protégé via [Supabase Auth](https://supabase.com/docs/guides/auth):

1. Dans le dashboard Supabase, active l’auth email+mot de passe et crée les membres de ton entreprise (table `auth.users`).
2. Renseigne `VITE_SUPABASE_URL` et `VITE_SUPABASE_ANON_KEY` dans `frontend/.env`.
3. Le frontend utilise `supabase-js` pour se connecter ; l’access token est automatiquement envoyé au backend dans l’en-tête `Authorization`.
4. Le backend vérifie le token à chaque requête (excepté le webhook) via `supabase.auth.get_user(...)`. Toute personne connectée a accès à l’ensemble des conversations. On pourra ajouter plus tard des rôles/permissions fines par utilisateur.

> ⚠️ Le webhook WhatsApp et Supabase restent publics ; seule l’interface et les API internes nécessitent un utilisateur authentifié.

## Déploiement gratuit

### Backend (Render)

Tu peux utiliser le fichier `render.yaml` fourni à la racine :

1. Pousse le repo sur GitHub (branche `main`).
2. Sur [Render](https://render.com/), choisis **Blueprint** → connecte ton repo → Render détecte `render.yaml`.
3. Le blueprint crée :
   - un service web Docker (`backend/Dockerfile`, port 8000)
   - un site statique (build Vite dans `frontend/`)
4. Sur l’onglet **Environment** de chaque service, saisis les valeurs :
   - Backend : `SUPABASE_URL`, `SUPABASE_KEY`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_PHONE_NUMBER`
   - Frontend : `VITE_BACKEND_URL` (URL du service backend), `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`
5. Déploie → Render fournit deux URLs (`.onrender.com`).

### Frontend (Netlify / Vercel)

Tu peux aussi utiliser Netlify en te basant sur `netlify.toml` :

1. Connecte le repo à [Netlify](https://www.netlify.com/).
2. Le fichier `netlify.toml` définit `base=frontend`, `command=npm run build`, `publish=dist`.
3. Variables : `VITE_BACKEND_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.
4. Déploie → Netlify fournit `https://xxx.netlify.app`.

> Tu peux aussi utiliser `docker-compose up --build` en local pour valider avant chaque push : les Dockerfile backend/frontend sont prêts pour Render/Netlify.

## RBAC : rôles & permissions

- Les utilisateurs se connectent via Supabase Auth comme auparavant. À la première connexion, une ligne est créée dans `app_users`. Si aucune attribution n’existe encore, ce premier membre reçoit automatiquement le rôle `admin`.
- Les rôles (`app_roles`) et leurs permissions (`app_permissions`) sont gérés depuis l’onglet **Paramètres** de l’UI (section “Rôles & permissions”) ou via les nouvelles routes `/admin/*`.
- Permissions disponibles :
  - `accounts.view`, `accounts.manage`, `accounts.assign`
  - `conversations.view`
  - `messages.view`, `messages.send`
  - `contacts.view`
  - `users.manage`, `roles.manage`, `settings.manage`
- Tu peux assigner un rôle global ou scoped à un compte WhatsApp (ex. opérateur uniquement pour `account_id=X`). Les overrides permettent d’autoriser/interdire une permission précise pour un membre donné.
- L’API expose :
  - `GET /auth/me` → profil + permissions agrégées (utilisé par le frontend)
  - `GET/POST/PUT/DELETE /admin/roles`
  - `GET /admin/permissions`
  - `GET /admin/users`
  - `POST /admin/users/{id}/status`
  - `PUT /admin/users/{id}/roles`
  - `PUT /admin/users/{id}/overrides`
- Côté UI :
  - L’onglet “Discussions” n’affiche que les comptes sur lesquels tu as `accounts.view`.
  - L’envoi de message est désactivé (barre grisée) si tu n’as pas `messages.send` pour la conversation courante.
  - L’onglet “Contacts” n’est accessible qu’avec `contacts.view`.
  - Le panneau “Paramètres” contient désormais :
    - gestion des comptes (création/suppression) pour les personnes ayant `accounts.manage`,
    - éditeur de rôles/permissions,
    - gestion des utilisateurs (activation, rôles par compte, overrides).

## Tokens WhatsApp

- **Verify Token** : valeur statique que tu choisis (à déclarer dans Meta + `WHATSAPP_VERIFY_TOKEN`). Elle n’expire pas ; inutile de la régénérer automatiquement.
- **Access Token** (Meta Business) : les tokens temporaires expirent au bout d’une heure. Pour éviter de perdre la connexion, génère un token long-lived (60 jours) via :

```bash
cd backend
python scripts/refresh_whatsapp_token.py
```

Pré-requis :
1. Renseigner `META_APP_ID` et `META_APP_SECRET` dans `backend/.env`.
2. `WHATSAPP_TOKEN` doit contenir le token court actuel (fourni par Meta).

Le script :
- échange le token court contre un token long-lived via l’API Meta,
- met à jour `backend/.env` (`WHATSAPP_TOKEN=...`) et la table `whatsapp_accounts`,
- affiche la durée `expires_in`. Relance-le avant l’expiration (ou programme un cron).


