# Configuration Google Drive OAuth2 via SSH

## 🔐 Étape 1 : Se connecter au serveur

```bash
ssh user@votre-serveur-ovh.com
# Remplacez user et votre-serveur-ovh.com par vos identifiants
```

## 📍 Étape 2 : Trouver le projet

```bash
# Chercher le dossier whatsapp-inbox
find ~ -type d -name "whatsapp-inbox" 2>/dev/null

# Ou chercher le dossier deploy
find ~ -type d -name "deploy" 2>/dev/null

# Voir ce qu'il y a dans le répertoire home
ls -la ~

# Chercher dans les emplacements courants
ls -la ~/projects 2>/dev/null
ls -la /opt 2>/dev/null
ls -la /var/www 2>/dev/null
```

## 📂 Étape 3 : Aller dans le projet

```bash
# Une fois que vous avez trouvé le projet, allez dedans
cd ~/whatsapp-inbox
# Ou le chemin où vous l'avez trouvé

# Vérifier que vous êtes au bon endroit
pwd
ls -la
```

## ✏️ Étape 4 : Éditer le fichier .env du backend

```bash
# Aller dans le dossier backend
cd backend

# Vérifier si le fichier .env existe
ls -la .env

# Éditer le fichier .env (utilisez nano, vi, ou vim selon vos préférences)
nano .env
# OU
vi .env
# OU
vim .env
```

## 🔑 Étape 5 : Ajouter les variables Google Drive

Dans le fichier `.env`, ajoutez ces lignes (remplacez par vos vraies valeurs) :

```bash
# Google Drive OAuth2 Configuration
GOOGLE_DRIVE_CLIENT_ID=votre_client_id_google.apps.googleusercontent.com
GOOGLE_DRIVE_CLIENT_SECRET=votre_client_secret_google
GOOGLE_DRIVE_REDIRECT_URI=https://votre-domaine.com/api/auth/google-drive/callback
```

**Exemple concret :**
```bash
GOOGLE_DRIVE_CLIENT_ID=123456789-abcdefghijklmnop.apps.googleusercontent.com
GOOGLE_DRIVE_CLIENT_SECRET=GOCSPX-abcdefghijklmnopqrstuvwxyz
GOOGLE_DRIVE_REDIRECT_URI=https://whatsapp.lamaisonduchauffeurvtc.fr/api/auth/google-drive/callback
```

**Pour sauvegarder dans nano :**
- Appuyez sur `Ctrl + O` pour sauvegarder
- Appuyez sur `Enter` pour confirmer
- Appuyez sur `Ctrl + X` pour quitter

**Pour sauvegarder dans vi/vim :**
- Appuyez sur `Esc` pour être sûr d'être en mode commande
- Tapez `:wq` puis `Enter` pour sauvegarder et quitter
- Ou `:q!` pour quitter sans sauvegarder

## 🔄 Étape 6 : Redémarrer le service backend

```bash
# Retourner dans le dossier deploy
cd ../deploy

# Vérifier que docker-compose.prod.yml existe
ls -la docker-compose.prod.yml

# Redémarrer seulement le backend (recharge les variables d'environnement)
docker compose -f docker-compose.prod.yml restart backend

# OU reconstruire et redémarrer si nécessaire
docker compose -f docker-compose.prod.yml up -d --build backend
```

## ✅ Étape 7 : Vérifier que ça fonctionne

```bash
# Voir les logs du backend pour vérifier qu'il n'y a plus l'erreur
docker compose -f docker-compose.prod.yml logs -f backend | grep -i "google"

# Ou voir tous les logs récents
docker compose -f docker-compose.prod.yml logs --tail=50 backend
```

Vous devriez voir que l'erreur `❌ Google Drive OAuth2 not configured` a disparu.

## 🚀 Alternative : Ajouter directement via echo (si vous préférez)

Si vous préférez ajouter les variables sans éditeur :

```bash
# Aller dans le dossier backend
cd ~/whatsapp-inbox/backend

# Ajouter les variables à la fin du fichier .env
echo "" >> .env
echo "# Google Drive OAuth2 Configuration" >> .env
echo "GOOGLE_DRIVE_CLIENT_ID=votre_client_id_google.apps.googleusercontent.com" >> .env
echo "GOOGLE_DRIVE_CLIENT_SECRET=votre_client_secret_google" >> .env
echo "GOOGLE_DRIVE_REDIRECT_URI=https://votre-domaine.com/api/auth/google-drive/callback" >> .env

# Vérifier que c'est bien ajouté
tail -5 .env

# Redémarrer le backend
cd ../deploy
docker compose -f docker-compose.prod.yml restart backend
```

## 📋 Checklist rapide

```bash
# 1. Où suis-je ?
pwd

# 2. Le fichier .env existe-t-il ?
ls -la backend/.env

# 3. Les variables sont-elles présentes ?
grep GOOGLE_DRIVE backend/.env

# 4. Le backend est-il redémarré ?
docker compose -f docker-compose.prod.yml ps backend

# 5. Plus d'erreur Google Drive ?
docker compose -f docker-compose.prod.yml logs --tail=20 backend | grep -i "google"
```

## ⚠️ Notes importantes

1. **Si vous n'avez pas encore créé les credentials Google OAuth2 :**
   - Allez sur [Google Cloud Console](https://console.cloud.google.com/)
   - Créez un projet ou sélectionnez-en un
   - Activez l'API Google Drive
   - Créez des identifiants OAuth 2.0
   - Ajoutez l'URI de redirection autorisée : `https://votre-domaine.com/api/auth/google-drive/callback`

2. **Si vous ne voulez pas utiliser Google Drive :**
   - Vous pouvez laisser les variables vides ou les commenter avec `#`
   - L'application fonctionnera sans Google Drive, mais cette fonctionnalité sera désactivée

3. **Sécurité :**
   - Ne partagez jamais vos `CLIENT_SECRET` publiquement
   - Vérifiez que le fichier `.env` n'est pas dans votre dépôt Git (il devrait être dans `.gitignore`)

## 🔍 Si vous ne trouvez pas le projet

```bash
# Chercher les conteneurs Docker directement
docker ps -a | grep backend

# Voir les volumes Docker pour trouver où sont les fichiers
docker volume ls

# Chercher les fichiers .env
find ~ -name ".env" -type f 2>/dev/null | grep -i whatsapp
```

