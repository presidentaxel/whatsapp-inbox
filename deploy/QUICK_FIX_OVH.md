# Fix Rapide - Webhooks OVH

## 🎯 Problème

Les webhooks n'arrivent pas en production sur votre serveur OVH.

## ✅ Solution Rapide

### 1. Vérifier que les conteneurs sont démarrés

```bash
cd deploy
docker compose -f docker-compose.prod.yml ps
```

Vous devriez voir `backend` et `caddy` avec le statut `Up`.

### 2. Vérifier que le backend répond

```bash
# Test depuis Caddy (vérifie la connectivité réseau Docker)
docker compose -f docker-compose.prod.yml exec caddy wget -q -O- http://backend:8000/healthz
```

Si ça ne fonctionne pas, le problème vient du réseau Docker ou du backend.

### 3. Vérifier les logs

```bash
# Logs backend
docker compose -f docker-compose.prod.yml logs --tail=20 backend

# Logs Caddy
docker compose -f docker-compose.prod.yml logs --tail=20 caddy | grep webhook
```

### 4. Redémarrer les services

```bash
cd deploy
docker compose -f docker-compose.prod.yml restart backend caddy
```

### 5. Tester l'endpoint

```bash
curl -X GET "https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=VOTRE_TOKEN&hub.challenge=test"
```

## 🔍 Diagnostic Complet

Exécutez le script de diagnostic :

```bash
cd deploy
chmod +x diagnose_ovh_webhook.sh
./diagnose_ovh_webhook.sh
```

Ce script va vérifier automatiquement tous les points critiques.

## 🐛 Problèmes Courants

### Le backend ne répond pas depuis Caddy

**Solution** :
1. Vérifier que le backend écoute sur `0.0.0.0:8000` (déjà configuré dans Dockerfile)
2. Vérifier que les deux conteneurs sont sur le même réseau :
   ```bash
   docker network inspect deploy_appnet
   ```
3. Redémarrer :
   ```bash
   docker compose -f docker-compose.prod.yml restart backend caddy
   ```

### Les ports 80/443 ne sont pas accessibles

**Solution** :
1. Vérifier le firewall OVH
2. Vérifier que Caddy écoute bien :
   ```bash
   docker compose -f docker-compose.prod.yml exec caddy netstat -tlnp | grep -E '80|443'
   ```

## 📋 Checklist

- [ ] Backend démarré : `docker compose -f docker-compose.prod.yml ps backend`
- [ ] Caddy démarré : `docker compose -f docker-compose.prod.yml ps caddy`
- [ ] Backend répond : `docker compose -f docker-compose.prod.yml exec backend curl http://localhost:8000/healthz`
- [ ] Caddy peut atteindre backend : `docker compose -f docker-compose.prod.yml exec caddy wget -q -O- http://backend:8000/healthz`
- [ ] Endpoint accessible : `curl https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp?...`

