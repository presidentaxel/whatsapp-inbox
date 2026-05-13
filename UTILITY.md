# Commandes utiles

Conventions : **Ubuntu / Linux** = bloc `bash`. **Windows** = bloc `powershell` (PowerShell 5+ ou 7+). Quand une seule étiquette « Shell » suffit (commandes identiques), le bloc est en `bash` mais valable aussi dans PowerShell.

---

## Lancer l'app (local)

**Ubuntu / Linux (bash)**

```bash
cd backend
# python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

cd frontend
npm install
npm run dev
```

**Windows (PowerShell)**

```powershell
cd backend
# py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload

cd frontend
npm install
npm run dev
```

---

## Docker tests (local)

Même syntaxe sous bash et PowerShell à la racine du dépôt :

```bash
docker compose build
docker compose up
```

---

## Push GitHub

```bash
git add .
git commit -m "****"
git push
```

---

## Supabase push (local)

```bash
# npx supabase login
# npx supabase link --project-ref TON_PROJECT_REF
npx supabase migration list
npx supabase db push
```

---

## Serveur — GitHub pull

Les commandes après `ssh` s’exécutent sur le serveur Ubuntu (shell bash).

**Ubuntu / Linux (bash) ou Windows (PowerShell)** — jusqu’au `ssh`, la ligne est la même :

```bash
ssh ubuntu@217.182.65.32
cd /opt/whatsapp-inbox/deploy
git pull
```

---

## .env — variables puis recréation du backend

Après `ssh` (session sur le serveur) :

```bash
cd /opt/whatsapp-inbox/backend
sudo nano .env
cd ../deploy
sudo docker compose -f docker-compose.prod.yml up -d --force-recreate backend
```

---

## Accès aux logs

Après `ssh` :

```bash
# backend
cd /opt/whatsapp-inbox/deploy
docker compose -f docker-compose.prod.yml logs -f backend

# frontend
cd /opt/whatsapp-inbox/deploy
docker compose -f docker-compose.prod.yml logs -f frontend
```

---

## Rebuild

Après `ssh` :

```bash
# frontend
cd /opt/whatsapp-inbox/deploy
docker compose -f docker-compose.prod.yml stop frontend
docker compose -f docker-compose.prod.yml build --no-cache frontend
docker compose -f docker-compose.prod.yml up -d frontend

# backend
cd /opt/whatsapp-inbox/deploy
docker compose -f docker-compose.prod.yml stop backend
docker compose -f docker-compose.prod.yml build --no-cache backend
docker compose -f docker-compose.prod.yml up -d backend

# caddy
cd /opt/whatsapp-inbox/deploy
docker compose -f docker-compose.prod.yml stop caddy
docker compose -f docker-compose.prod.yml pull caddy
docker compose -f docker-compose.prod.yml up -d --force-recreate caddy

# rebuild complet
cd /opt/whatsapp-inbox/deploy
# 1) Prépare les nouvelles images pendant que l'app tourne encore
docker compose -f docker-compose.prod.yml build --no-cache backend frontend
docker compose -f docker-compose.prod.yml pull caddy prometheus grafana
# 2) Recrée seulement les services modifiés (un par un)
docker compose -f docker-compose.prod.yml up -d --no-deps backend
docker compose -f docker-compose.prod.yml up -d --no-deps frontend
# 3) (optionnel) Met à jour les autres sans forcer de restart inutile
docker compose -f docker-compose.prod.yml up -d caddy prometheus grafana
```

---

## Grafana — reset mot de passe admin

Après `ssh` :

```bash
cd /opt/whatsapp-inbox/deploy
docker compose -f docker-compose.prod.yml exec grafana grafana-cli admin reset-admin-password "votre_nouveau_mot_de_passe"
```

