#!/bin/bash
# Script pour configurer le déploiement automatique sur le serveur OVH
# À exécuter UNE SEULE FOIS sur le serveur pour configurer le webhook GitHub

set -e

echo "=== CONFIGURATION DÉPLOIEMENT AUTOMATIQUE ==="
echo ""

# 1. Trouver le projet
PROJECT_DIR=$(find ~ /opt /home /var/www -type d -name "whatsapp-inbox" 2>/dev/null | head -1)
if [ -z "$PROJECT_DIR" ]; then
    COMPOSE_FILE=$(find / -name "docker-compose.prod.yml" 2>/dev/null | head -1)
    if [ -n "$COMPOSE_FILE" ]; then
        PROJECT_DIR=$(dirname "$COMPOSE_FILE")
    else
        echo "❌ Projet non trouvé"
        exit 1
    fi
fi

cd "$PROJECT_DIR"
echo "✅ Projet trouvé: $PROJECT_DIR"
echo ""

# 2. Créer le script webhook
echo "=== 1. CRÉATION DU SCRIPT WEBHOOK ==="
cat > /usr/local/bin/github-deploy.sh << 'EOF'
#!/bin/bash
# Script de déploiement déclenché par webhook GitHub

set -e

LOG_FILE="/tmp/github_deploy.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo "Déploiement déclenché: $(date)"
echo "=========================================="

PROJECT_DIR=$(find ~ /opt /home /var/www -type d -name "whatsapp-inbox" 2>/dev/null | head -1)
if [ -z "$PROJECT_DIR" ]; then
    COMPOSE_FILE=$(find / -name "docker-compose.prod.yml" 2>/dev/null | head -1)
    if [ -n "$COMPOSE_FILE" ]; then
        PROJECT_DIR=$(dirname "$COMPOSE_FILE")
    else
        echo "❌ Projet non trouvé"
        exit 1
    fi
fi

cd "$PROJECT_DIR"
git fetch origin
git reset --hard origin/main || git reset --hard origin/master

cd deploy 2>/dev/null || cd .

if [ -f .env ]; then
    if ! grep -q "^BACKEND_URL=" .env; then
        echo "BACKEND_URL=backend:8000" >> .env
    fi
else
    echo "BACKEND_URL=backend:8000" > .env
fi

docker compose -f docker-compose.prod.yml build --no-cache backend frontend || true
docker compose -f docker-compose.prod.yml up -d --force-recreate

sleep 10

for i in {1..30}; do
    if docker compose -f docker-compose.prod.yml exec -T backend curl -f http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Backend est prêt"
        break
    fi
    sleep 2
done

echo "✅ Déploiement terminé: $(date)"
EOF

chmod +x /usr/local/bin/github-deploy.sh
echo "✅ Script créé: /usr/local/bin/github-deploy.sh"
echo ""

# 3. Créer un endpoint webhook simple (optionnel, nécessite un serveur web)
echo "=== 2. CONFIGURATION WEBHOOK (OPTION 1: GitHub Actions) ==="
echo ""
echo "Pour utiliser GitHub Actions, configurez ces secrets dans GitHub:"
echo "  - OVH_HOST: votre IP ou domaine du serveur"
echo "  - OVH_USERNAME: ubuntu (ou votre user)"
echo "  - OVH_SSH_KEY: votre clé SSH privée"
echo "  - OVH_SSH_PORT: 22 (optionnel)"
echo ""
echo "Le workflow .github/workflows/deploy.yml se déclenchera automatiquement"
echo "sur chaque push vers main/master."
echo ""

# 4. Option 2: Webhook HTTP (nécessite un serveur web)
echo "=== 3. CONFIGURATION WEBHOOK (OPTION 2: Webhook HTTP) ==="
echo ""
echo "Si vous préférez un webhook HTTP, vous pouvez:"
echo "1. Installer un serveur web simple (nginx, Caddy, etc.)"
echo "2. Créer un endpoint qui appelle /usr/local/bin/github-deploy.sh"
echo "3. Configurer le webhook dans GitHub Settings → Webhooks"
echo ""
echo "Exemple avec Caddy (ajoutez dans votre Caddyfile):"
echo ""
cat << 'CADDY_EXAMPLE'
# Webhook GitHub
@github_webhook {
    path /webhook/github
    method POST
}
handle @github_webhook {
    reverse_proxy unix//run/github-webhook.sock
}
CADDY_EXAMPLE

echo ""
echo "=== 4. TEST MANUEL ==="
echo ""
echo "Pour tester le déploiement manuellement:"
echo "  /usr/local/bin/github-deploy.sh"
echo ""
echo "Pour voir les logs:"
echo "  tail -f /tmp/github_deploy.log"
echo ""

echo "✅ Configuration terminée!"

