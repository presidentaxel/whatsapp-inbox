#!/bin/bash
# Script de vérification rapide - à exécuter depuis n'importe où

echo "=========================================="
echo "VÉRIFICATION RAPIDE - WEBHOOKS OVH"
echo "=========================================="
echo ""

# 1. Vérifier Docker
echo "1. DOCKER"
if command -v docker &> /dev/null; then
    echo "✅ Docker installé"
    docker --version
else
    echo "❌ Docker non installé"
    exit 1
fi
echo ""

# 2. Chercher les conteneurs
echo "2. CONTENEURS"
BACKEND_CONTAINER=$(docker ps --format "{{.Names}}" | grep -E "backend|whatsapp" | head -1)
CADDY_CONTAINER=$(docker ps --format "{{.Names}}" | grep -i caddy | head -1)

if [ -n "$BACKEND_CONTAINER" ]; then
    echo "✅ Backend trouvé: $BACKEND_CONTAINER"
else
    echo "❌ Backend non trouvé"
    echo "   Conteneurs en cours:"
    docker ps --format "table {{.Names}}\t{{.Status}}"
fi

if [ -n "$CADDY_CONTAINER" ]; then
    echo "✅ Caddy trouvé: $CADDY_CONTAINER"
else
    echo "❌ Caddy non trouvé"
fi
echo ""

# 3. Tester le backend
echo "3. TEST BACKEND"
if [ -n "$BACKEND_CONTAINER" ]; then
    if docker exec "$BACKEND_CONTAINER" curl -s http://localhost:8000/healthz > /dev/null 2>&1; then
        echo "✅ Backend répond sur localhost:8000"
        RESPONSE=$(docker exec "$BACKEND_CONTAINER" curl -s http://localhost:8000/healthz)
        echo "   Réponse: $RESPONSE"
    else
        echo "❌ Backend ne répond pas"
    fi
else
    echo "⚠️  Backend non trouvé, impossible de tester"
fi
echo ""

# 4. Tester la connectivité depuis Caddy
echo "4. CONNECTIVITÉ CADDY -> BACKEND"
if [ -n "$CADDY_CONTAINER" ] && [ -n "$BACKEND_CONTAINER" ]; then
    if docker exec "$CADDY_CONTAINER" wget -q -O- --timeout=2 http://backend:8000/healthz 2>/dev/null; then
        echo "✅ Caddy peut atteindre backend:8000"
    else
        echo "❌ Caddy NE PEUT PAS atteindre backend:8000"
        echo "   C'est probablement le problème !"
        echo ""
        echo "   Vérifications:"
        echo "   1. Les deux conteneurs sont-ils sur le même réseau ?"
        echo "   2. Le backend écoute-t-il sur 0.0.0.0:8000 ?"
        echo "   3. Le nom 'backend' résout-il correctement ?"
    fi
else
    echo "⚠️  Caddy ou backend non trouvé"
fi
echo ""

# 5. Logs récents
echo "5. LOGS RÉCENTS (backend)"
if [ -n "$BACKEND_CONTAINER" ]; then
    echo "Dernières lignes:"
    docker logs --tail=5 "$BACKEND_CONTAINER" 2>&1 | grep -E "webhook|POST|Uvicorn|ERROR" || echo "   (aucun log pertinent)"
fi
echo ""

# 6. Test endpoint externe
echo "6. TEST ENDPOINT EXTERNE"
echo "Testez manuellement:"
echo "  curl -X GET 'https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=VOTRE_TOKEN&hub.challenge=test'"
echo ""

echo "=========================================="
echo "RÉSUMÉ"
echo "=========================================="
if [ -n "$BACKEND_CONTAINER" ] && [ -n "$CADDY_CONTAINER" ]; then
    echo "✅ Conteneurs trouvés"
    echo "   → Vérifiez la connectivité Caddy -> Backend ci-dessus"
else
    echo "❌ Conteneurs manquants"
    echo "   → Trouvez d'abord où se trouve votre projet"
fi

