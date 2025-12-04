# Commandes à Exécuter sur le Serveur OVH

## 🔍 Étape 1 : Trouver le Projet

Exécutez ces commandes pour trouver où se trouve votre projet :

```bash
# Chercher le dossier whatsapp-inbox
find ~ -type d -name "whatsapp-inbox" 2>/dev/null

# Ou chercher le dossier deploy
find ~ -type d -name "deploy" 2>/dev/null

# Voir ce qu'il y a dans le répertoire home
ls -la ~

# Chercher dans les emplacements courants
ls -la ~/projects 2>/dev/null
ls -la ~/apps 2>/dev/null
ls -la /opt 2>/dev/null
ls -la /var/www 2>/dev/null
```

## 📍 Étape 2 : Aller dans le Projet

Une fois que vous avez trouvé le projet, allez dedans :

```bash
# Exemple si trouvé dans ~/whatsapp-inbox
cd ~/whatsapp-inbox

# Ou si trouvé ailleurs
cd /chemin/vers/whatsapp-inbox
```

## 🔧 Étape 3 : Vérifier la Structure

```bash
# Vérifier que vous êtes au bon endroit
pwd

# Voir la structure
ls -la

# Vérifier que le dossier deploy existe
ls -la deploy/
```

## 🚀 Étape 4 : Mettre à Jour depuis GitHub

Si vous venez de pousser les changements :

```bash
# Mettre à jour le code
git pull origin main

# Ou si vous êtes sur une autre branche
git pull
```

## 🧪 Étape 5 : Diagnostic Rapide

### Option A : Si le script existe déjà

```bash
cd deploy
chmod +x diagnose_ovh_webhook.sh
./diagnose_ovh_webhook.sh
```

### Option B : Diagnostic Manuel

```bash
cd deploy

# 1. Vérifier les conteneurs
docker compose -f docker-compose.prod.yml ps

# 2. Vérifier que le backend répond
docker compose -f docker-compose.prod.yml exec backend curl http://localhost:8000/healthz

# 3. Vérifier que Caddy peut atteindre le backend (CRITIQUE!)
docker compose -f docker-compose.prod.yml exec caddy wget -q -O- http://backend:8000/healthz

# 4. Voir les logs
docker compose -f docker-compose.prod.yml logs --tail=30 backend | grep -E "webhook|POST|Uvicorn"
docker compose -f docker-compose.prod.yml logs --tail=30 caddy | grep webhook

# 5. Tester l'endpoint webhook
curl -X GET "https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=VOTRE_TOKEN&hub.challenge=test"
```

## 🔄 Étape 6 : Redémarrer les Services

Si nécessaire :

```bash
cd deploy

# Redémarrer tout
docker compose -f docker-compose.prod.yml restart

# Ou seulement backend et caddy
docker compose -f docker-compose.prod.yml restart backend caddy

# Reconstruire si nécessaire
docker compose -f docker-compose.prod.yml up -d --build
```

## 📋 Checklist Rapide

Exécutez ces commandes dans l'ordre et notez les résultats :

```bash
# 1. Où suis-je ?
pwd

# 2. Y a-t-il un dossier deploy ?
ls -la | grep deploy

# 3. Les conteneurs sont-ils démarrés ?
docker ps

# 4. Le backend répond-il ?
docker ps | grep backend
docker exec $(docker ps -q -f name=backend) curl http://localhost:8000/healthz

# 5. Caddy peut-il atteindre le backend ?
docker exec $(docker ps -q -f name=caddy) wget -q -O- http://backend:8000/healthz 2>&1
```

## 💡 Si Vous Ne Trouvez Pas le Projet

Le projet pourrait être :
- Dans un autre répertoire utilisateur
- Dans `/opt/` ou `/var/www/`
- Nommé différemment
- Déployé via un autre mécanisme (systemd, PM2, etc.)

Cherchez les conteneurs Docker directement :

```bash
# Voir tous les conteneurs Docker
docker ps -a

# Voir les images
docker images | grep whatsapp

# Voir les volumes
docker volume ls
```

