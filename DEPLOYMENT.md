# 🚀 Déploiement Automatique avec GitHub

Ce projet est configuré pour se déployer automatiquement sur votre serveur OVH à chaque `git push`.

## 📋 Configuration Initiale (UNE SEULE FOIS)

### Option 1 : GitHub Actions (Recommandé)

1. **Créer les secrets GitHub** :
   - Allez dans votre repo GitHub → Settings → Secrets and variables → Actions
   - Ajoutez ces secrets :
     - `OVH_HOST` : L'IP ou le domaine de votre serveur OVH
     - `OVH_USERNAME` : `ubuntu` (ou votre utilisateur)
     - `OVH_SSH_KEY` : Votre clé SSH privée (contenu complet de `~/.ssh/id_rsa` ou équivalent)
     - `OVH_SSH_PORT` : `22` (optionnel, par défaut 22)

2. **Générer une clé SSH** (si vous n'en avez pas) :
   ```bash
   ssh-keygen -t rsa -b 4096 -C "github-actions"
   # Copiez la clé privée dans OVH_SSH_KEY
   # Ajoutez la clé publique sur le serveur OVH :
   cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
   ```

3. **C'est tout !** 🎉
   - À chaque `git push` vers `main` ou `master`, le déploiement se fera automatiquement
   - Vous pouvez suivre le déploiement dans l'onglet "Actions" de GitHub

### Option 2 : Webhook GitHub (Alternative)

Si vous préférez ne pas utiliser GitHub Actions :

1. **Sur le serveur OVH**, exécutez une seule fois :
   ```bash
   # Trouvez votre projet
   find ~ /opt /home /var/www -name "docker-compose.prod.yml"
   cd /chemin/trouve/deploy
   
   # Copiez le script de déploiement
   cp webhook_deploy.sh /usr/local/bin/github-deploy.sh
   chmod +x /usr/local/bin/github-deploy.sh
   ```

2. **Dans GitHub** :
   - Settings → Webhooks → Add webhook
   - Payload URL : `https://votre-domaine.com/webhook/github` (nécessite un serveur web configuré)
   - Content type : `application/json`
   - Events : `Just the push event`

## 🔄 Workflow de Déploiement

1. **Vous faites des modifications** dans votre code
2. **Vous faites `git push`** :
   ```bash
   git add .
   git commit -m "Vos modifications"
   git push origin main
   ```
3. **Le déploiement se déclenche automatiquement** :
   - Pull du code depuis GitHub
   - Rebuild des images Docker (backend + frontend)
   - Redémarrage des services
   - Vérification de la santé

## 📊 Vérifier le Déploiement

### Dans GitHub
- Onglet **Actions** → Voir les logs en temps réel

### Sur le Serveur
```bash
# Voir les logs de déploiement
tail -f /tmp/github_deploy.log

# Vérifier les conteneurs
docker ps

# Voir les logs backend
docker logs deploy-backend-1 --tail=50

# Vérifier la santé
curl https://votre-domaine.com/health
```

## 🐛 Dépannage

### Le déploiement échoue

1. **Vérifiez les secrets GitHub** :
   - `OVH_HOST` est correct ?
   - `OVH_SSH_KEY` est la clé privée complète ?
   - La clé publique est dans `~/.ssh/authorized_keys` sur le serveur ?

2. **Vérifiez la connexion SSH** :
   ```bash
   ssh -i ~/.ssh/id_rsa ubuntu@VOTRE_IP
   ```

3. **Vérifiez les logs GitHub Actions** :
   - Onglet Actions → Cliquez sur le workflow en échec → Voir les logs

### Le déploiement réussit mais l'app ne fonctionne pas

1. **Vérifiez les logs backend** :
   ```bash
   docker logs deploy-backend-1 --tail=100
   ```

2. **Vérifiez la configuration** :
   ```bash
   cd deploy
   cat .env  # Vérifiez BACKEND_URL, DOMAIN, etc.
   ```

3. **Redémarrez manuellement** :
   ```bash
   cd deploy
   docker compose -f docker-compose.prod.yml restart backend frontend caddy
   ```

## 🔧 Modifier le Comportement de Déploiement

Le fichier `.github/workflows/deploy.yml` contrôle le déploiement. Vous pouvez :

- **Changer la branche** : Modifiez `branches: - main`
- **Restreindre les fichiers** : Décommentez la section `paths:`
- **Modifier les étapes** : Ajoutez/supprimez des commandes dans `script:`

## 📝 Notes

- Le déploiement prend environ 2-5 minutes
- Les images sont rebuild à chaque fois (pour garantir la fraîcheur)
- Les services sont redémarrés avec `--force-recreate` pour appliquer tous les changements
- Le health check attend jusqu'à 60 secondes pour que le backend soit prêt

## ✅ Checklist de Déploiement

- [ ] Secrets GitHub configurés
- [ ] Clé SSH ajoutée au serveur
- [ ] Test de connexion SSH réussi
- [ ] Premier push testé
- [ ] Déploiement réussi dans GitHub Actions
- [ ] Application accessible en production

