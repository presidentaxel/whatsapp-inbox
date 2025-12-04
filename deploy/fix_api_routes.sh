#!/bin/bash
# Script pour trouver le projet, diagnostiquer et corriger les routes API

set -e

echo "=== DIAGNOSTIC ET CORRECTION DES ROUTES API ==="
echo ""

# 1. Trouver le projet
echo "=== 1. TROUVER LE PROJET ==="
PROJECT_DIR=$(find ~ /opt /home /var/www -type d -name "whatsapp-inbox" 2>/dev/null | head -1)

if [ -z "$PROJECT_DIR" ]; then
    # Chercher via docker-compose
    COMPOSE_FILE=$(find / -name "docker-compose.prod.yml" 2>/dev/null | head -1)
    if [ -n "$COMPOSE_FILE" ]; then
        PROJECT_DIR=$(dirname "$COMPOSE_FILE")
        echo "✅ Projet trouvé via docker-compose: $PROJECT_DIR"
    else
        echo "❌ Projet non trouvé"
        echo "Conteneurs actifs:"
        docker ps --format "table {{.Names}}\t{{.Image}}"
        exit 1
    fi
else
    echo "✅ Projet trouvé: $PROJECT_DIR"
fi

cd "$PROJECT_DIR/deploy" 2>/dev/null || cd "$PROJECT_DIR"
echo "📁 Répertoire: $(pwd)"
echo ""

# 2. Vérifier les conteneurs
echo "=== 2. CONTENEURS ==="
BACKEND_CONTAINER=$(docker ps --format "{{.Names}}" | grep -E "backend|whatsapp.*backend" | head -1)
CADDY_CONTAINER=$(docker ps --format "{{.Names}}" | grep -E "caddy" | head -1)

if [ -z "$BACKEND_CONTAINER" ]; then
    echo "❌ Conteneur backend non trouvé"
    exit 1
fi
if [ -z "$CADDY_CONTAINER" ]; then
    echo "❌ Conteneur Caddy non trouvé"
    exit 1
fi

echo "✅ Backend: $BACKEND_CONTAINER"
echo "✅ Caddy: $CADDY_CONTAINER"
echo ""

# 3. Vérifier BACKEND_URL
echo "=== 3. CONFIGURATION BACKEND_URL ==="
ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
    ENV_FILE="../.env"
fi

if [ -f "$ENV_FILE" ]; then
    BACKEND_URL=$(grep "^BACKEND_URL=" "$ENV_FILE" | cut -d= -f2 || echo "")
    if [ -z "$BACKEND_URL" ]; then
        echo "⚠️  BACKEND_URL non défini dans $ENV_FILE"
        echo "   Ajout de BACKEND_URL=backend:8000"
        echo "BACKEND_URL=backend:8000" >> "$ENV_FILE"
        BACKEND_URL="backend:8000"
    else
        echo "✅ BACKEND_URL=$BACKEND_URL"
    fi
else
    echo "⚠️  Fichier .env non trouvé, création..."
    echo "BACKEND_URL=backend:8000" > "$ENV_FILE"
    BACKEND_URL="backend:8000"
fi

# Vérifier dans docker-compose
if [ -f "docker-compose.prod.yml" ]; then
    if ! grep -q "BACKEND_URL" docker-compose.prod.yml; then
        echo "⚠️  BACKEND_URL manquant dans docker-compose.prod.yml"
    fi
fi
echo ""

# 4. Tester la connectivité
echo "=== 4. TEST CONNECTIVITÉ ==="
echo "Test Caddy → Backend:"
docker exec "$CADDY_CONTAINER" wget -q -O- --timeout=3 http://backend:8000/health 2>&1 | head -1 || echo "❌ Échec"
echo ""

# 5. Tester les routes API
echo "=== 5. TEST ROUTES API ==="
echo "Test /api/accounts (devrait devenir /accounts):"
RESPONSE=$(docker exec "$CADDY_CONTAINER" wget -q -O- --timeout=3 "http://backend:8000/accounts" 2>&1 | head -1)
if echo "$RESPONSE" | grep -q "error\|503\|502"; then
    echo "❌ Erreur: $RESPONSE"
else
    echo "✅ Backend répond: $(echo "$RESPONSE" | head -c 100)..."
fi
echo ""

# 6. Vérifier le Caddyfile
echo "=== 6. VÉRIFICATION CADDYFILE ==="
if [ -f "Caddyfile" ]; then
    if grep -q "uri strip_prefix /api" Caddyfile; then
        echo "✅ Caddyfile utilise strip_prefix /api (correct)"
    else
        echo "⚠️  Caddyfile ne strip pas /api"
    fi
    
    if grep -q "{\$BACKEND_URL:backend:8000}" Caddyfile; then
        echo "✅ Caddyfile utilise BACKEND_URL avec fallback backend:8000"
    else
        echo "⚠️  Caddyfile n'utilise pas BACKEND_URL correctement"
    fi
else
    echo "❌ Caddyfile non trouvé"
fi
echo ""

# 7. Redémarrer Caddy si nécessaire
echo "=== 7. REDÉMARRAGE ==="
if [ -f "$ENV_FILE" ] && grep -q "BACKEND_URL" "$ENV_FILE"; then
    echo "Redémarrage de Caddy pour appliquer les changements..."
    docker compose -f docker-compose.prod.yml restart caddy 2>/dev/null || \
    docker restart "$CADDY_CONTAINER" 2>/dev/null || \
    echo "⚠️  Impossible de redémarrer Caddy automatiquement"
    echo "   Redémarrez manuellement: docker restart $CADDY_CONTAINER"
    echo ""
    echo "Attente de 3 secondes..."
    sleep 3
fi

# 8. Test final
echo "=== 8. TEST FINAL ==="
echo "Test depuis l'extérieur (simulé):"
docker exec "$CADDY_CONTAINER" wget -q -O- --timeout=3 "http://localhost/api/accounts" 2>&1 | head -3 || echo "❌ Échec"
echo ""

echo "=== RÉSUMÉ ==="
echo "✅ Projet: $PROJECT_DIR"
echo "✅ BACKEND_URL: $BACKEND_URL"
echo ""
echo "Si les erreurs 503 persistent:"
echo "1. Vérifiez que le backend est démarré: docker ps | grep backend"
echo "2. Vérifiez les logs: docker logs $BACKEND_CONTAINER | tail -20"
echo "3. Vérifiez les logs Caddy: docker logs $CADDY_CONTAINER | tail -20"
echo "4. Testez directement: docker exec $CADDY_CONTAINER wget -O- http://backend:8000/accounts"

