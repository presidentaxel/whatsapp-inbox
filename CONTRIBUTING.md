# Contribuer à WhatsApp Inbox

Ce document décrit le flux technique : branches, qualité de code, tests et emplacements utiles dans le dépôt. Pour l’onboarding humain (buddy, accès, première semaine), voir [docs/equipe/README.md](./docs/equipe/README.md).

## Prérequis

- Python **3.11** (aligné avec la CI)
- Node **≥ 20**
- Git

L’installation depuis une machine vide est décrite dans le notebook [`notebooks/EQUIPE_ONBOARDING_FROM_ZERO.ipynb`](./notebooks/EQUIPE_ONBOARDING_FROM_ZERO.ipynb) - il est **autonome** (envoyable par mail avec seulement l’URL du dépôt dans le message).

## Branches et pull requests

- Travailler depuis une branche dédiée (`feat/…`, `fix/…`, `chore/…`).
- Ouvrir une **pull request** vers `main` ou `master` (branches suivies par la CI, voir `[.github/workflows/test.yml](./.github/workflows/test.yml)`).
- Décrire le **pourquoi** et le **comportement attendu** ; joindre captures ou extraits de logs si pertinent.
- Garder les PR **reviewables** : préférer plusieurs petites PR à un énorme diff sauf nécessité réelle.
- Ne jamais committer de **secrets** (tokens Meta, clés Supabase, Gemini, mots de passe). Utiliser `backend/.env.example` comme référence et des fichiers `.env` locaux ou secrets CI.

## Backend (FastAPI)

Répertoire : `backend/`

```bash
cd backend
python -m pip install -r requirements.txt
# Variables d’environnement : copier depuis .env.example puis adapter

# Tests
pytest

# Aligné avec la CI : compilation + flake8 (voir workflow pour les flags exacts)
python -m py_compile app/main.py
flake8 app --count --select=E9,F63,F7,F82 --show-source --statistics
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
- Joindre les **messages d’erreur complets** et la version des dépendances quand vous ouvrez une discussion ou une issue.

