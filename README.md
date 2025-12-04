# WhatsApp Inbox

Petite boîte de réception temps réel basée sur WhatsApp Cloud API + Supabase.

## 🆕 Nouvelle Fonctionnalité : API WhatsApp Complète

L'application implémente maintenant **toutes les fonctionnalités de l'API WhatsApp Business Cloud API** :

✅ **Messages avancés** : texte, médias, templates, boutons interactifs, listes déroulantes  
✅ **Gestion des médias** : upload, téléchargement, suppression  
✅ **Numéros de téléphone** : enregistrement, vérification, détails  
✅ **Profil business** : consultation et mise à jour  
✅ **Templates de messages** : création, liste, suppression  
✅ **Webhooks** : abonnement et gestion avancée  
✅ **WABA Management** : gestion des comptes WhatsApp Business  
✅ **Utilitaires** : debug de tokens, validation de numéros  

📚 **Documentation complète :**
- [Guide complet de l'API](./WHATSAPP_API_COMPLETE_GUIDE.md) - Documentation détaillée de tous les endpoints
- [Démarrage rapide](./WHATSAPP_API_QUICK_START.md) - Configuration en 5 minutes

🚀 **Pour activer ces fonctionnalités :**
1. Appliquez la migration SQL : `supabase/migrations/011_whatsapp_extended_fields.sql`
2. Ajoutez `META_APP_ID` et `META_APP_SECRET` à votre `.env`
3. Explorez tous les endpoints dans Swagger UI : http://localhost:8000/docs

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
GEMINI_API_KEY=sk-xxx
# optionnel, change le modèle si nécessaire
GEMINI_MODEL=gemini-1.5-flash
HUMAN_BACKUP_NUMBER=+33123456789
PROMETHEUS_ENABLED=true
PROMETHEUS_METRICS_PATH=/metrics
PROMETHEUS_APP_LABEL=whatsapp_inbox_api
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

### Assistant Gemini

- Active le toggle **Bot** dans l'en-tête d'une conversation pour laisser Gemini répondre automatiquement (un badge « Bot » est visible dans la liste).
- L’onglet **Assistant Gemini** (icône CPU dans la barre latérale) contient maintenant un **template structuré** :
  1. Règles système (langue, ton, mission, style, sécurité…)
  2. Infos entreprise (adresse, zone, rendez-vous, activité…)
  3. Offres / produits par catégorie (tableau libre)
  4. Conditions & documents
  5. Procédures simplifiées
  6. FAQ
  7. Cas spéciaux (réponses standardisées)
  8. Liens utiles
  9. Escalade humain (procédure interne)
  10. Règles spéciales
- Chaque bloc alimente automatiquement le prompt (visible dans la section “Aperçu généré”). Clique sur **“Copier dans la base”** si tu veux tout déverser dans la zone libre.
- Si une information est absente du template, le bot répond strictement : *« Je me renseigne auprès d’un collègue et je reviens vers vous au plus vite. »* et `HUMAN_BACKUP_NUMBER` reçoit un SMS/WhatsApp d’alerte (si renseigné).
- Les pièces jointes (audio / image / vidéo) déclenchent automatiquement : *« Je ne peux pas lire ce type de contenu, peux-tu me l'écrire ? »*.

### Docker
`docker-compose.yml` charge automatiquement les fichiers `.env` ci-dessus.

## Base de données

1. Appliquer `supabase/schema/001_init_whatsapp_inbox.sql`
2. Pour les instances existantes, exécuter également `002_update_contacts_messages.sql`
3. Pour activer le multi-compte, lancer `003_multitenant_accounts.sql` (il crée un compte “Legacy account” temporaire puis assigne toutes les conversations dessus ; il sera automatiquement synchronisé avec tes variables `.env` dès que le backend redémarre)
4. Pour les filtres (favoris, non lues, groupes), appliquer `004_conversation_flags.sql` qui ajoute `is_favorite`, `is_group`, `unread_count`
5. **RBAC / permissions** : exécuter `005_rbac.sql` pour créer les tables `app_users`, `app_roles`, `app_permissions`, etc. La première personne qui se connecte obtient automatiquement le rôle `admin`.
6. **Médias** : appliquer `006_message_media.sql` qui ajoute `media_id`, `media_mime_type`, `media_filename` aux messages pour pouvoir diffuser audio / images côté interface.
7. **Bot Gemini** : `007_gemini_bot.sql` ajoute `bot_enabled`, `bot_last_reply_at` et la table `bot_profiles`.
8. **Template bot** : `008_bot_template.sql` ajoute la colonne `template_config` (JSON) pour stocker le playbook.

### Table `whatsapp_accounts`

| Colonne            | Description                                    |
|--------------------|------------------------------------------------|
| `name`, `slug`     | Nom lisible + identifiant unique                |
| `phone_number`     | Numéro affiché (facultatif)                     |
| `phone_number_id`  | ID fourni par Meta                             |
| `access_token`     | Token d’accès au Graph API                     |
| `verify_token`     | Token utilisé lors du handshake webhook        |

Le backend synchronise automatiquement un compte "par défaut" à partir des variables d'environnement ci-dessus. Pour ajouter d'autres comptes, insère de nouvelles lignes dans `whatsapp_accounts` (via Supabase SQL ou l'UI) avec leurs tokens respectifs. L'interface affiche ensuite un sélecteur pour passer d'un compte à l'autre.

### Images de profil

Le système récupère automatiquement les images de profil des contacts via WhatsApp Graph API. Les images sont stockées dans Supabase Storage et mises à jour automatiquement toutes les heures.

**Note** : WhatsApp Graph API a des limitations pour récupérer les images de profil. Certaines images peuvent ne pas être disponibles selon les permissions et la configuration de votre compte WhatsApp Business.

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

### Monitoring continu (dev & prod)

- L'appli expose désormais `/metrics` (Prometheus) dès que `PROMETHEUS_ENABLED=true`.
- En local, lance la stack avec Prometheus + Grafana déjà configurés :
  ```bash
  docker compose up backend frontend prometheus grafana
  ```
  - Prometheus : http://localhost:9090 (scrute `backend:8000`)
  - Grafana : http://localhost:3001 (login par défaut `admin/admin`, à changer dans `docker-compose.yml`)
- En production, `deploy/docker-compose.prod.yml` embarque les mêmes services :
  - Prometheus reste interne (pas de port exposé).
  - Grafana est accessible via `https://ton-domaine/grafana` derrière Caddy (auth Grafana obligatoire).
- Ajoute tes dashboards Prometheus/Grafana favoris ou importe un template FastAPI (ID 14369) pour suivre latence P95, requêtes/minute, erreurs 4xx/5xx, etc.

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

## Déploiement OVH (VPS + Caddy + Docker)

> Objectif : garder un coût très bas (~15 €/mois) tout en automatisant le `git push → prod`.

### 1. Provisionner un VPS

- **OVH VPS Essential (2 vCPU / 4 Go / 80 Go SSD)** ≈ 13 € / mois.
- Ajoute un nom de domaine (~1 € / mois) et un enregistrement `A` vers l’IP du VPS.
- Supabase (base de données + auth) reste sur l’offre gratuite pour des charges modestes.

### 2. Préparer le serveur

```bash
sudo apt update && sudo apt install -y git curl ca-certificates
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo apt install docker-compose-plugin
mkdir -p /opt/whatsapp-inbox
```

Clone ton repo dans `/opt/whatsapp-inbox` et copie les `.env` :

```
scp backend/.env vps:/opt/whatsapp-inbox/backend/.env
scp frontend/.env vps:/opt/whatsapp-inbox/frontend/.env
```

**Important** : Créez également un fichier `deploy/.env` avec les variables nécessaires pour Caddy et Grafana (le workflow GitHub le génère automatiquement depuis les secrets `OVH_DOMAIN` et `OVH_TLS_EMAIL`, mais en déploiement manuel vous devez le créer vous‑même) :

```bash
cd deploy
cat > .env << EOF
DOMAIN=votre-domaine.com
EMAIL=votre-email@example.com
EOF
```

Ou utilisez le script automatique :
```powershell
cd deploy
.\setup-env.ps1
```

Ce fichier est nécessaire pour que Caddy puisse générer les certificats SSL et que Grafana soit correctement configuré (et il est créé automatiquement par la GitHub Action lors des déploiements vers OVH).

### 3. Stack Docker prête à l'emploi

- `deploy/docker-compose.prod.yml` : backend, frontend et **Caddy** (reverse proxy HTTPS auto).
- `deploy/Caddyfile` : reverse proxy + sécurité HTTP (HSTS, Referrer Policy, etc.).
- `deploy/deploy.sh` : script idempotent (git pull + `docker compose up -d --build` + reload automatique de Caddy + prune des images).
- `monitoring/prometheus/prometheus.yml` : configuration Prometheus partagée dev/prod.
- Grafana est déjà branché sur Prometheus et exposé via `https://{$DOMAIN}/grafana` (utilise les creds définis dans `docker-compose.prod.yml`).

Usage manuel :

```bash
cd /opt/whatsapp-inbox
chmod +x deploy/deploy.sh

# Créer le fichier deploy/.env (ou utiliser setup-env.ps1 sur Windows)
cd deploy
cat > .env << EOF
DOMAIN=chat.example.com
EMAIL=admin@example.com
EOF

# Déployer
./deploy.sh
```

**Note** : Le fichier `deploy/.env` est maintenant requis pour que Caddy et Grafana fonctionnent correctement. Il sera automatiquement chargé par docker-compose.

### 4. Action GitHub automatique

Le workflow `.github/workflows/deploy-ovh.yml` :

1. Push sur `main`.
2. `rsync` des fichiers vers `/opt/whatsapp-inbox`.
3. SSH + exécution de `deploy/deploy.sh`.

Secrets requis côté GitHub :

| Secret            | Contenu                                  |
|-------------------|------------------------------------------|
| `OVH_HOST`        | IP ou domaine du VPS                      |
| `OVH_USER`        | Utilisateur SSH                           |
| `OVH_SSH_KEY`     | Clé privée (deploy key)                   |
| `OVH_DOMAIN`      | Domaine public (ex. `chat.example.com`)   |
| `OVH_TLS_EMAIL`   | Email pour Let’s Encrypt                  |
| `BACKEND_ENV`     | Contenu complet de `backend/.env`         |
| `FRONTEND_ENV`    | Contenu complet de `frontend/.env`        |

> Tu peux déclencher le workflow manuellement via **Actions → Deploy to OVH → Run workflow** si tu veux déployer sans commit.

### 5. Sécurité

- Caddy force HTTPS + entêtes de sécurité.
- `backend/.env` et `frontend/.env` ne sont jamais commités (copiés via SCP ou Secret Manager).
- Docker tourne en réseau privé `appnet` ; seul Caddy expose 80/443.
- `HUMAN_BACKUP_NUMBER` et les clés Meta sont chargés via `.env`.

### Mettre à jour les fichiers `.env`

Les secrets vivent dans `backend/.env` et `frontend/.env`. Pour les modifier :

1. Mets à jour les fichiers **en local** (dans ton repo).
2. Copie-les sur le serveur :

   ```bash
   cd D:\Code\whatsapp-inbox  # ou ton dossier local
   scp backend/.env ubuntu@217.182.65.32:/opt/whatsapp-inbox/backend/.env
   scp frontend/.env ubuntu@217.182.65.32:/opt/whatsapp-inbox/frontend/.env
   ```

3. Redeploie pour recharger les nouveaux secrets :

   ```bash
    ssh ubuntu@217.182.65.32
    cd /opt/whatsapp-inbox/deploy
    export DOMAIN=whatsapp.lamaisonduchauffeurvtc.fr
    export EMAIL=ton.email@domaine.com
    bash deploy.sh
   ```

Les workflows GitHub n’écrasent pas ces fichiers (ils sont listés dans `.gitignore`). Si tu veux aller plus loin, tu peux utiliser un gestionnaire de secrets (OVH Secret Manager, Hashicorp Vault…) pour les injecter dynamiquement avant `docker compose up`, mais pour un petit setup, l’étape `scp + deploy.sh` reste la plus simple et sûre.

> **Option automatisée :** tu peux stocker le contenu complet des `.env` dans les secrets GitHub `BACKEND_ENV` et `FRONTEND_ENV` (multiligne, par exemple en collant directement le fichier entre guillemets). Le workflow `Deploy to OVH` réécrira automatiquement `backend/.env` et `frontend/.env` sur le serveur avant chaque déploiement.

### 6. Coûts & scalabilité

| Poste                                  | Estimation mensuelle |
|----------------------------------------|----------------------|
| OVH VPS Essential                      | ~13 €                |
| Nom de domaine                         | ~1 €                 |
| Supabase (plan gratuit)                | 0 € (jusqu’à 500 Mo) |
| Let’s Encrypt / Caddy                  | 0 €                  |

**Scalabilité** :

- Démarre sur le VPS Essential. Si la charge augmente, passe en **VPS Advance** (6 vCPU / 8 Go, ~25 €).
- Au-delà, bascule vers *OVH Managed Kubernetes* : pousse tes images sur GHCR/Docker Hub et réutilise la même stack (backend+frontend+caddy) sous forme de deployments + services + ingress.
- La base Supabase peut passer au plan Pro (25 $) si tu dépasses les quotas gratuits.

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


