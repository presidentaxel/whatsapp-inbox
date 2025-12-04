# 🔧 Fix Rapide : Erreurs 503 et Webhook Meta

## Problème
- Erreurs 503 sur `/api/auth/me` et `/api/accounts`
- Webhook Meta ne peut pas être validé

## Solution Rapide (via GitHub)

1. **Pushez les corrections** :
   ```bash
   git add .
   git commit -m "Fix: Configuration BACKEND_URL et Caddyfile"
   git push origin main
   ```

2. **Sur le serveur OVH** (une seule fois via SSH) :
   ```bash
   # Trouvez le projet
   find ~ /opt /home /var/www -name "docker-compose.prod.yml"
   cd /chemin/trouve/deploy
   
   # Exécutez le script de diagnostic
   chmod +x fix_all_issues.sh
   ./fix_all_issues.sh
   ```

## Solution Manuelle (si GitHub Actions pas encore configuré)

### 1. Vérifier BACKEND_URL

```bash
cd deploy
# Vérifiez que BACKEND_URL existe dans .env
grep BACKEND_URL .env || echo "BACKEND_URL=backend:8000" >> .env
```

### 2. Redémarrer Caddy

```bash
docker compose -f docker-compose.prod.yml restart caddy
```

### 3. Vérifier la connectivité

```bash
# Test depuis Caddy vers backend
docker exec deploy-caddy-1 wget -q -O- http://backend:8000/health

# Si ça échoue, vérifiez le réseau
docker network ls
docker network inspect deploy_appnet  # ou le nom de votre réseau
```

### 4. Tester le webhook

```bash
# Récupérer le token
docker exec deploy-backend-1 python -c "
import os
from dotenv import load_dotenv
load_dotenv('/app/.env')
print(os.getenv('WHATSAPP_VERIFY_TOKEN', ''))
"

# Tester depuis l'extérieur (remplacez TOKEN)
curl "https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=TOKEN&hub.challenge=test123"
```

## Configuration Meta

1. **URL** : `https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp`
2. **Token** : Le token affiché par la commande ci-dessus (doit correspondre EXACTEMENT)
3. **Champs** : `messages` et `message_status`

## Vérification

Après correction, testez :
- Frontend : `https://whatsapp.lamaisonduchauffeurvtc.fr` (plus d'erreurs 503)
- Webhook Meta : Validation réussie dans Meta Developers Console

