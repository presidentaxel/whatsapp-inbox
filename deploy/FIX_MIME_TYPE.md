# Fix MIME Type pour .mjs files

## 🔴 Problème
Les fichiers `.mjs` (comme `pdf.worker.min.mjs`) sont servis avec le MIME type `application/octet-stream` au lieu de `application/javascript`, ce qui cause des erreurs de chargement des modules ES.

## ✅ Solution Appliquée

### 1. Configuration Nginx (`frontend/nginx.conf`)
- Ajout de la directive `types` pour définir explicitement les MIME types
- Configuration spécifique pour `.mjs` et `.js` avec `default_type` et `add_header`
- Utilisation de `always` pour forcer les headers même si le fichier existe

### 2. Configuration Caddy (`deploy/Caddyfile`)
- Ajout de handlers spécifiques pour `.mjs` et `.js` AVANT le proxy vers nginx
- Force le `Content-Type` correct même si nginx ne le fait pas
- Préserve les autres headers de nginx

## 🚀 Commandes de Déploiement

### Étape 1 : Mettre à jour le code
```bash
cd ~/whatsapp-inbox
git pull origin main
```

### Étape 2 : Reconstruire le frontend
```bash
cd deploy
docker compose -f docker-compose.prod.yml up -d --build --no-cache --force-recreate frontend
```

### Étape 3 : Redémarrer Caddy
```bash
# Option A : Redémarrer complètement
docker compose -f docker-compose.prod.yml restart caddy

# Option B : Recharger la config sans redémarrer
docker compose -f docker-compose.prod.yml exec caddy caddy reload --config /etc/caddy/Caddyfile
```

### Étape 4 : Vérifier
```bash
# Vérifier que le frontend tourne
docker compose -f docker-compose.prod.yml ps frontend

# Voir les logs
docker compose -f docker-compose.prod.yml logs --tail=50 frontend

# Tester le MIME type depuis le serveur
curl -I http://localhost/pdf.worker.min.mjs
# OU depuis l'extérieur
curl -I https://whatsapp.lamaisonduchauffeurvtc.fr/pdf.worker.min.mjs

# Devrait retourner: Content-Type: application/javascript; charset=utf-8
```

## 🧪 Tests de Vérification

### Test 1 : Vérifier le MIME type depuis le conteneur nginx
```bash
docker compose -f docker-compose.prod.yml exec frontend wget -q -O- --server-response http://localhost/pdf.worker.min.mjs 2>&1 | grep -i "content-type"
```

### Test 2 : Vérifier le MIME type via Caddy
```bash
curl -I https://whatsapp.lamaisonduchauffeurvtc.fr/pdf.worker.min.mjs | grep -i "content-type"
```

### Test 3 : Vérifier que le fichier existe
```bash
docker compose -f docker-compose.prod.yml exec frontend ls -la /usr/share/nginx/html/pdf.worker.min.mjs
```

### Test 4 : Tester depuis le navigateur
1. Ouvrir la console du navigateur (F12)
2. Aller sur https://whatsapp.lamaisonduchauffeurvtc.fr
3. Vérifier qu'il n'y a plus d'erreurs MIME type
4. Tester l'affichage d'un PDF dans la galerie

## 🔍 Debug si ça ne fonctionne toujours pas

### Vérifier la configuration nginx dans le conteneur
```bash
docker compose -f docker-compose.prod.yml exec frontend cat /etc/nginx/conf.d/default.conf | grep -A 5 "\.mjs"
```

### Vérifier la configuration Caddy
```bash
docker compose -f docker-compose.prod.yml exec caddy cat /etc/caddy/Caddyfile | grep -A 5 "mjs"
```

### Vérifier les logs nginx
```bash
docker compose -f docker-compose.prod.yml logs frontend | grep -i "mime\|content-type"
```

### Vérifier les logs Caddy
```bash
docker compose -f docker-compose.prod.yml logs caddy | grep -i "pdf.worker"
```

### Tester directement nginx (sans Caddy)
```bash
# Depuis le serveur, tester directement le port du conteneur frontend
docker compose -f docker-compose.prod.yml exec frontend wget -q -O- --server-response http://localhost/pdf.worker.min.mjs 2>&1 | head -20
```

## 📝 Notes Importantes

1. **Cache du navigateur** : Vider le cache du navigateur (Ctrl+Shift+Delete) ou tester en navigation privée
2. **Cache Caddy** : Caddy peut mettre en cache les réponses, redémarrer complètement si nécessaire
3. **Ordre des handlers Caddy** : Les handlers spécifiques (`.mjs`, `.js`) doivent être AVANT le handler général
4. **Double vérification** : Les deux niveaux (nginx ET Caddy) sont configurés pour garantir le bon MIME type

## 🆘 Si Rien Ne Fonctionne

1. Vérifier que le fichier existe bien dans le build :
   ```bash
   docker compose -f docker-compose.prod.yml exec frontend ls -la /usr/share/nginx/html/ | grep pdf
   ```

2. Reconstruire complètement sans cache :
   ```bash
   docker compose -f docker-compose.prod.yml down frontend
   docker compose -f docker-compose.prod.yml build --no-cache frontend
   docker compose -f docker-compose.prod.yml up -d frontend
   docker compose -f docker-compose.prod.yml restart caddy
   ```

3. Vérifier que le fichier est bien dans `frontend/public/` :
   ```bash
   ls -la frontend/public/pdf.worker.min.mjs
   ```

