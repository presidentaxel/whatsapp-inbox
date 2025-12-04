#!/bin/bash
# Script de déploiement déclenché par webhook GitHub
# À placer sur le serveur OVH et configurer comme webhook dans GitHub

set -e

LOG_FILE="/tmp/github_deploy.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo "Déploiement déclenché: $(date)"
echo "=========================================="

# Trouver le projet
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
echo "📁 Répertoire: $(pwd)"

# Pull les dernières modifications
echo "📥 Pull depuis GitHub..."
git fetch origin
git reset --hard origin/main || git reset --hard origin/master

# Aller dans deploy
cd deploy 2>/dev/null || cd .

# S'assurer que BACKEND_URL est défini
if [ -f .env ]; then
    if ! grep -q "^BACKEND_URL=" .env; then
        echo "BACKEND_URL=backend:8000" >> .env
    fi
else
    echo "BACKEND_URL=backend:8000" > .env
fi

# Rebuild et redémarrer
echo "🔨 Rebuild des images..."
docker compose -f docker-compose.prod.yml build --no-cache backend frontend || true

echo "🔄 Redémarrage des services..."
docker compose -f docker-compose.prod.yml up -d --force-recreate

# Attendre que les services soient prêts
echo "⏳ Attente du démarrage..."
sleep 10

# Vérifier la santé
echo "🏥 Vérification de la santé..."
for i in {1..30}; do
    if docker compose -f docker-compose.prod.yml exec -T backend curl -f http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Backend est prêt"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "⚠️  Backend n'est pas prêt après 30 tentatives"
    fi
    sleep 2
done

echo "✅ Déploiement terminé: $(date)"
echo "=========================================="

