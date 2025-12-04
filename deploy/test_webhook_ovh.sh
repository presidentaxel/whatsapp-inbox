#!/bin/bash
# Script de test complet pour les webhooks sur OVH

echo "=========================================="
echo "TEST COMPLET WEBHOOK OVH"
echo "=========================================="
echo ""

# Couleurs
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }
print_info() { echo -e "${YELLOW}ℹ️  $1${NC}"; }

# 1. Test backend avec le bon endpoint
echo "1. TEST BACKEND - /health (pas /healthz)"
echo "----------------------------------------"
docker exec deploy-caddy-1 wget -q -O- --timeout=3 http://backend:8000/health 2>&1 && print_success "Backend répond sur /health" || print_error "Backend ne répond pas sur /health"
echo ""

# 2. Test endpoint racine
echo "2. TEST BACKEND - / (racine)"
echo "----------------------------"
RESPONSE=$(docker exec deploy-caddy-1 wget -q -O- --timeout=3 http://backend:8000/ 2>&1)
if echo "$RESPONSE" | grep -q "status"; then
    print_success "Backend répond sur /"
    echo "$RESPONSE" | head -3
else
    print_error "Backend ne répond pas correctement sur /"
    echo "$RESPONSE"
fi
echo ""

# 3. Test webhook GET (vérification)
echo "3. TEST WEBHOOK - GET (vérification)"
echo "------------------------------------"
# Utiliser le verify token depuis les variables d'env si possible, sinon utiliser un test
TEST_TOKEN="test_token_123"
RESPONSE=$(docker exec deploy-caddy-1 wget -q -O- --timeout=3 "http://backend:8000/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=$TEST_TOKEN&hub.challenge=test123" 2>&1)
if echo "$RESPONSE" | grep -q "403\|test123"; then
    if echo "$RESPONSE" | grep -q "test123"; then
        print_success "Webhook GET fonctionne (challenge retourné)"
    else
        print_info "Webhook GET répond (403 = token incorrect, c'est normal)"
    fi
else
    print_error "Webhook GET ne répond pas correctement"
    echo "Réponse: $RESPONSE"
fi
echo ""

# 4. Test webhook POST (simulé)
echo "4. TEST WEBHOOK - POST (simulé)"
echo "-------------------------------"
TEST_PAYLOAD='{"object":"whatsapp_business_account","entry":[]}'
RESPONSE=$(docker exec deploy-caddy-1 wget -q -O- --timeout=3 --post-data="$TEST_PAYLOAD" --header="Content-Type: application/json" http://backend:8000/webhook/whatsapp 2>&1)
if echo "$RESPONSE" | grep -q "received\|status"; then
    print_success "Webhook POST fonctionne"
    echo "$RESPONSE"
else
    print_error "Webhook POST ne répond pas correctement"
    echo "Réponse: $RESPONSE"
fi
echo ""

# 5. Vérifier les logs backend pour voir si les requêtes arrivent
echo "5. LOGS BACKEND (dernières 10 lignes)"
echo "-------------------------------------"
docker logs --tail=10 deploy-backend-1 2>&1
echo ""

# 6. Vérifier la configuration Caddy complète
echo "6. CONFIGURATION CADDY COMPLÈTE"
echo "------------------------------"
docker exec deploy-caddy-1 cat /etc/caddy/Caddyfile 2>/dev/null
echo ""

# 7. Test depuis l'extérieur
echo "7. TEST ENDPOINT EXTERNE"
echo "------------------------"
print_info "Testez manuellement depuis votre machine:"
echo "  curl -X GET 'https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=VOTRE_TOKEN&hub.challenge=test'"
echo ""

echo "=========================================="
echo "RÉSUMÉ"
echo "=========================================="
echo ""
print_info "Si tous les tests passent mais que les webhooks n'arrivent toujours pas:"
echo "  1. Vérifiez la configuration dans Meta (URL et token)"
echo "  2. Vérifiez les logs Meta pour voir les tentatives de livraison"
echo "  3. Vérifiez que le firewall OVH autorise les connexions entrantes sur 80/443"

