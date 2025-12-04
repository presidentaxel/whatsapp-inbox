# Commandes de Diagnostic Complet - Serveur OVH

## 🔍 Problème Identifié

Vous avez **DEUX sets de conteneurs** :
- **Anciens** (10 jours) : `whatsapp-inbox-backend-1`, `whatsapp-inbox-frontend-1` - ports exposés
- **Nouveaux** (57 min) : `deploy-backend-1`, `deploy-frontend-1` - dans réseau Docker

Caddy essaie probablement d'atteindre `backend:8000` mais ne trouve pas le bon conteneur.

## 📋 Commandes à Exécuter

### 1. Vérifier les Réseaux Docker

```bash
# Voir tous les réseaux
docker network ls

# Voir sur quels réseaux sont les conteneurs
docker inspect deploy-backend-1 --format '{{range $net, $conf := .NetworkSettings.Networks}}{{$net}} ({{$conf.IPAddress}}){{"\n"}}{{end}}'
docker inspect deploy-caddy-1 --format '{{range $net, $conf := .NetworkSettings.Networks}}{{$net}} ({{$conf.IPAddress}}){{"\n"}}{{end}}'
```

### 2. Tester la Connectivité

```bash
# Test 1: Depuis Caddy vers backend:8000
docker exec deploy-caddy-1 wget -q -O- --timeout=3 http://backend:8000/healthz

# Test 2: Depuis Caddy vers deploy-backend-1:8000
docker exec deploy-caddy-1 wget -q -O- --timeout=3 http://deploy-backend-1:8000/healthz

# Test 3: Depuis Caddy vers l'IP directe
BACKEND_IP=$(docker inspect deploy-backend-1 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
echo "IP du backend: $BACKEND_IP"
docker exec deploy-caddy-1 wget -q -O- --timeout=3 "http://$BACKEND_IP:8000/healthz"
```

### 3. Vérifier la Configuration Caddy

```bash
# Voir le Caddyfile
docker exec deploy-caddy-1 cat /etc/caddy/Caddyfile

# Vérifier les logs Caddy
docker logs --tail=50 deploy-caddy-1 | grep -i webhook
```

### 4. Vérifier les Logs Backend

```bash
# Logs backend
docker logs --tail=50 deploy-backend-1

# Chercher les erreurs
docker logs deploy-backend-1 2>&1 | grep -i error

# Vérifier que le backend écoute bien
docker logs deploy-backend-1 2>&1 | grep -i "uvicorn running"
```

### 5. Tester le Backend Directement

```bash
# Test depuis l'hôte (le port 8000 est exposé sur whatsapp-inbox-backend-1)
curl http://localhost:8000/healthz

# Ou depuis un autre conteneur
docker exec deploy-caddy-1 wget -q -O- http://localhost:8000/healthz
```

## 🔧 Solutions Possibles

### Solution 1 : Vérifier le Nom du Service dans docker-compose

Le problème peut venir du fait que dans `docker-compose.prod.yml`, le service s'appelle `backend` mais Docker l'a nommé `deploy-backend-1`.

**Vérifiez** :
```bash
# Trouver le fichier docker-compose
find ~ -name "docker-compose.prod.yml" 2>/dev/null

# Voir la configuration
cat /chemin/vers/docker-compose.prod.yml | grep -A 10 "backend:"
```

### Solution 2 : Utiliser le Nom Complet du Conteneur

Si le nom `backend` ne résout pas, modifiez le Caddyfile pour utiliser `deploy-backend-1:8000` :

```bash
# Trouver le Caddyfile
find ~ -name "Caddyfile" 2>/dev/null

# Voir la configuration actuelle
cat /chemin/vers/Caddyfile | grep -A 5 "webhook"
```

### Solution 3 : Redémarrer les Conteneurs

Parfois, la résolution DNS Docker a besoin d'un redémarrage :

```bash
# Trouver où est le docker-compose
cd /chemin/vers/deploy

# Redémarrer
docker compose -f docker-compose.prod.yml restart backend caddy

# Ou reconstruire
docker compose -f docker-compose.prod.yml up -d --force-recreate backend caddy
```

### Solution 4 : Arrêter les Anciens Conteneurs

Les anciens conteneurs peuvent créer de la confusion :

```bash
# Voir quels conteneurs utilisent le port 8000
docker ps --format "table {{.Names}}\t{{.Ports}}" | grep 8000

# Arrêter les anciens (si vous êtes sûr qu'ils ne sont plus utilisés)
docker stop whatsapp-inbox-backend-1 whatsapp-inbox-frontend-1
```

## 🎯 Diagnostic Rapide - Copiez-Collez

Exécutez ce bloc de commandes :

```bash
echo "=== RÉSEAUX ==="
docker network ls
echo ""
echo "=== RÉSEAU DU BACKEND ==="
docker inspect deploy-backend-1 --format '{{range $net, $conf := .NetworkSettings.Networks}}{{$net}} (IP: {{$conf.IPAddress}}){{"\n"}}{{end}}'
echo ""
echo "=== RÉSEAU DE CADDY ==="
docker inspect deploy-caddy-1 --format '{{range $net, $conf := .NetworkSettings.Networks}}{{$net}} (IP: {{$conf.IPAddress}}){{"\n"}}{{end}}'
echo ""
echo "=== TEST CONNECTIVITÉ ==="
docker exec deploy-caddy-1 wget -q -O- --timeout=3 http://backend:8000/healthz 2>&1 && echo "✅ OK" || echo "❌ ÉCHEC"
echo ""
echo "=== CONFIGURATION CADDY ==="
docker exec deploy-caddy-1 cat /etc/caddy/Caddyfile | grep -A 3 "webhook"
echo ""
echo "=== LOGS BACKEND (Uvicorn) ==="
docker logs deploy-backend-1 2>&1 | grep -i "uvicorn running" | tail -1
```

## 📝 Informations à Me Donner

Après avoir exécuté les commandes ci-dessus, donnez-moi :

1. **Les réseaux** : Sur quels réseaux sont `deploy-backend-1` et `deploy-caddy-1` ?
2. **Le test de connectivité** : Est-ce que `wget http://backend:8000/healthz` depuis Caddy fonctionne ?
3. **Le Caddyfile** : Quelle URL est utilisée pour le webhook ?
4. **Les logs** : Y a-t-il des erreurs dans les logs Caddy ou backend ?

Avec ces informations, je pourrai corriger le problème précisément !

