# Fix : Webhooks en Production

## 🔍 Problème Identifié

Le backend est déployé sur **Render** (via `render.yaml`), mais le `Caddyfile` pointe vers `backend:8000` qui est un service Docker local. En production, il n'y a pas de service Docker "backend" - le backend est sur Render.

## ✅ Solution

Il faut configurer Caddy pour pointer vers l'URL Render du backend au lieu de `backend:8000`.

### Option 1 : Utiliser une Variable d'Environnement (Recommandé)

1. **Récupérer l'URL Render du backend**
   - Allez sur https://dashboard.render.com
   - Ouvrez le service `whatsapp-inbox-backend`
   - Copiez l'URL (ex: `https://whatsapp-inbox-backend.onrender.com`)

2. **Ajouter la variable d'environnement BACKEND_URL**
   - Dans votre serveur où Caddy tourne, ajoutez dans le `.env` :
     ```bash
     BACKEND_URL=https://whatsapp-inbox-backend.onrender.com
     ```

3. **Utiliser le nouveau Caddyfile**
   - Remplacez `deploy/Caddyfile` par `deploy/Caddyfile.render`
   - Ou modifiez le Caddyfile existant pour utiliser `{$BACKEND_URL}`

### Option 2 : Modifier le Caddyfile Directement

Modifiez `deploy/Caddyfile` pour remplacer `backend:8000` par l'URL Render :

```caddy
# Avant
reverse_proxy backend:8000

# Après
reverse_proxy https://whatsapp-inbox-backend.onrender.com {
  header_up Host {upstream_hostport}
  header_up X-Forwarded-Proto {scheme}
}
```

## 📝 Modifications à Faire

### 1. Mettre à jour le Caddyfile

Le fichier `deploy/Caddyfile.render` est prêt à l'emploi. Il utilise la variable d'environnement `BACKEND_URL`.

### 2. Configurer la Variable d'Environnement

Sur votre serveur de production (où Caddy tourne) :

```bash
# Dans le fichier .env ou dans les variables d'environnement
BACKEND_URL=https://whatsapp-inbox-backend.onrender.com
```

### 3. Redémarrer Caddy

```bash
cd deploy
docker compose -f docker-compose.prod.yml restart caddy
# Ou
docker compose -f docker-compose.prod.yml exec caddy caddy reload --config /etc/caddy/Caddyfile
```

## 🧪 Test

1. **Tester l'endpoint webhook directement sur Render** :
   ```bash
   curl -X GET "https://whatsapp-inbox-backend.onrender.com/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=VOTRE_TOKEN&hub.challenge=test"
   ```
   Devrait retourner `test`

2. **Tester via le domaine personnalisé** :
   ```bash
   curl -X GET "https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=VOTRE_TOKEN&hub.challenge=test"
   ```
   Devrait aussi retourner `test`

3. **Tester avec un webhook simulé** :
   ```bash
   curl -X POST https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp \
     -H "Content-Type: application/json" \
     -d '{"object":"whatsapp_business_account","entry":[]}'
   ```
   Devrait retourner `{"status":"received"}`

## 🔧 Si Vous Utilisez Docker Compose en Production

Si vous déployez avec `docker-compose.prod.yml`, modifiez-le pour ajouter la variable :

```yaml
caddy:
  image: caddy:2
  environment:
    - DOMAIN=${DOMAIN}
    - EMAIL=${EMAIL}
    - BACKEND_URL=${BACKEND_URL}  # Ajoutez cette ligne
  volumes:
    - ./Caddyfile.render:/etc/caddy/Caddyfile  # Utilisez le nouveau fichier
```

## ⚠️ Notes Importantes

1. **L'URL Render peut changer** si vous recréez le service
2. **Vérifiez les logs Render** pour voir si les webhooks arrivent
3. **Vérifiez les logs Caddy** pour voir les requêtes proxy
4. **Le backend Render doit être accessible publiquement** (pas de firewall)

## 🐛 Debug

Si ça ne fonctionne toujours pas :

1. Vérifiez que le backend Render répond :
   ```bash
   curl https://whatsapp-inbox-backend.onrender.com/healthz
   ```

2. Vérifiez les logs Caddy :
   ```bash
   docker compose -f docker-compose.prod.yml logs caddy
   ```

3. Vérifiez les logs Render :
   - Allez sur https://dashboard.render.com
   - Ouvrez le service backend
   - Regardez les logs

4. Testez directement l'URL Render dans Meta :
   - Configurez temporairement le webhook avec l'URL Render directe
   - Si ça fonctionne, le problème vient de Caddy
   - Si ça ne fonctionne pas, le problème vient du backend Render

