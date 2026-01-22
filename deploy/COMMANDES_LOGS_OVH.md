# Commandes pour Voir les Logs sur OVH

## 📍 Le projet est dans `/opt/whatsapp-inbox`

## 🚀 Commandes Rapides

### 1. Aller dans le projet

```bash
cd /opt/whatsapp-inbox/deploy
```

### 2. Voir les logs du backend

```bash
# Logs des 100 dernières lignes
docker compose -f docker-compose.prod.yml logs --tail=100 backend

# Logs en temps réel (suivre les nouveaux logs)
docker compose -f docker-compose.prod.yml logs -f backend

# Logs des dernières 10 minutes
docker compose -f docker-compose.prod.yml logs --since 10m backend

# Logs des dernières 24h
docker compose -f docker-compose.prod.yml logs --since 24h backend
```

### 3. Chercher spécifiquement les webhooks

```bash
# Chercher les webhooks dans les logs
docker compose -f docker-compose.prod.yml logs --tail=200 backend | grep -E "webhook|MESSAGE|message"

# Chercher les erreurs
docker compose -f docker-compose.prod.yml logs --tail=200 backend | grep -i "error\|critical\|❌"

# Chercher les messages traités
docker compose -f docker-compose.prod.yml logs --tail=200 backend | grep -E "💾|MESSAGE INSERT|Message processed"
```

### 4. Voir l'état des conteneurs

```bash
# Voir les conteneurs qui tournent
docker compose -f docker-compose.prod.yml ps

# Voir tous les conteneurs (y compris arrêtés)
docker compose -f docker-compose.prod.yml ps -a
```

### 5. Exporter les logs dans un fichier

```bash
# Logs complets
docker compose -f docker-compose.prod.yml logs backend > ~/backend_logs_$(date +%Y%m%d_%H%M%S).txt

# Logs des dernières 24h avec filtrage webhook
docker compose -f docker-compose.prod.yml logs --since 24h backend | grep -E "webhook|MESSAGE|message" > ~/webhook_logs_24h.txt
```

## 🎯 Commandes pour Diagnostiquer les Messages Manquants

### Vérifier que les webhooks arrivent

```bash
cd /opt/whatsapp-inbox/deploy
docker compose -f docker-compose.prod.yml logs --since 1h backend | grep "📥 Webhook received"
```

### Vérifier que les comptes sont trouvés

```bash
docker compose -f docker-compose.prod.yml logs --since 1h backend | grep -E "Account found|Cannot find account"
```

### Vérifier que les messages sont traités

```bash
docker compose -f docker-compose.prod.yml logs --since 1h backend | grep "💾 \[MESSAGE INSERT\]"
```

### Vérifier les erreurs

```bash
docker compose -f docker-compose.prod.yml logs --since 1h backend | grep -i "error\|❌\|critical"
```

## 📊 Surveiller en Temps Réel

### Terminal 1: Suivre les logs

```bash
cd /opt/whatsapp-inbox/deploy
docker compose -f docker-compose.prod.yml logs -f backend | grep -E "webhook|MESSAGE|message|error|❌|✅|💾"
```

### Terminal 2: Envoyer un message de test depuis WhatsApp

Puis observez dans Terminal 1 si:
- `📥 Webhook received` apparaît
- `💾 [MESSAGE INSERT]` apparaît
- `✅ Message processed successfully` apparaît
- Ou des erreurs `❌` apparaissent

## 🔄 Redémarrer le Backend

Si nécessaire:

```bash
cd /opt/whatsapp-inbox/deploy

# Redémarrer seulement le backend
docker compose -f docker-compose.prod.yml restart backend

# Reconstruire et redémarrer
docker compose -f docker-compose.prod.yml up -d --build backend

# Voir les logs après redémarrage
docker compose -f docker-compose.prod.yml logs -f backend
```

## 💡 Alias Utiles (Optionnel)

Ajoutez à `~/.bashrc` pour faciliter l'accès:

```bash
# Éditer le fichier
nano ~/.bashrc

# Ajouter ces lignes à la fin:
alias logs-backend='cd /opt/whatsapp-inbox/deploy && docker compose -f docker-compose.prod.yml logs -f backend'
alias logs-webhook='cd /opt/whatsapp-inbox/deploy && docker compose -f docker-compose.prod.yml logs --tail=100 backend | grep -E "webhook|MESSAGE|message"'

# Recharger
source ~/.bashrc
```

Ensuite vous pouvez simplement taper:
```bash
logs-backend
# ou
logs-webhook
```










