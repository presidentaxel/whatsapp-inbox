# Accès Direct au Backend - Solution au problème d'interception

## 🔍 Problème

Le frontend (nginx) intercepte toutes les routes, même `/_diagnostics/`. C'est parce que le frontend et le backend sont deux services séparés sur Render, mais ils partagent le même domaine.

## ✅ Solution : Accéder directement à l'URL du backend

Le backend Render a sa propre URL. Vous devez utiliser cette URL directement, pas le domaine du frontend.

### Comment trouver l'URL du backend

1. **Via Render Dashboard :**
   - Allez sur https://dashboard.render.com
   - Cliquez sur le service `whatsapp-inbox-backend`
   - L'URL est affichée en haut, elle ressemble à :
     - `https://whatsapp-inbox-backend-xxxx.onrender.com`
     - ou une URL personnalisée si configurée

2. **Via les variables d'environnement du frontend :**
   - Dans Render Dashboard → `whatsapp-inbox-frontend` → Environment
   - Cherchez `VITE_BACKEND_URL`
   - Cette valeur est l'URL du backend

### Endpoints de diagnostic sur le backend direct

Une fois que vous avez l'URL du backend (ex: `https://whatsapp-inbox-backend-xxxx.onrender.com`), utilisez :

1. **Diagnostic complet :**
   ```
   https://whatsapp-inbox-backend-xxxx.onrender.com/_diagnostics/full
   ```

2. **État des webhooks :**
   ```
   https://whatsapp-inbox-backend-xxxx.onrender.com/_diagnostics/webhook-status
   ```

3. **Erreurs récentes :**
   ```
   https://whatsapp-inbox-backend-xxxx.onrender.com/_diagnostics/recent-errors
   ```

4. **Test webhook :**
   ```
   https://whatsapp-inbox-backend-xxxx.onrender.com/_diagnostics/test-webhook
   ```

5. **Connexion DB :**
   ```
   https://whatsapp-inbox-backend-xxxx.onrender.com/_diagnostics/database-connection
   ```

## 🔧 Alternative : Script pour trouver automatiquement l'URL

J'ai créé un script qui peut tester différentes URLs possibles :

```bash
cd backend
python scripts/auto_find_backend.py
```

Ce script teste automatiquement plusieurs URLs possibles et vous dit laquelle est le backend.

## 📝 Exemple d'utilisation

Une fois que vous avez l'URL du backend :

```bash
# Dans votre navigateur ou avec curl
curl https://whatsapp-inbox-backend-xxxx.onrender.com/_diagnostics/full

# Vous verrez le JSON avec toutes les informations
```

## ⚠️ Important

- Le frontend est sur : `whatsapp.lamaisonduchauffeurvtc.fr`
- Le backend est sur : `whatsapp-inbox-backend-xxxx.onrender.com` (URL différente)
- Pour les diagnostics, utilisez l'URL du backend directement
- Pour les appels API depuis le frontend, le frontend utilise `VITE_BACKEND_URL` automatiquement

## 🚀 Workflow recommandé

1. Trouvez l'URL du backend dans Render Dashboard
2. Utilisez cette URL pour accéder aux endpoints de diagnostic
3. Envoyez un webhook de test depuis Meta
4. Vérifiez immédiatement `/_diagnostics/recent-errors` sur l'URL du backend
5. Vous verrez les erreurs exactes sans avoir accès aux logs Render

