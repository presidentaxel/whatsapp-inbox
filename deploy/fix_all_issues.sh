#!/bin/bash
# Script complet pour diagnostiquer et corriger TOUS les problèmes

set -e

echo "=========================================="
echo "🔧 DIAGNOSTIC ET CORRECTION COMPLÈTE"
echo "=========================================="
echo ""

# 1. Trouver le projet
echo "=== 1. LOCALISATION DU PROJET ==="
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

cd "$PROJECT_DIR/deploy" 2>/dev/null || cd "$PROJECT_DIR"
echo "✅ Projet: $PROJECT_DIR"
echo "📁 Répertoire: $(pwd)"
echo ""

# 2. Vérifier les conteneurs
echo "=== 2. CONTENEURS DOCKER ==="
BACKEND_CONTAINER=$(docker ps --format "{{.Names}}" | grep -E "backend" | head -1)
CADDY_CONTAINER=$(docker ps --format "{{.Names}}" | grep -E "caddy" | head -1)

if [ -z "$BACKEND_CONTAINER" ]; then
    echo "❌ Backend non trouvé - Démarrage..."
    docker compose -f docker-compose.prod.yml up -d backend
    sleep 5
    BACKEND_CONTAINER=$(docker ps --format "{{.Names}}" | grep -E "backend" | head -1)
fi

if [ -z "$CADDY_CONTAINER" ]; then
    echo "❌ Caddy non trouvé - Démarrage..."
    docker compose -f docker-compose.prod.yml up -d caddy
    sleep 5
    CADDY_CONTAINER=$(docker ps --format "{{.Names}}" | grep -E "caddy" | head -1)
fi

echo "✅ Backend: $BACKEND_CONTAINER"
echo "✅ Caddy: $CADDY_CONTAINER"
echo ""

# 3. Vérifier BACKEND_URL
echo "=== 3. CONFIGURATION BACKEND_URL ==="
ENV_FILE=".env"
[ ! -f "$ENV_FILE" ] && ENV_FILE="../.env"

if [ -f "$ENV_FILE" ]; then
    if ! grep -q "^BACKEND_URL=" "$ENV_FILE"; then
        echo "⚠️  BACKEND_URL manquant - Ajout..."
        echo "BACKEND_URL=backend:8000" >> "$ENV_FILE"
    fi
    BACKEND_URL=$(grep "^BACKEND_URL=" "$ENV_FILE" | cut -d= -f2)
    echo "✅ BACKEND_URL=$BACKEND_URL"
else
    echo "⚠️  .env non trouvé - Création..."
    echo "BACKEND_URL=backend:8000" > "$ENV_FILE"
    BACKEND_URL="backend:8000"
fi
echo ""

# 4. Vérifier le réseau Docker
echo "=== 4. RÉSEAU DOCKER ==="
NETWORK=$(docker network ls | grep -E "appnet|deploy" | awk '{print $1}' | head -1)
if [ -n "$NETWORK" ]; then
    echo "✅ Réseau trouvé: $(docker network inspect $NETWORK --format '{{.Name}}')"
    
    # Vérifier que les conteneurs sont sur le même réseau
    BACKEND_NETWORKS=$(docker inspect "$BACKEND_CONTAINER" --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}')
    CADDY_NETWORKS=$(docker inspect "$CADDY_CONTAINER" --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}')
    
    if echo "$BACKEND_NETWORKS" | grep -q "appnet\|deploy"; then
        echo "✅ Backend sur le bon réseau"
    else
        echo "⚠️  Backend pas sur le bon réseau"
    fi
    
    if echo "$CADDY_NETWORKS" | grep -q "appnet\|deploy"; then
        echo "✅ Caddy sur le bon réseau"
    else
        echo "⚠️  Caddy pas sur le bon réseau"
    fi
else
    echo "⚠️  Réseau non trouvé"
fi
echo ""

# 5. Tester la connectivité backend
echo "=== 5. TEST CONNECTIVITÉ BACKEND ==="
echo "Test direct backend:"
if docker exec "$BACKEND_CONTAINER" curl -f -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Backend répond sur localhost:8000"
else
    echo "❌ Backend ne répond pas"
fi

echo "Test depuis Caddy vers backend:"
if docker exec "$CADDY_CONTAINER" wget -q -O- --timeout=3 http://backend:8000/health 2>&1 | grep -q "status"; then
    echo "✅ Caddy peut joindre backend:8000"
else
    echo "❌ Caddy ne peut PAS joindre backend:8000"
    echo "   Vérifiez que les deux conteneurs sont sur le même réseau Docker"
fi
echo ""

# 6. Vérifier le Caddyfile
echo "=== 6. VÉRIFICATION CADDYFILE ==="
if [ -f "Caddyfile" ]; then
    if grep -q "{\$BACKEND_URL:backend:8000}" Caddyfile; then
        echo "✅ Caddyfile utilise BACKEND_URL avec fallback"
    else
        echo "⚠️  Caddyfile n'utilise pas BACKEND_URL correctement"
    fi
    
    if grep -q "uri strip_prefix /api" Caddyfile; then
        echo "✅ Caddyfile strip /api (correct)"
    else
        echo "⚠️  Caddyfile ne strip pas /api"
    fi
else
    echo "❌ Caddyfile non trouvé"
fi
echo ""

# 7. Redémarrer avec la bonne configuration
echo "=== 7. REDÉMARRAGE AVEC CONFIGURATION ==="
echo "Redémarrage de Caddy avec BACKEND_URL..."
docker compose -f docker-compose.prod.yml stop caddy
docker compose -f docker-compose.prod.yml up -d caddy
sleep 5
echo ""

# 8. Test final
echo "=== 8. TESTS FINAUX ==="
echo "Test /api/accounts (via Caddy interne):"
RESPONSE=$(docker exec "$CADDY_CONTAINER" wget -q -O- --timeout=3 "http://localhost/api/accounts" 2>&1 | head -1)
if echo "$RESPONSE" | grep -q "error\|503\|502"; then
    echo "❌ Erreur: $RESPONSE"
else
    echo "✅ Réponse: $(echo "$RESPONSE" | head -c 100)..."
fi

echo ""
echo "Test /webhook/whatsapp (GET):"
WEBHOOK_RESPONSE=$(docker exec "$CADDY_CONTAINER" wget -q -O- --timeout=3 "http://localhost/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=test&hub.challenge=test123" 2>&1)
if echo "$WEBHOOK_RESPONSE" | grep -q "403"; then
    echo "✅ Webhook accessible (403 normal avec token de test)"
else
    echo "⚠️  Réponse inattendue: $WEBHOOK_RESPONSE"
fi
echo ""

# 9. Récupérer le token de vérification
echo "=== 9. TOKEN DE VÉRIFICATION ==="
TOKEN=$(docker exec "$BACKEND_CONTAINER" python -c "
import os
from dotenv import load_dotenv
load_dotenv('/app/.env')
print(os.getenv('WHATSAPP_VERIFY_TOKEN', ''))
" 2>/dev/null || echo "")

if [ -n "$TOKEN" ]; then
    echo "✅ Token trouvé: ${TOKEN:0:10}...${TOKEN: -5}"
    echo ""
    echo "📋 CONFIGURATION META:"
    echo "   URL: https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp"
    echo "   Token: $TOKEN"
else
    echo "❌ Token non trouvé"
fi
echo ""

# 10. Test depuis l'extérieur (si domaine configuré)
echo "=== 10. TEST EXTERNE ==="
DOMAIN=$(grep "^DOMAIN=" "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "")
if [ -n "$DOMAIN" ]; then
    echo "Test GET depuis l'extérieur:"
    EXTERNAL_TEST=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
        "https://$DOMAIN/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=$TOKEN&hub.challenge=test123" \
        2>&1 || echo "ERREUR_CONNEXION")
    
    HTTP_CODE=$(echo "$EXTERNAL_TEST" | grep "HTTP_CODE:" | cut -d: -f2)
    if [ "$HTTP_CODE" = "200" ]; then
        echo "✅ Webhook accessible depuis l'extérieur (200 OK)"
    elif [ "$HTTP_CODE" = "403" ]; then
        echo "⚠️  Webhook accessible mais token incorrect (403)"
        echo "   Vérifiez que le token dans Meta correspond exactement"
    else
        echo "❌ Erreur HTTP $HTTP_CODE"
        echo "   Vérifiez:"
        echo "   - Que le DNS pointe vers ce serveur"
        echo "   - Que le port 443 est ouvert"
        echo "   - Que Caddy fonctionne"
    fi
else
    echo "⚠️  DOMAIN non configuré dans .env"
fi
echo ""

echo "=========================================="
echo "✅ DIAGNOSTIC TERMINÉ"
echo "=========================================="
echo ""
echo "📋 RÉSUMÉ:"
echo "1. Vérifiez que BACKEND_URL=backend:8000 est dans .env"
echo "2. Vérifiez que les conteneurs sont sur le même réseau"
echo "3. Testez le webhook dans Meta avec le token affiché ci-dessus"
echo "4. Si les erreurs 503 persistent, redémarrez tous les services:"
echo "   docker compose -f docker-compose.prod.yml restart"

