# Trouver le Projet sur le Serveur OVH

## 🔍 Étape 1: Chercher le Projet

Exécutez ces commandes dans l'ordre:

```bash
# 1. Chercher dans tout le système (peut prendre du temps)
sudo find / -type d -name "whatsapp-inbox" 2>/dev/null

# 2. Chercher dans les emplacements courants
ls -la /opt/ 2>/dev/null | grep -i whatsapp
ls -la /var/www/ 2>/dev/null | grep -i whatsapp
ls -la /home/ 2>/dev/null | grep -i whatsapp

# 3. Chercher les conteneurs Docker directement
docker ps -a | grep -i whatsapp
docker ps -a | grep -i backend

# 4. Voir tous les conteneurs Docker
docker ps -a

# 5. Chercher les volumes Docker
docker volume ls

# 6. Chercher dans le répertoire courant et parent
ls -la ~/
ls -la /home/ubuntu/
```

## 📍 Étape 2: Si le Projet est Trouvé

Une fois que vous avez trouvé le chemin (par exemple `/opt/whatsapp-inbox`):

```bash
# Aller dans le projet
cd /chemin/trouvé/whatsapp-inbox

# Vérifier la structure
ls -la

# Aller dans deploy
cd deploy
ls -la
```

## 🐳 Étape 3: Si le Projet est dans Docker

Si vous trouvez des conteneurs Docker mais pas le code source:

```bash
# Voir les conteneurs
docker ps -a

# Voir les logs d'un conteneur backend
docker logs $(docker ps -q -f name=backend) --tail=100

# Ou si vous connaissez le nom exact
docker logs backend --tail=100
docker logs whatsapp-backend --tail=100
```

## 🔧 Étape 4: Chercher par les Fichiers Docker Compose

```bash
# Chercher les fichiers docker-compose
sudo find / -name "docker-compose*.yml" 2>/dev/null
sudo find / -name "docker-compose*.yaml" 2>/dev/null

# Chercher les fichiers Caddyfile
sudo find / -name "Caddyfile*" 2>/dev/null
```

## 📂 Étape 5: Vérifier les Services Systemd

```bash
# Voir les services systemd
systemctl list-units --type=service | grep -i whatsapp
systemctl list-units --type=service | grep -i docker

# Voir les services actifs
systemctl list-units --type=service --state=running | grep -i whatsapp
```

## 🎯 Étape 6: Commandes Rapides pour Voir les Logs

Même sans trouver le projet, vous pouvez voir les logs:

```bash
# Voir tous les conteneurs
docker ps -a

# Voir les logs du conteneur backend (remplacez le nom si différent)
docker logs $(docker ps -q -f name=backend) --tail=100 -f

# Ou essayer ces noms communs
docker logs backend --tail=100 2>/dev/null
docker logs whatsapp-backend --tail=100 2>/dev/null
docker logs app-backend --tail=100 2>/dev/null

# Chercher les webhooks dans tous les logs
docker logs $(docker ps -q) 2>/dev/null | grep -i webhook | tail -50
```

## 💡 Astuce: Lister Tous les Conteneurs

```bash
# Voir tous les conteneurs avec leurs noms
docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"

# Voir les conteneurs qui tournent
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
```

Une fois que vous avez trouvé le nom du conteneur backend, vous pouvez voir ses logs directement!

