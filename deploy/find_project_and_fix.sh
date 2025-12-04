#!/bin/bash
# Script pour trouver le projet et diagnostiquer les problèmes

set -e

echo "=== 1. TROUVER LE PROJET ==="
PROJECT_DIR=$(find ~ -type d -name "whatsapp-inbox" 2>/dev/null | head -1)
if [ -z "$PROJECT_DIR" ]; then
    echo "❌ Projet non trouvé dans ~"
    echo "Recherche dans /opt, /home, /var/www..."
    PROJECT_DIR=$(find /opt /home /var/www -type d -name "whatsapp-inbox" 2>/dev/null | head -1)
fi

if [ -z "$PROJECT_DIR" ]; then
    echo "❌ Projet non trouvé"
    echo ""
    echo "Conteneurs Docker actifs:"
    docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
    echo ""
    echo "Cherchez le répertoire avec docker-compose.prod.yml:"
    find / -name "docker-compose.prod.yml" 2>/dev/null | head -5
    exit 1
fi

echo "✅ Projet trouvé: $PROJECT_DIR"
cd "$PROJECT_DIR/deploy" || cd "$PROJECT_DIR"
echo "📁 Répertoire actuel: $(pwd)"
echo ""

echo "=== 2. VÉRIFIER LES CONTENEURS ==="
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "NAME|backend|caddy|frontend" || echo "Aucun conteneur trouvé"
echo ""

echo "=== 3. VÉRIFIER BACKEND_URL ==="
if [ -f "docker-compose.prod.yml" ]; then
    echo "Backend URL dans docker-compose:"
    grep -A 5 "BACKEND_URL" docker-compose.prod.yml || echo "BACKEND_URL non trouvé"
fi

if [ -f ".env" ]; then
    echo ""
    echo "Backend URL dans .env:"
    grep "BACKEND_URL" .env || echo "BACKEND_URL non trouvé dans .env"
fi
echo ""

echo "=== 4. TESTER CONNECTIVITÉ BACKEND ==="
if docker ps | grep -q "backend"; then
    BACKEND_CONTAINER=$(docker ps | grep "backend" | awk '{print $1}' | head -1)
    echo "Test depuis Caddy vers backend:"
    if docker ps | grep -q "caddy"; then
        CADDY_CONTAINER=$(docker ps | grep "caddy" | awk '{print $1}' | head -1)
        docker exec "$CADDY_CONTAINER" wget -q -O- --timeout=3 http://backend:8000/health 2>&1 | head -3 || echo "❌ Impossible de joindre backend"
    fi
else
    echo "❌ Conteneur backend non trouvé"
fi
echo ""

echo "=== 5. LOGS CADDY RÉCENTS ==="
if docker ps | grep -q "caddy"; then
    CADDY_CONTAINER=$(docker ps | grep "caddy" | awk '{print $1}' | head -1)
    docker logs --tail=10 "$CADDY_CONTAINER" 2>&1 | grep -E "error|503|502|api" || echo "Aucune erreur récente"
fi
echo ""

echo "=== 6. LOGS BACKEND RÉCENTS ==="
if docker ps | grep -q "backend"; then
    BACKEND_CONTAINER=$(docker ps | grep "backend" | awk '{print $1}' | head -1)
    docker logs --tail=10 "$BACKEND_CONTAINER" 2>&1 | tail -5 || echo "Aucun log"
fi
echo ""

echo "=== 7. CONFIGURATION CADDYFILE ==="
if [ -f "Caddyfile" ]; then
    echo "Routes API dans Caddyfile:"
    grep -A 5 "@api" Caddyfile || echo "Section @api non trouvée"
else
    echo "❌ Caddyfile non trouvé"
fi
echo ""

echo "=== 8. CORRECTION PROPOSÉE ==="
echo "Si BACKEND_URL n'est pas défini ou incorrect, ajoutez dans .env:"
echo "BACKEND_URL=backend:8000"
echo ""
echo "Puis redémarrez Caddy:"
echo "docker compose -f docker-compose.prod.yml restart caddy"

