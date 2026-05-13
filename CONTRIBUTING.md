# Contribuer à WhatsApp Inbox

Ce document décrit le flux technique : branches, qualité de code, tests et emplacements utiles dans le dépôt. Pour l’onboarding humain (buddy, accès, première semaine), voir [docs/equipe/README.md](./docs/equipe/README.md).

## Prérequis

- Python **3.11** (aligné avec la CI)
- Node **≥ 20**
- Git

L’installation depuis une machine vide est décrite dans le notebook [`notebooks/EQUIPE_ONBOARDING_FROM_ZERO.ipynb`](./notebooks/EQUIPE_ONBOARDING_FROM_ZERO.ipynb) - il est **autonome** (envoyable par mail avec seulement l’URL du dépôt dans le message).

## Vérifier comme la CI (recommandé avant push)

Même logique que les jobs **test-backend** et **test-frontend** de [`.github/workflows/test.yml`](./.github/workflows/test.yml) :

- **Avec Make** : `make check` à la racine du dépôt
- **Avec npm** : `npm run ci:check` à la racine (nécessite Node ; installe les dépendances Python et npm aux emplacements attendus)

Python **3.11** est requis (comme en CI). Si la commande `python` par défaut pointe vers une autre version (souvent le cas sur Windows), définissez la variable d’environnement `PYTHON` avec le chemin de l’exécutable 3.11 avant de lancer les vérifications (ex. `PYTHON=%LocalAppData%\Programs\Python\Python311\python.exe` sous cmd, ou l’équivalent PowerShell).

Hooks Git optionnels (même linter backend + `eslint` frontend que la CI, via les scripts `lint:ci`) :

```bash
pip install pre-commit
pre-commit install
```

## Branches et pull requests

- Travailler depuis une branche dédiée (`feat/…`, `fix/…`, `chore/…`).
- Ouvrir une **pull request** vers `main` ou `master` (branches suivies par la CI, voir [`.github/workflows/test.yml`](./.github/workflows/test.yml)).
- Décrire le **pourquoi** et le **comportement attendu** ; joindre captures ou extraits de logs si pertinent.
- Garder les PR **reviewables** : préférer plusieurs petites PR à un énorme diff sauf nécessité réelle.
- Ne jamais committer de **secrets** (tokens Meta, clés Supabase, Gemini, mots de passe). Utiliser `backend/.env.example` comme référence et des fichiers `.env` locaux ou secrets CI.

## Backend (FastAPI)

Répertoire : `backend/`

```bash
cd backend
python -m pip install -r requirements.txt
python -m pip install ruff
# Variables d’environnement : copier depuis .env.example puis adapter

# Tests unitaires
pytest

# Aligné avec la CI : compilation + ruff (voir aussi make check / npm run ci:check)
python -m py_compile app/main.py
python -m ruff check app
```

Les routes principales vivent sous `app/api/` ; la configuration sous `app/core/`.

## Frontend (React + Vite)

Répertoire : `frontend/`

```bash
cd frontend
npm ci
npm run lint
npm run format:check
npm run test
npm run build
```

Les commandes `lint:ci`, `build:ci` et `test:ci` injectent des variables Vite factices pour reproduire la CI sans fichier `.env` local.

## Supabase

- Schéma et historique : [`supabase/migrations`](./supabase/migrations) ; point d’entrée [`supabase/schema/README.md`](./supabase/schema/README.md). Politique / squash : [`docs/equipe/supabase-source-of-truth.md`](./docs/equipe/supabase-source-of-truth.md).
- Toute évolution de schéma doit passer par des **migrations versionnées** et être documentée dans la PR.

## Où toucher le code selon le sujet


| Sujet                              | Emplacement indicatif                        |
| ---------------------------------- | -------------------------------------------- |
| Webhook WhatsApp, envoi, templates | `backend/app/` (routes, services)            |
| UI boîte, conversation             | `frontend/src/`                              |
| Auth / politiques / données        | `supabase/`, backend + frontend selon le cas |
| Déploiement, reverse proxy         | `deploy/`                                    |


## Aide et dépannage

- [docs/equipe/troubleshooting.md](./docs/equipe/troubleshooting.md) - incidents fréquents (webhook, auth, Supabase).
- Signalement **sécurité** : [SECURITY.md](./SECURITY.md).
- Joindre les **messages d’erreur complets** et la version des dépendances quand vous ouvrez une discussion ou une issue.
