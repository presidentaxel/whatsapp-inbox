## Lancer l'app
```bash
# backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
# frontend
cd frontend
npm install
npm run dev
```

## Docker tests
```bash
#ouvrir docker
docker compose build
docker compose up
```

## Push Online
```bash
git add .
git commit -m "****"
git push
```

## .env variables changes
```bash
ssh ubuntu@217.182.65.32
cd /opt/whatsapp-inbox/backend
sudo nano .env
cd ../deploy
sudo docker compose -f docker-compose.prod.yml up -d --force-recreate backend
```

## Accès aux logs
```bash
#backend
ssh ubuntu@217.182.65.32
cd /opt/whatsapp-inbox/deploy
docker compose -f docker-compose.prod.yml logs -f backend
#frontend
ssh ubuntu@217.182.65.32
cd /opt/whatsapp-inbox/deploy
docker compose -f docker-compose.prod.yml logs -f frontend
```

## Rebuild
```bash
#frontend
ssh ubuntu@217.182.65.32
cd /opt/whatsapp-inbox/deploy
docker compose -f docker-compose.prod.yml stop frontend
docker compose -f docker-compose.prod.yml build --no-cache frontend
docker compose -f docker-compose.prod.yml up -d frontend

#backend
ssh ubuntu@217.182.65.32
cd /opt/whatsapp-inbox/deploy
docker compose -f docker-compose.prod.yml stop backend
docker compose -f docker-compose.prod.yml build --no-cache backend
docker compose -f docker-compose.prod.yml up -d backend

#caddy
ssh ubuntu@217.182.65.32
cd /opt/whatsapp-inbox/deploy
docker compose -f docker-compose.prod.yml stop caddy
docker compose -f docker-compose.prod.yml pull caddy
docker compose -f docker-compose.prod.yml up -d --force-recreate caddy

#rebuild complet
ssh ubuntu@217.182.65.32
cd /opt/whatsapp-inbox/deploy
docker compose -f docker-compose.prod.yml stop
docker compose -f docker-compose.prod.yml build --no-cache backend frontend
docker compose -f docker-compose.prod.yml pull caddy prometheus grafana
docker compose -f docker-compose.prod.yml up -d
```

## Grafana reset
```bash
ssh ubuntu@217.182.65.32
cd /opt/whatsapp-inbox/deploy
docker compose -f docker-compose.prod.yml exec grafana grafana-cli admin reset-admin-password "votre_nouveau_mot_de_passe"
```
