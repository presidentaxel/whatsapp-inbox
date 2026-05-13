# Dépannage (premier incident)

Guide **symptôme → pistes**. Toujours joindre le message d’erreur complet et la couche concernée (backend, frontend, Meta, Supabase).

## Webhook WhatsApp / Meta

| Symptôme | Pistes |
|----------|--------|
| Aucun événement reçu | URL webhook HTTPS accessible depuis Internet ; pas d’auth Basic « en trop » devant Meta ; vérifier le chemin configuré chez Meta vs route FastAPI / reverse proxy (`deploy/Caddyfile` : route `/webhook`). |
| 403 / signature invalide | `WHATSAPP_VERIFY_TOKEN` (challenge GET) et secret d’app pour la signature POST - alignés avec la config Meta. |
| Timeout ou 5xx | Logs backend au moment du POST ; limites rate ; base ou Supabase injoignable depuis le serveur. |

## Auth / JWT / Supabase côté UI

| Symptôme | Pistes |
|----------|--------|
| 401 sur l’API après login | JWT expiré ou non transmis ; URL Supabase / clé anon vs service ; CORS si origine différente. |
| Données vides alors que la DB a des lignes | Politiques **RLS** : l’utilisateur n’a pas le droit de lire les lignes concernées. |

## Base de données et migrations

| Symptôme | Pistes |
|----------|--------|
| Erreur au démarrage après `git pull` | Nouvelles migrations dans `supabase/migrations` : les appliquer sur l’instance locale / staging. |
| Contrainte unique / FK | Vérifier l’ordre des inserts et les IDs référencés. |

## Frontend

| Symptôme | Pistes |
|----------|--------|
| `npm run build` échoue | Lire la première erreur TypeScript/ESLint ; `npm ci` pour resynchroniser les lockfiles. |
| App blanche | Console navigateur ; variable d’env Vite manquante (souvent préfixe `VITE_`). |

## Backend - import / config

| Symptôme | Pistes |
|----------|--------|
| Crash au démarrage sur une variable manquante | Comparer avec `backend/.env.example` ; en CI des mocks sont utilisés ([`test.yml`](../../.github/workflows/test.yml)). |
| `pytest` échoue | Lancer depuis `backend/` ; certaines suites peuvent nécessiter des variables ou mocks selon les tests. |

## Docker / déploiement

- Vérifier `BACKEND_URL` et les services attendus dans `deploy/docker-compose.prod.yml` (validés en CI).
- Pour le dev local, voir `docker-compose.yml` à la racine du dépôt et le [README](../../README.md).

## Si rien ne matche

1. Réduire le problème (reproductible sur une branche minimale).
2. Ouvrir une issue ou demander au buddy avec : **commande exacte**, **fichiers de config masqués** (valeurs fictives), **extrait de logs**.
