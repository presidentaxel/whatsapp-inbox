# Glossaire - équipe

Ce fichier rassemble le **vocabulaire métier** (WhatsApp / Meta), le **vocabulaire produit** (notre app) et des **termes techniques** qu’on croise dans le dépôt. Il complète le [README](../../README.md) et le notebook d’installation : pas besoin de tout mémoriser - utiliser `Ctrl+F` ici quand un message est opaque.

**Lecture conseillée** : section *Meta & WhatsApp* → *Compte & multicompte* → *Supabase* → *Projet WhatsApp Inbox*.

---

## Meta & WhatsApp Cloud API


| Terme                                    | Explication courte                                                                                                                                                                                              |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Meta**                                 | Société mère de Facebook, Instagram, WhatsApp ; héberge l’**API Cloud** et le **Business Manager**.                                                                                                             |
| **WhatsApp Cloud API**                   | API **officielle** HTTP pour envoyer/recevoir des messages WhatsApp Business ; alternative historique : API On-Premises (hébergée chez le client).                                                              |
| **Graph API**                            | API HTTP de Meta (`graph.facebook.com`) utilisée pour envoyer des messages, gérer les templates, médias, etc. - en parallèle du **webhook** qui *reçoit* les événements.                                        |
| **WABA**                                 | *WhatsApp Business Account* : le compte **entreprise** WhatsApp rattaché à l’API (un client peut avoir plusieurs numéros sous une WABA).                                                                        |
| **Business Manager**                     | Espace Meta pour gérer entreprises, actifs, utilisateurs et **apps** ; souvent nécessaire pour lier la WABA à ton application.                                                                                  |
| **App Meta / application**               | Projet enregistré chez Meta Developers ; fournit **App ID**, **App Secret**, produits (WhatsApp), tokens.                                                                                                       |
| `**META_APP_ID` / `META_APP_SECRET`**    | Identifiants de l’app Meta ; le **secret** sert entre autres à **vérifier la signature** des webhooks (`X-Hub-Signature-256`).                                                                                  |
| `**WHATSAPP_TOKEN`**                     | *Access token* (souvent **long-lived**) autorisant les appels **sortants** vers la Graph API (envoi message, upload média, etc.).                                                                               |
| **Phone Number ID**                      | Identifiant **technique** du numéro WhatsApp Business côté API (`WHATSAPP_PHONE_ID`) - ce n’est pas toujours le numéro affiché (`WHATSAPP_PHONE_NUMBER`).                                                       |
| **Webhook**                              | URL **HTTPS** publique où **Meta envoie** les événements (messages entrants, statuts, erreurs). Notre backend **vérifie** l’origine puis traite le JSON.                                                        |
| **Challenge GET (vérification webhook)** | Lors de l’enregistrement de l’URL, Meta envoie un GET avec un paramètre `hub.verify_token` : le serveur doit répondre avec le `hub.challenge` si le token correspond à `WHATSAPP_VERIFY_TOKEN`.                 |
| `**X-Hub-Signature-256*`*                | En-tête contenant une **signature HMAC** du corps du POST ; le backend la recalcule avec `META_APP_SECRET` pour s’assurer que le payload vient bien de Meta (`WEBHOOK_SIGNATURE_REQUIRED` dans `.env.example`). |
| **Template (modèle HSM)**                | Message **pré-validé** par Meta avec un nom, une langue, des variables (`{{1}}`, etc.) ; obligatoire pour certains envois **hors fenêtre de session** (voir ci-dessous).                                        |
| **Catégorie de template**                | Souvent **MARKETING** (promotions) ou **UTILITY** (transactionnel : livraison, rappel de RDV…) ; les règles d’opt-in et de contenu diffèrent.                                                                   |
| **Statut de template**                   | Côté Meta : typiquement **PENDING** (en revue), **APPROVED**, **REJECTED** - visible dans le Business Manager ou via l’API.                                                                                     |
| **Fenêtre de 24 h / session messaging**  | Après le **dernier message du client**, l’entreprise peut répondre en **message libre** pendant ~24 h ; **après**, le premier message entreprise→client doit souvent passer par un **template** approuvé.       |
| **Opt-in**                               | Consentement du client à recevoir des messages WhatsApp ; requis surtout pour le marketing et les templates.                                                                                                    |
| **Média (handle / id)**                  | WhatsApp identifie un fichier par un **id** ; le backend peut télécharger via une **URL** fournie par Meta (souvent avec le bearer token).                                                                      |
| **CDN Meta**                             | Les URLs média pointent vers les serveurs Meta ; le téléchargement utilise en général l’**Authorization: Bearer** du token WhatsApp.                                                                            |
| **Code d’erreur Meta**                   | Ex. erreurs numériques dans les réponses API ou webhooks (template rejeté, numéro invalide…) - utiles à copier-coller dans le troubleshooting.                                                                  |


---

## Messages, statuts & conversations


| Terme                            | Explication courte                                                                                                                                               |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Conversation (thread)**        | Fil continu entre un **contact** (numéro client) et une **ligne** WhatsApp Business ; dans l’app, c’est la « discussion » affichée.                              |
| **Message entrant / sortant**    | **Entrant** : du client vers l’entreprise ; **sortant** : de l’entreprise (ou de l’outil) vers le client.                                                        |
| **Statut de message**            | Cycle typique côté WhatsApp : **sent** (accepté par les serveurs) → **delivered** (livré sur l’appareil) → **read** (lu) ; peut aussi **failed**.                |
| **Webhook `statuses`**           | Notifications Meta quand un message change de statut (livré, lu, échec).                                                                                         |
| **Pièce jointe / PJ**            | Image, PDF, audio, etc. - peut nécessiter **sniff MIME** (magic bytes) si Meta renvoie `application/octet-stream` (voir `storage_service` et migrations bucket). |
| **Réaction**                     | Emoji sur un message ; traité comme un type d’événement dans le flux webhook.                                                                                    |
| **Réponse citée (quoted reply)** | Message qui référence un message précédent (contexte `context` dans le payload WhatsApp).                                                                        |


---

## Compte, multicompte & déploiement


| Terme                              | Explication courte                                                                                                                                   |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Compte (account)**               | Dans l’app : une **ligne WhatsApp** (token, phone id, WABA…) configurée en base ; on peut en gérer **plusieurs** (*multicompte*).                    |
| `**account_id` / slug**            | Identifiant interne ou nom lisible (`DEFAULT_ACCOUNT_SLUG` dans `.env.example`) pour router webhook et API vers la bonne config.                     |
| `**waba_id`**                      | Identifiant Meta de la WABA ; utile pour support et scripts de synchro.                                                                              |
| `**BACKEND_URL` / `FRONTEND_URL**` | URLs utilisées pour CORS, liens, webhooks publics, etc.                                                                                              |
| **CORS**                           | Mécanisme navigateur : le frontend (origine A) n’appelle le backend (origine B) que si B **autorise** explicitement A (`CORS_ORIGINS_*` dans l’env). |


---

## Supabase, Postgres & auth


| Terme                        | Explication courte                                                                                                                                                             |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Supabase**                 | Plateforme « backend as a service » : **Postgres**, **Auth**, **Storage**, parfois **Edge Functions**.                                                                         |
| `**SUPABASE_URL`**           | URL du projet (`https://xxx.supabase.co`).                                                                                                                                     |
| `**SUPABASE_KEY` (backend)** | Dans notre `.env.example` : clé **service_role** - **privilèges élevés**, uniquement **côté serveur**, jamais dans le navigateur.                                              |
| **Clé `anon`**               | Clé publique côté client ; les accès données sont limitées par **RLS**.                                                                                                        |
| **RLS**                      | *Row Level Security* : règles SQL qui décident **quelle ligne** un utilisateur peut lire/écrire selon son JWT ou rôle.                                                         |
| **JWT**                      | Jeton signé (souvent après login Supabase Auth) ; prouve l’identité de l’**opérateur** dans l’UI.                                                                              |
| **Migration**                | Fichier SQL versionné dans `supabase/migrations/` qui modifie le schéma ; à appliquer dans l’ordre sur chaque environnement.                                                   |
| **Storage / bucket**         | Espace fichiers (ex. `message-media`, `profile-pictures`) avec **types MIME** autorisés par politique.                                                                         |
| **Edge Function**            | Fonction serverless hébergée chez Supabase ; le dépôt mentionne une fonction type webhook avec **secrets** distincts des vars `SUPABASE_*` (voir commentaires `.env.example`). |


---

## Produit WhatsApp Inbox (ce dépôt)


| Terme                                        | Explication courte                                                                                                                                                                          |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Boîte / inbox**                            | Interface où les **opérateurs** voient les conversations et répondent (remplace le téléphone partagé).                                                                                      |
| **Opérateur**                                | Utilisateur humain connecté via Supabase Auth ; droits selon rôles / RLS.                                                                                                                   |
| **Axelia**                                   | Assistant IA (Gemini) intégré au CRM : réponses, brouillons, outils **contrôlés** ; ne remplace pas la validation humaine pour les actions sensibles (templates, blocages…).                |
| `**AXELIA_FAST_MODEL` / `AXELIA_PRO_MODEL`** | Modèles Gemini utilisés pour des réponses rapides vs plus « lourdes » / qualitatives.                                                                                                       |
| **Bot profile / profil bot**                 | Configuration côté produit (comportement, flux par défaut, etc.) liée au compte / à l’IA.                                                                                                   |
| **Playground (flux)**                        | Graphe de scénario (nœuds / arêtes) édité dans l’UI ; stocké en base (`playground_flows`). Sert aux automatisations / campagnes sandbox selon le **trigger** (`playground_audience`, etc.). |
| **Broadcast**                                | Envoi **à une liste** (groupe de destinataires, campagne) plutôt qu’une conversation 1-to-1 ; routes et services `broadcast_*`.                                                             |
| **Campagne**                                 | Instance d’envoi broadcast (ciblage, statut, progression).                                                                                                                                  |
| **Groupe de diffusion**                      | Liste de contacts / numéros rattachés à une campagne broadcast.                                                                                                                             |
| **Pending template**                         | File ou état intermédiaire quand un **template** est en cours de création / validation / envoi (logique métier `pending_template`).                                                         |
| **Human backup / escalade**                  | Numéro optionnel (`HUMAN_BACKUP_NUMBER`) pour transférer vers un humain en dehors du flux auto.                                                                                             |
| **Prometheus / Grafana**                     | **Métriques** (compteurs, latences) et **tableaux de bord** ; endpoint `/metrics` potentiellement protégé par token.                                                                        |
| `**slowapi` / rate limit**                   | Limitation du nombre de requêtes par minute (globale, auth, webhook, IA) pour protéger l’API.                                                                                               |


---

## Stack technique (backend & frontend)


| Terme                 | Explication courte                                                                                               |
| --------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **FastAPI**           | Framework Python **async** pour exposer des routes HTTP / WebSocket ; génère aussi la doc **OpenAPI** (`/docs`). |
| **Uvicorn**           | Serveur ASGI qui exécute l’app FastAPI.                                                                          |
| **Pydantic**          | Validation et modèles de données (v2 dans ce projet) pour les payloads JSON.                                     |
| `**httpx`**           | Client HTTP async pour appeler Meta, Supabase HTTP, etc.                                                         |
| `**asyncpg**`         | Driver Postgres **async** pour du SQL direct quand on ne passe pas par le client Supabase.                       |
| **Route**             | Point d’entrée HTTP (`routes_webhook`, `routes_accounts`, … sous `app/api/`).                                    |
| **Service**           | Couche **métier** (gros fichiers sous `app/services/`) appelée par les routes.                                   |
| **React**             | Bibliothèque UI par composants ; ici React 18.                                                                   |
| **Vite**              | Outil de build / dev server très rapide pour le frontend.                                                        |
| **SPA**               | *Single Page Application* : une seule page HTML, la navigation se fait côté client (React Router).               |
| `**VITE_…`**          | Préfixe des variables d’environnement **exposées au navigateur** par Vite (ne jamais y mettre de secret).        |
| **Vitest**            | Framework de tests unitaires / composants pour le frontend.                                                      |
| **ESLint / Prettier** | **Lint** = règles de qualité de code ; **Prettier** = formatage automatique.                                     |
| `**pytest`**          | Framework de tests Python pour le backend (`backend/tests/`).                                                    |


---

## Git, CI & collaboration


| Terme                 | Explication courte                                                                                                       |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **PR (Pull Request)** | Demande de fusion d’une branche vers `main` / `master` ; l’équipe **review** avant merge.                                |
| **CI**                | *Continuous Integration* : à chaque push/PR, GitHub Actions lance des vérifications (voir `.github/workflows/test.yml`). |
| **Lockfile**          | `package-lock.json` : fige les versions npm ; `**npm ci`** installe exactement ce fichier (recommandé en CI).            |


---

## Voir aussi

- [troubleshooting.md](./troubleshooting.md) - quand un terme ci-dessus « claque » en prod ou en local.
- [securite-conformite.md](./securite-conformite.md) - secrets, logs, données personnelles.
- `[backend/.env.example](../../backend/.env.example)` - noms exacts des variables et commentaires courts.

