# Guide: Voir les Logs sur OVH

## 🚀 Méthode 1: Via SSH (Recommandé)

### Étape 1: Se connecter au serveur OVH

```bash
ssh votre_utilisateur@votre_ip_ovh
# ou
ssh votre_utilisateur@votre_domaine
```

### Étape 2: Trouver le projet

```bash
# Chercher le dossier du projet
find ~ -type d -name "whatsapp-inbox" 2>/dev/null
# ou
find ~ -type d -name "deploy" 2>/dev/null

# Aller dans le projet
cd ~/whatsapp-inbox/deploy
# (ou le chemin trouvé)
```

### Étape 3: Voir les logs Docker

```bash
# Logs du backend (les 100 dernières lignes)
docker compose -f docker-compose.prod.yml logs --tail=100 backend

# Logs en temps réel (suivre les nouveaux logs)
docker compose -f docker-compose.prod.yml logs -f backend

# Chercher spécifiquement les webhooks
docker compose -f docker-compose.prod.yml logs --tail=200 backend | grep -E "webhook|MESSAGE|message"

# Logs des dernières 5 minutes
docker compose -f docker-compose.prod.yml logs --since 5m backend

# Tous les logs (attention, peut être long)
docker compose -f docker-compose.prod.yml logs backend > backend_logs.txt
```

### Étape 4: Chercher les erreurs spécifiques

```bash
# Chercher les erreurs critiques
docker compose -f docker-compose.prod.yml logs backend | grep -i "critical\|error\|❌"

# Chercher les webhooks reçus
docker compose -f docker-compose.prod.yml logs backend | grep "📥 Webhook received"

# Chercher les messages traités
docker compose -f docker-compose.prod.yml logs backend | grep "💾 \[MESSAGE INSERT\]"

# Chercher les problèmes de compte
docker compose -f docker-compose.prod.yml logs backend | grep "Cannot find account"
```

## 🌐 Méthode 2: Via l'API (Sans SSH)

### Utiliser l'endpoint de diagnostic

Ouvrez dans votre navigateur ou avec curl:

```bash
# Voir l'état des webhooks et messages récents
curl https://whatsapp.lamaisonduchauffeurvtc.fr/api/diagnostics/webhook-status

# Voir les erreurs récentes
curl https://whatsapp.lamaisonduchauffeurvtc.fr/api/diagnostics/recent-errors

# Diagnostic complet
curl https://whatsapp.lamaisonduchauffeurvtc.fr/api/diagnostics/comprehensive
```

Ces endpoints retournent des informations sur:
- Les messages récents (entrants et sortants)
- L'état des comptes WhatsApp
- Les erreurs récentes
- Les webhooks reçus

## 📊 Méthode 3: Logs via l'Interface Web (Si disponible)

Si vous avez accès à un panneau de contrôle (Portainer, Docker Desktop, etc.):

1. Connectez-vous à l'interface
2. Allez dans "Containers"
3. Sélectionnez le conteneur `backend`
4. Cliquez sur "Logs"

## 🔍 Commandes Utiles pour le Diagnostic

### Voir l'état des conteneurs

```bash
docker compose -f docker-compose.prod.yml ps
```

### Voir les logs des 10 dernières minutes

```bash
docker compose -f docker-compose.prod.yml logs --since 10m backend
```

### Exporter les logs dans un fichier

```bash
# Logs complets
docker compose -f docker-compose.prod.yml logs backend > backend_logs_$(date +%Y%m%d_%H%M%S).txt

# Logs des dernières 24h
docker compose -f docker-compose.prod.yml logs --since 24h backend > backend_logs_24h.txt

# Logs avec filtrage webhook
docker compose -f docker-compose.prod.yml logs --since 24h backend | grep -E "webhook|MESSAGE|message" > webhook_logs.txt
```

### Voir les logs en temps réel pendant un test

```bash
# Terminal 1: Suivre les logs
docker compose -f docker-compose.prod.yml logs -f backend | grep -E "webhook|MESSAGE|message|error|❌|✅"

# Terminal 2: Envoyer un message de test depuis WhatsApp
# (ou utiliser un autre terminal pour tester)
```

## 🎯 Checklist pour Diagnostiquer les Messages Manquants

1. **Vérifier que les webhooks arrivent:**
   ```bash
   docker compose -f docker-compose.prod.yml logs --since 1h backend | grep "📥 Webhook received"
   ```

2. **Vérifier que les comptes sont trouvés:**
   ```bash
   docker compose -f docker-compose.prod.yml logs --since 1h backend | grep -E "Account found|Cannot find account"
   ```

3. **Vérifier que les messages sont traités:**
   ```bash
   docker compose -f docker-compose.prod.yml logs --since 1h backend | grep "💾 \[MESSAGE INSERT\]"
   ```

4. **Vérifier les erreurs:**
   ```bash
   docker compose -f docker-compose.prod.yml logs --since 1h backend | grep -i "error\|❌\|critical"
   ```

## 💡 Astuce: Créer un Alias

Pour faciliter l'accès aux logs, créez un alias dans votre `~/.bashrc`:

```bash
# Ajouter à ~/.bashrc
alias logs-backend='cd ~/whatsapp-inbox/deploy && docker compose -f docker-compose.prod.yml logs -f backend'
alias logs-webhook='cd ~/whatsapp-inbox/deploy && docker compose -f docker-compose.prod.yml logs --tail=100 backend | grep -E "webhook|MESSAGE|message"'
```

Puis rechargez:
```bash
source ~/.bashrc
```

Maintenant vous pouvez simplement taper:
```bash
logs-backend
# ou
logs-webhook
```

## 🆘 Si Vous N'Arrivez Pas à Vous Connecter en SSH

1. **Vérifiez vos identifiants SSH** dans le panneau OVH
2. **Utilisez l'API de diagnostic** (Méthode 2 ci-dessus)
3. **Contactez le support OVH** pour réinitialiser l'accès SSH
4. **Utilisez l'interface web OVH** si disponible (KVM, VNC, etc.)

