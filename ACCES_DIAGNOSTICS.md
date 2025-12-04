# Accès aux Diagnostics - Solution Complète

## ✅ Solution : Routes ajoutées dans Caddy

J'ai ajouté des routes dans le Caddyfile pour que les endpoints de diagnostic soient routés directement vers le backend, sans passer par le frontend.

## 📍 Endpoints disponibles

**Après déploiement**, vous pourrez accéder à :

### 1. Diagnostic complet
```
https://whatsapp.lamaisonduchauffeurvtc.fr/_diagnostics/full
```

### 2. État des webhooks
```
https://whatsapp.lamaisonduchauffeurvtc.fr/_diagnostics/webhook-status
```

### 3. Erreurs récentes
```
https://whatsapp.lamaisonduchauffeurvtc.fr/_diagnostics/recent-errors
```

### 4. Test webhook
```
https://whatsapp.lamaisonduchauffeurvtc.fr/_diagnostics/test-webhook
```

### 5. Connexion DB
```
https://whatsapp.lamaisonduchauffeurvtc.fr/_diagnostics/database-connection
```

## 🚀 Déploiement

### Option 1 : Script de déploiement automatique

```bash
# Sur votre serveur
./deploy/deploy.sh
```

### Option 2 : Déploiement manuel

```bash
# 1. Sur votre serveur, aller dans le dossier deploy
cd deploy

# 2. Rebuild et redémarrer les services
docker compose -f docker-compose.prod.yml up -d --build

# 3. Recharger la configuration Caddy
docker compose -f docker-compose.prod.yml exec caddy caddy reload --config /etc/caddy/Caddyfile

# Ou redémarrer Caddy si le reload échoue
docker compose -f docker-compose.prod.yml restart caddy
```

### Option 3 : Via SSH si vous avez accès

```bash
# Se connecter au serveur
ssh user@votre-serveur

# Aller dans le repo
cd /chemin/vers/whatsapp-inbox

# Pull les dernières modifications
git pull

# Déployer
./deploy/deploy.sh
```

## 📊 Utilisation

### Voir l'état des webhooks

Ouvrez dans votre navigateur ou avec curl :
```
https://whatsapp.lamaisonduchauffeurvtc.fr/_diagnostics/webhook-status
```

Vous verrez :
- Nombre de messages entrants/sortants
- Messages des dernières 24h
- Comptes configurés
- Derniers messages reçus

### Voir les erreurs après un test

1. Envoyez un webhook de test depuis Meta
2. Immédiatement après, ouvrez :
   ```
   https://whatsapp.lamaisonduchauffeurvtc.fr/_diagnostics/recent-errors
   ```
3. Vous verrez l'erreur exacte avec tous les détails

### Diagnostic complet

```
https://whatsapp.lamaisonduchauffeurvtc.fr/_diagnostics/full
```

Retourne tout : messages, comptes, DB, erreurs.

## 🔍 Alternative : Logs Docker directement

Si vous avez accès SSH au serveur, vous pouvez aussi voir les logs directement :

```bash
# Voir les logs du backend
docker compose -f deploy/docker-compose.prod.yml logs backend

# Voir les logs en temps réel (suivre)
docker compose -f deploy/docker-compose.prod.yml logs -f backend

# Filtrer les logs de webhook
docker compose -f deploy/docker-compose.prod.yml logs backend | grep "📥\|❌\|✅"

# Voir les dernières 100 lignes
docker compose -f deploy/docker-compose.prod.yml logs --tail=100 backend
```

## 📝 Routes ajoutées dans Caddy

Les routes suivantes sont maintenant routées directement vers le backend :
- `/_diagnostics/*` - Endpoints de diagnostic
- `/health*` et `/healthz` - Health checks
- `/metrics` - Métriques Prometheus
- `/webhook/*` - Webhooks WhatsApp (déjà existant)
- `/api/*` - API REST (déjà existant)

## ⚠️ Important

- Les erreurs sont stockées en mémoire (perdues au redémarrage)
- Seulement les 100 dernières erreurs sont conservées
- Après chaque redéploiement, les erreurs en mémoire sont perdues

## 🎯 Workflow recommandé

1. **Push les modifications** (code + Caddyfile)
2. **Déployer sur le serveur** (via script ou manuellement)
3. **Tester les endpoints** : `/_diagnostics/full`
4. **Envoyer un webhook de test** depuis Meta
5. **Vérifier immédiatement** : `/_diagnostics/recent-errors`
6. **Voir l'erreur exacte** et corriger le problème

Cela vous permettra de voir exactement pourquoi les webhooks ne stockent pas les messages !
