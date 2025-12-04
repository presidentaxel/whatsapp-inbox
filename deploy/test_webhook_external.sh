#!/bin/bash
# Script pour tester le webhook depuis l'extérieur et vérifier la configuration

set -e

echo "=== TEST WEBHOOK EXTERNE ==="
echo ""

# Couleurs
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Récupérer le domaine depuis les variables d'environnement ou utiliser une valeur par défaut
DOMAIN=${DOMAIN:-"whatsapp.lamaisonduchauffeurvtc.fr"}

echo "🌐 Domaine: $DOMAIN"
echo ""

# 1. Vérifier le token dans le backend
echo "=== 1. TOKEN DE VÉRIFICATION ==="
TOKEN=$(docker exec deploy-backend-1 python -c "
import os
from dotenv import load_dotenv
load_dotenv('/app/.env')
token = os.getenv('WHATSAPP_VERIFY_TOKEN')
if token:
    print(f'{token[:10]}...{token[-5:]}')
else:
    print('NON CONFIGURÉ')
" 2>/dev/null || echo "ERREUR: Impossible de lire le token")

if [ "$TOKEN" != "NON CONFIGURÉ" ] && [ "$TOKEN" != "ERREUR"* ]; then
    echo -e "${GREEN}✅ Token trouvé: $TOKEN${NC}"
    echo "   ⚠️  Vérifiez que ce token correspond EXACTEMENT à celui dans Meta"
else
    echo -e "${RED}❌ Token non configuré ou erreur${NC}"
fi
echo ""

# 2. Test GET depuis l'extérieur (simulation Meta)
echo "=== 2. TEST GET (VÉRIFICATION META) ==="
TEST_TOKEN="test_token_12345"
CHALLENGE="test_challenge_67890"

RESPONSE=$(curl -s -w "\n%{http_code}" \
    "https://$DOMAIN/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=$TEST_TOKEN&hub.challenge=$CHALLENGE" \
    2>&1 || echo "ERREUR_CONNEXION")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ Webhook accessible (200 OK)${NC}"
    echo "   Réponse: $BODY"
elif [ "$HTTP_CODE" = "403" ]; then
    echo -e "${YELLOW}⚠️  Webhook accessible mais token incorrect (403)${NC}"
    echo "   C'est normal si le token ne correspond pas"
    echo "   Réponse: $BODY"
elif [ "$HTTP_CODE" = "404" ]; then
    echo -e "${RED}❌ Webhook non trouvé (404)${NC}"
    echo "   Vérifiez la configuration Caddy"
elif [[ "$RESPONSE" == *"ERREUR_CONNEXION"* ]]; then
    echo -e "${RED}❌ Impossible de se connecter au serveur${NC}"
    echo "   Vérifiez:"
    echo "   - Que le DNS pointe vers ce serveur"
    echo "   - Que le port 443 est ouvert"
    echo "   - Que Caddy fonctionne"
else
    echo -e "${RED}❌ Erreur HTTP $HTTP_CODE${NC}"
    echo "   Réponse: $BODY"
fi
echo ""

# 3. Test POST depuis l'extérieur (simulation webhook)
echo "=== 3. TEST POST (WEBHOOK META) ==="
TEST_PAYLOAD='{"object":"whatsapp_business_account","entry":[]}'

RESPONSE_POST=$(curl -s -w "\n%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d "$TEST_PAYLOAD" \
    "https://$DOMAIN/webhook/whatsapp" \
    2>&1 || echo "ERREUR_CONNEXION")

HTTP_CODE_POST=$(echo "$RESPONSE_POST" | tail -1)
BODY_POST=$(echo "$RESPONSE_POST" | head -n -1)

if [ "$HTTP_CODE_POST" = "200" ]; then
    echo -e "${GREEN}✅ Webhook POST fonctionne (200 OK)${NC}"
    echo "   Réponse: $BODY_POST"
elif [[ "$RESPONSE_POST" == *"ERREUR_CONNEXION"* ]]; then
    echo -e "${RED}❌ Impossible de se connecter au serveur${NC}"
else
    echo -e "${YELLOW}⚠️  Réponse HTTP $HTTP_CODE_POST${NC}"
    echo "   Réponse: $BODY_POST"
fi
echo ""

# 4. Vérifier les logs backend récents
echo "=== 4. LOGS BACKEND RÉCENTS (webhook) ==="
docker logs --tail=10 deploy-backend-1 2>&1 | grep -i "webhook" | tail -5 || echo "Aucun log webhook récent"
echo ""

# 5. Instructions pour Meta
echo "=== 5. CONFIGURATION META ==="
echo "Pour configurer le webhook dans Meta:"
echo ""
echo "1. URL du webhook:"
echo "   https://$DOMAIN/webhook/whatsapp"
echo ""
echo "2. Verify token:"
if [ "$TOKEN" != "NON CONFIGURÉ" ] && [ "$TOKEN" != "ERREUR"* ]; then
    FULL_TOKEN=$(docker exec deploy-backend-1 python -c "
import os
from dotenv import load_dotenv
load_dotenv('/app/.env')
print(os.getenv('WHATSAPP_VERIFY_TOKEN', ''))
" 2>/dev/null || echo "")
    if [ -n "$FULL_TOKEN" ]; then
        echo "   $FULL_TOKEN"
    else
        echo "   (Récupérez depuis le .env du backend)"
    fi
else
    echo "   ⚠️  Configurez WHATSAPP_VERIFY_TOKEN dans le .env du backend"
fi
echo ""
echo "3. Champs à abonner:"
echo "   - messages"
echo "   - message_status"
echo ""
echo "=== FIN DES TESTS ==="

