# Diagnostic Webhook - Serveur OVH

## 🔍 Problème Potentiel

Sur un serveur OVH avec Docker Compose, le problème peut venir de plusieurs sources :

1. **Le backend n'est pas démarré** ou n'écoute pas correctement
2. **Caddy ne peut pas atteindre le backend** (problème de réseau Docker)
3. **Le backend écoute seulement sur localhost** au lieu de 0.0.0.0
4. **Les ports ne sont pas correctement exposés**

## 🧪 Diagnostic Automatique

Exécutez le script de diagnostic :

```bash
cd deploy
./diagnose_ovh_webhook.sh
```

Ce script va vérifier :
- ✅ L'état des conteneurs Docker
- ✅ Si le backend répond
- ✅ Si Caddy peut atteindre le backend
- ✅ La configuration du réseau Docker
- ✅ L'accessibilité externe de l'endpoint webhook

## 🔧 Vérifications Manuelles

### 1. Vérifier que les conteneurs sont démarrés

```bash
cd deploy
docker compose -f docker-compose.prod.yml ps
```

Vous devriez voir :
- `backend` : Status `Up`
- `caddy` : Status `Up`
- `frontend` : Status `Up` (optionnel)

### 2. Vérifier que le backend répond

```bash
# Depuis l'hôte
docker compose -f docker-compose.prod.yml exec backend curl http://localhost:8000/healthz

# Depuis Caddy (test de connectivité réseau)
docker compose -f docker-compose.prod.yml exec caddy wget -q -O- http://backend:8000/healthz
```

### 3. Vérifier les logs

```bash
# Logs backend
docker compose -f docker-compose.prod.yml logs --tail=50 backend

# Logs Caddy
docker compose -f docker-compose.prod.yml logs --tail=50 caddy

# Chercher les requêtes webhook
docker compose -f docker-compose.prod.yml logs | grep webhook
```

### 4. Vérifier la configuration Caddy

```bash
docker compose -f docker-compose.prod.yml exec caddy cat /etc/caddy/Caddyfile
```

Vérifiez que les routes `/webhook*` pointent bien vers `backend:8000`.

### 5. Tester l'endpoint webhook

```bash
# Depuis l'hôte (si le port est exposé)
curl -X GET "http://localhost:PORT/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=VOTRE_TOKEN&hub.challenge=test"

# Depuis l'extérieur
curl -X GET "https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=VOTRE_TOKEN&hub.challenge=test"
```

## 🐛 Problèmes Courants et Solutions

### Problème 1 : Backend non accessible depuis Caddy

**Symptôme** : Caddy ne peut pas atteindre `backend:8000`

**Solutions** :
1. Vérifier que les deux conteneurs sont sur le même réseau :
   ```bash
   docker network inspect deploy_appnet
   ```

2. Vérifier que le backend écoute sur `0.0.0.0:8000` et pas seulement `localhost:8000` :
   - Dans `backend/Dockerfile`, la commande doit être : `uvicorn app.main:app --host 0.0.0.0 --port 8000`
   - Vérifier dans les logs : `INFO:     Uvicorn running on http://0.0.0.0:8000`

3. Redémarrer les conteneurs :
   ```bash
   docker compose -f docker-compose.prod.yml restart backend caddy
   ```

### Problème 2 : Backend non démarré

**Symptôme** : Le conteneur backend n'existe pas ou est arrêté

**Solution** :
```bash
cd deploy
docker compose -f docker-compose.prod.yml up -d backend
docker compose -f docker-compose.prod.yml logs backend
```

### Problème 3 : Caddy ne démarre pas

**Symptôme** : Le conteneur Caddy est arrêté ou en erreur

**Solution** :
```bash
cd deploy
docker compose -f docker-compose.prod.yml logs caddy
docker compose -f docker-compose.prod.yml restart caddy
```

### Problème 4 : Ports non accessibles

**Symptôme** : L'endpoint webhook n'est pas accessible depuis l'extérieur

**Solutions** :
1. Vérifier que les ports 80 et 443 sont ouverts dans le firewall OVH
2. Vérifier que Caddy écoute bien sur ces ports :
   ```bash
   docker compose -f docker-compose.prod.yml exec caddy netstat -tlnp | grep -E '80|443'
   ```

3. Vérifier les règles de firewall :
   ```bash
   sudo ufw status
   # ou
   sudo iptables -L -n
   ```

## 📋 Checklist de Vérification

- [ ] Les conteneurs `backend` et `caddy` sont démarrés
- [ ] Le backend répond sur `http://localhost:8000/healthz` depuis le conteneur
- [ ] Caddy peut atteindre le backend sur `http://backend:8000/healthz`
- [ ] Les deux conteneurs sont sur le même réseau Docker
- [ ] Le backend écoute sur `0.0.0.0:8000` (pas seulement localhost)
- [ ] La configuration Caddy est valide
- [ ] Les ports 80 et 443 sont ouverts dans le firewall
- [ ] L'endpoint webhook est accessible depuis l'extérieur
- [ ] Les logs montrent des requêtes POST vers `/webhook/whatsapp`

## 🚀 Commandes de Redémarrage

Si vous avez fait des modifications :

```bash
cd deploy

# Reconstruire et redémarrer
docker compose -f docker-compose.prod.yml up -d --build

# Ou redémarrer seulement
docker compose -f docker-compose.prod.yml restart backend caddy

# Recharger la config Caddy sans redémarrer
docker compose -f docker-compose.prod.yml exec caddy caddy reload --config /etc/caddy/Caddyfile
```

## 📞 Support

Si le problème persiste après ces vérifications, collectez ces informations :

1. Sortie du script de diagnostic : `./diagnose_ovh_webhook.sh > diagnostic.txt`
2. Logs backend : `docker compose -f docker-compose.prod.yml logs backend > backend_logs.txt`
3. Logs Caddy : `docker compose -f docker-compose.prod.yml logs caddy > caddy_logs.txt`
4. Configuration Caddy : `docker compose -f docker-compose.prod.yml exec caddy cat /etc/caddy/Caddyfile > caddyfile.txt`

