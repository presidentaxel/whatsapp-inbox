#!/bin/bash
# Script final pour corriger les problèmes sur OVH

set -e

echo "=========================================="
echo "🔧 CORRECTION FINALE OVH"
echo "=========================================="
echo ""

# Aller dans le répertoire du projet
cd /opt/whatsapp-inbox/deploy
echo "📁 Répertoire: $(pwd)"
echo ""

# 1. Ajouter BACKEND_URL au .env
echo "=== 1. CONFIGURATION BACKEND_URL ==="
if [ -f .env ]; then
    if ! grep -q "^BACKEND_URL=" .env; then
        echo "BACKEND_URL=backend:8000" >> .env
        echo "✅ BACKEND_URL ajouté"
    else
        # S'assurer que la valeur est correcte
        sed -i 's|^BACKEND_URL=.*|BACKEND_URL=backend:8000|' .env
        echo "✅ BACKEND_URL mis à jour"
    fi
    echo "Contenu de BACKEND_URL:"
    grep "^BACKEND_URL=" .env
else
    echo "BACKEND_URL=backend:8000" > .env
    echo "✅ .env créé avec BACKEND_URL"
fi
echo ""

# 2. Vérifier docker-compose.prod.yml
echo "=== 2. VÉRIFICATION DOCKER-COMPOSE ==="
if grep -q "BACKEND_URL" docker-compose.prod.yml; then
    echo "✅ docker-compose.prod.yml contient BACKEND_URL"
else
    echo "⚠️  BACKEND_URL manquant dans docker-compose.prod.yml"
fi
echo ""

# 3. Redémarrer Caddy avec la nouvelle configuration
echo "=== 3. REDÉMARRAGE CADDY ==="
echo "Arrêt de Caddy..."
docker compose -f docker-compose.prod.yml stop caddy || true
sleep 2

echo "Démarrage de Caddy..."
docker compose -f docker-compose.prod.yml up -d caddy
sleep 5
echo ""

# 4. Vérifier la connectivité
echo "=== 4. VÉRIFICATION CONNECTIVITÉ ==="
echo "Test Caddy → Backend:"
if docker exec deploy-caddy-1 wget -q -O- --timeout=3 http://backend:8000/health 2>&1 | grep -q "status"; then
    echo "✅ Caddy peut joindre backend:8000"
else
    echo "❌ Caddy ne peut PAS joindre backend:8000"
    echo "   Vérifiez les logs: docker logs deploy-caddy-1"
fi
echo ""

# 5. Test des routes API
echo "=== 5. TEST ROUTES API ==="
echo "Test /api/accounts (via Caddy):"
RESPONSE=$(docker exec deploy-caddy-1 wget -q -O- --timeout=3 "http://localhost/api/accounts" 2>&1 | head -1)
if echo "$RESPONSE" | grep -q "error\|503\|502"; then
    echo "❌ Erreur: $RESPONSE"
else
    echo "✅ Réponse reçue: $(echo "$RESPONSE" | head -c 100)..."
fi
echo ""

# 6. Récupérer le token de vérification
echo "=== 6. TOKEN DE VÉRIFICATION ==="
TOKEN=$(docker exec deploy-backend-1 python -c "
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

# 7. Test webhook depuis l'extérieur
echo "=== 7. TEST WEBHOOK EXTERNE ==="
if [ -n "$TOKEN" ]; then
    DOMAIN=$(grep "^DOMAIN=" .env 2>/dev/null | cut -d= -f2 || echo "whatsapp.lamaisonduchauffeurvtc.fr")
    echo "Test GET avec le vrai token:"
    EXTERNAL_TEST=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
        "https://$DOMAIN/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=$TOKEN&hub.challenge=test123" \
        2>&1 || echo "ERREUR_CONNEXION")
    
    HTTP_CODE=$(echo "$EXTERNAL_TEST" | grep "HTTP_CODE:" | cut -d: -f2)
    BODY=$(echo "$EXTERNAL_TEST" | grep -v "HTTP_CODE:")
    
    if [ "$HTTP_CODE" = "200" ]; then
        if [ "$BODY" = "test123" ]; then
            echo "✅ Webhook fonctionne parfaitement !"
            echo "   Réponse: $BODY"
        else
            echo "⚠️  Webhook répond 200 mais challenge incorrect"
            echo "   Attendu: test123"
            echo "   Reçu: $BODY"
        fi
    elif [ "$HTTP_CODE" = "403" ]; then
        echo "⚠️  Webhook accessible mais token incorrect (403)"
        echo "   Vérifiez que le token dans Meta correspond EXACTEMENT à celui ci-dessus"
    else
        echo "❌ Erreur HTTP $HTTP_CODE"
        echo "   Réponse: $BODY"
    fi
else
    echo "⚠️  Impossible de tester sans token"
fi
echo ""

# 8. Logs récents
echo "=== 8. LOGS RÉCENTS ==="
echo "Logs Caddy (dernières 5 lignes):"
docker logs --tail=5 deploy-caddy-1 2>&1 | tail -5 || echo "Aucun log"
echo ""
echo "Logs Backend (dernières 5 lignes):"
docker logs --tail=5 deploy-backend-1 2>&1 | tail -5 || echo "Aucun log"
echo ""

echo "=========================================="
echo "✅ CORRECTION TERMINÉE"
echo "=========================================="
echo ""
echo "📋 PROCHAINES ÉTAPES:"
echo "1. Rechargez la page frontend (https://whatsapp.lamaisonduchauffeurvtc.fr)"
echo "2. Les erreurs 503 devraient avoir disparu"
echo "3. Testez le webhook dans Meta avec le token affiché ci-dessus"
echo ""
echo "Si les erreurs persistent:"
echo "  docker logs deploy-caddy-1 --tail=50"
echo "  docker logs deploy-backend-1 --tail=50"

