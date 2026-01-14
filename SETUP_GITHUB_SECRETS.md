# 🔐 Configuration des Secrets GitHub pour le Déploiement

L'erreur `ssh: unable to authenticate` indique que les secrets GitHub ne sont pas configurés ou que la clé SSH est incorrecte.

## 📋 Secrets Requis

Vous devez configurer ces secrets dans GitHub :

1. **OVH_HOST** : L'IP ou le domaine de votre serveur OVH
2. **OVH_USERNAME** : Votre nom d'utilisateur SSH (généralement `ubuntu`)
3. **OVH_SSH_KEY** : Votre clé SSH privée complète
4. **OVH_SSH_PORT** : Le port SSH (optionnel, par défaut 22)

## 🔧 Configuration Étape par Étape

### 1. Générer une Clé SSH (si vous n'en avez pas)

```bash
# Sur votre machine locale
ssh-keygen -t rsa -b 4096 -C "github-actions-deploy"
# Appuyez sur Entrée pour accepter l'emplacement par défaut
# Entrez un mot de passe (ou laissez vide)
```

### 2. Copier la Clé Publique sur le Serveur OVH

```bash
# Option 1 : Utiliser ssh-copy-id
ssh-copy-id -i ~/.ssh/id_rsa.pub ubuntu@VOTRE_IP_OVH

# Option 2 : Manuellement
cat ~/.ssh/id_rsa.pub | ssh ubuntu@VOTRE_IP_OVH "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

### 3. Tester la Connexion SSH

```bash
# Testez que vous pouvez vous connecter
ssh -i ~/.ssh/id_rsa ubuntu@VOTRE_IP_OVH
```

Si ça fonctionne, vous pouvez continuer.

### 4. Configurer les Secrets dans GitHub

1. Allez dans votre repo GitHub
2. **Settings** → **Secrets and variables** → **Actions**
3. Cliquez sur **New repository secret**
4. Ajoutez chaque secret :

#### Secret 1 : OVH_HOST
- **Name** : `OVH_HOST`
- **Value** : L'IP de votre serveur (ex: `123.45.67.89`) ou le domaine

#### Secret 2 : OVH_USERNAME
- **Name** : `OVH_USERNAME`
- **Value** : `ubuntu` (ou votre utilisateur)

#### Secret 3 : OVH_SSH_KEY
- **Name** : `OVH_SSH_KEY`
- **Value** : Le contenu COMPLET de votre clé privée :
  ```bash
  cat ~/.ssh/id_rsa
  ```
  Copiez TOUT le contenu, y compris :
  ```
  -----BEGIN OPENSSH PRIVATE KEY-----
  ...
  -----END OPENSSH PRIVATE KEY-----
  ```

#### Secret 4 : OVH_SSH_PORT (Optionnel)
- **Name** : `OVH_SSH_PORT`
- **Value** : `22` (ou votre port SSH si différent)

## 🔐 Secrets Google Drive (Optionnel - requis pour l'intégration Google Drive)

Si vous utilisez l'intégration Google Drive, vous devez également configurer ces secrets :

### 1. Obtenir les identifiants Google OAuth2

1. Allez sur [Google Cloud Console](https://console.cloud.google.com)
2. Créez un projet ou sélectionnez un projet existant
3. Activez l'API Google Drive
4. Créez des identifiants OAuth 2.0 :
   - Type : **Application Web**
   - URI de redirection autorisés : `https://votre-domaine.com/api/auth/google-drive/callback`
5. Récupérez le **Client ID** et le **Client Secret**

### 2. Configurer les Secrets dans GitHub

1. Allez dans votre repo GitHub
2. **Settings** → **Secrets and variables** → **Actions**
3. Cliquez sur **New repository secret**
4. Ajoutez chaque secret :

#### Secret 1 : GOOGLE_DRIVE_CLIENT_ID
- **Name** : `GOOGLE_DRIVE_CLIENT_ID`
- **Value** : Votre Client ID Google (ex: `580123451962-xxxxx.apps.googleusercontent.com`)

#### Secret 2 : GOOGLE_DRIVE_CLIENT_SECRET
- **Name** : `GOOGLE_DRIVE_CLIENT_SECRET`
- **Value** : Votre Client Secret Google (visible uniquement à la création)

#### Secret 3 : GOOGLE_DRIVE_REDIRECT_URI
- **Name** : `GOOGLE_DRIVE_REDIRECT_URI`
- **Value** : `https://votre-domaine.com/api/auth/google-drive/callback`
  - Remplacez `votre-domaine.com` par votre vrai domaine (ex: `whatsapp.lamaisonduchauffeurvtc.fr`)

### 3. Comment ça fonctionne

Le workflow GitHub Actions configure automatiquement ces variables dans le fichier `backend/.env` sur votre serveur lors de chaque déploiement. Vous n'avez pas besoin de les configurer manuellement sur le serveur.

### 5. Vérifier la Configuration

Après avoir ajouté les secrets, le workflow de déploiement devrait fonctionner.

## 🔍 Dépannage

### Erreur : "unable to authenticate"

**Causes possibles :**
1. La clé SSH n'est pas dans `authorized_keys` sur le serveur
2. La clé privée dans GitHub est incorrecte (copie incomplète)
3. Les permissions de la clé sont incorrectes

**Solution :**
```bash
# Sur le serveur OVH
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys

# Vérifier que la clé publique est bien là
cat ~/.ssh/authorized_keys
```

### Erreur : "Host key verification failed"

**Solution :**
Le workflow vérifie automatiquement la clé d'hôte. Si ça échoue, vous pouvez désactiver la vérification (non recommandé pour la sécurité).

### Erreur : "Connection refused"

**Causes possibles :**
1. Le port SSH est incorrect
2. Le firewall bloque le port
3. Le serveur n'est pas accessible

**Solution :**
```bash
# Vérifier que le serveur est accessible
ping VOTRE_IP_OVH

# Vérifier que le port SSH est ouvert
telnet VOTRE_IP_OVH 22
```

## ✅ Vérification Finale

Une fois les secrets configurés :

1. Faites un `git push`
2. Allez dans **Actions** → **Deploy to OVH Server**
3. Vérifiez que l'étape "Check SSH secrets" passe
4. Vérifiez que le déploiement se connecte correctement

## 🔒 Sécurité

- ⚠️ **Ne partagez JAMAIS votre clé privée**
- ⚠️ **Ne commitez JAMAIS votre clé privée dans Git**
- ✅ Utilisez des secrets GitHub pour stocker les clés
- ✅ Régénérez les clés régulièrement
- ✅ Utilisez des clés différentes pour différents environnements

## 📝 Notes

- La clé SSH doit être au format OpenSSH (pas PuTTY)
- Si vous utilisez une clé existante, assurez-vous qu'elle fonctionne manuellement avant de l'ajouter à GitHub
- Le workflow vérifie automatiquement que tous les secrets sont présents avant de tenter la connexion

