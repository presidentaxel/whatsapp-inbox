#!/bin/bash
# Test simple du webhook depuis l'extérieur

DOMAIN=${DOMAIN:-"whatsapp.lamaisonduchauffeurvtc.fr"}

echo "=== TEST WEBHOOK EXTERNE ==="
echo "Domaine: $DOMAIN"
echo ""

# 1. Récupérer le token
echo "=== 1. TOKEN DE VÉRIFICATION ==="
TOKEN=$(docker exec deploy-backend-1 python -c "
import os
from dotenv import load_dotenv
load_dotenv('/app/.env')
print(os.getenv('WHATSAPP_VERIFY_TOKEN', ''))
" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "❌ Token non trouvé"
    exit 1
fi

echo "✅ Token trouvé: ${TOKEN:0:10}...${TOKEN: -5}"
echo ""

# 2. Test GET avec le vrai token
echo "=== 2. TEST GET (avec vrai token) ==="
CHALLENGE="test_challenge_$(date +%s)"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
    "https://$DOMAIN/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=$TOKEN&hub.challenge=$CHALLENGE")

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | grep -v "HTTP_CODE:")

if [ "$HTTP_CODE" = "200" ]; then
    if [ "$BODY" = "$CHALLENGE" ]; then
        echo "✅ Webhook GET fonctionne !"
        echo "   Réponse: $BODY"
    else
        echo "⚠️  Webhook répond 200 mais challenge incorrect"
        echo "   Attendu: $CHALLENGE"
        echo "   Reçu: $BODY"
    fi
elif [ "$HTTP_CODE" = "403" ]; then
    echo "❌ Webhook accessible mais token incorrect (403)"
    echo "   Vérifiez que le token dans Meta correspond à: ${TOKEN:0:10}...${TOKEN: -5}"
else
    echo "❌ Erreur HTTP $HTTP_CODE"
    echo "   Réponse: $BODY"
fi
echo ""

# 3. Test POST
echo "=== 3. TEST POST ==="
TEST_PAYLOAD='{"object":"whatsapp_business_account","entry":[]}'
RESPONSE_POST=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d "$TEST_PAYLOAD" \
    "https://$DOMAIN/webhook/whatsapp")

HTTP_CODE_POST=$(echo "$RESPONSE_POST" | grep "HTTP_CODE:" | cut -d: -f2)
BODY_POST=$(echo "$RESPONSE_POST" | grep -v "HTTP_CODE:")

if [ "$HTTP_CODE_POST" = "200" ]; then
    echo "✅ Webhook POST fonctionne !"
    echo "   Réponse: $BODY_POST"
else
    echo "❌ Erreur HTTP $HTTP_CODE_POST"
    echo "   Réponse: $BODY_POST"
fi
echo ""

# 4. Instructions Meta
echo "=== 4. CONFIGURATION META ==="
echo "URL: https://$DOMAIN/webhook/whatsapp"
echo "Token: $TOKEN"
echo ""
echo "Vérifiez dans Meta Developers Console que:"
echo "  1. L'URL correspond exactement"
echo "  2. Le token correspond exactement"
echo "  3. Les champs 'messages' et 'message_status' sont abonnés"

