# Configuration Production - Webhooks

## 🎯 Problème Résolu

Le backend est déployé sur **Render**, mais Caddy pointait vers un service Docker local `backend:8000` qui n'existe pas en production.

## ✅ Solution Appliquée

Le `Caddyfile` a été modifié pour utiliser une variable d'environnement `BACKEND_URL` qui pointe vers l'URL Render du backend.

## 📋 Étapes de Configuration

### 1. Récupérer l'URL Render du Backend

1. Allez sur https://dashboard.render.com
2. Ouvrez le service `whatsapp-inbox-backend`
3. Copiez l'URL (ex: `https://whatsapp-inbox-backend.onrender.com`)

### 2. Configurer la Variable d'Environnement

Sur votre serveur de production (où Caddy tourne), ajoutez dans le fichier `.env` du dossier `deploy/` :

```bash
BACKEND_URL=https://whatsapp-inbox-backend.onrender.com
```

**Important** : Remplacez par votre vraie URL Render !

### 3. Redémarrer Caddy

```bash
cd deploy
docker compose -f docker-compose.prod.yml restart caddy
```

Ou si vous préférez recharger la config sans redémarrer :

```bash
docker compose -f docker-compose.prod.yml exec caddy caddy reload --config /etc/caddy/Caddyfile
```

## 🧪 Vérification

### Test 1 : Vérifier que le backend Render répond

```bash
curl https://whatsapp-inbox-backend.onrender.com/healthz
```

Devrait retourner `{"status":"ok"}`

### Test 2 : Vérifier le webhook via le domaine personnalisé

```bash
curl -X GET "https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=VOTRE_TOKEN&hub.challenge=test"
```

Devrait retourner `test`

### Test 3 : Tester avec un webhook simulé

```bash
curl -X POST https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{"object":"whatsapp_business_account","entry":[]}'
```

Devrait retourner `{"status":"received"}`

## 🔍 Debug

### Vérifier les Logs Caddy

```bash
docker compose -f docker-compose.prod.yml logs caddy
```

Cherchez les lignes avec `/webhook/whatsapp` pour voir si les requêtes arrivent.

### Vérifier les Logs Render

1. Allez sur https://dashboard.render.com
2. Ouvrez le service `whatsapp-inbox-backend`
3. Onglet "Logs"
4. Cherchez les lignes avec `POST /webhook/whatsapp`

### Si ça ne fonctionne toujours pas

1. **Testez directement l'URL Render dans Meta** :
   - Configurez temporairement le webhook avec `https://whatsapp-inbox-backend.onrender.com/webhook/whatsapp`
   - Si ça fonctionne → Le problème vient de Caddy
   - Si ça ne fonctionne pas → Le problème vient du backend Render

2. **Vérifiez que BACKEND_URL est bien définie** :
   ```bash
   docker compose -f docker-compose.prod.yml exec caddy env | grep BACKEND_URL
   ```

3. **Vérifiez la configuration Caddy** :
   ```bash
   docker compose -f docker-compose.prod.yml exec caddy caddy validate --config /etc/caddy/Caddyfile
   ```

## 📝 Notes

- Le `Caddyfile` utilise maintenant `{$BACKEND_URL:backend:8000}` qui signifie :
  - Si `BACKEND_URL` est définie → Utilise cette URL
  - Sinon → Utilise `backend:8000` (pour le développement local)

- En production, vous DEVEZ définir `BACKEND_URL` avec l'URL Render

- L'URL Render peut changer si vous recréez le service, mettez à jour `BACKEND_URL` dans ce cas

