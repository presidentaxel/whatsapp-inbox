#!/bin/bash
# Script pour diagnostiquer et corriger le problème de réseau Docker

echo "=========================================="
echo "DIAGNOSTIC RÉSEAU DOCKER"
echo "=========================================="
echo ""

# Couleurs
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }

# 1. Vérifier les réseaux
echo "1. RÉSEAUX DOCKER"
echo "-----------------"
docker network ls
echo ""

# 2. Vérifier sur quels réseaux sont les conteneurs
echo "2. RÉSEAUX DES CONTENEURS"
echo "-------------------------"

BACKEND_NEW="deploy-backend-1"
CADDY="deploy-caddy-1"

if [ -n "$BACKEND_NEW" ]; then
    echo "Backend ($BACKEND_NEW):"
    docker inspect "$BACKEND_NEW" --format '{{range $net, $conf := .NetworkSettings.Networks}}{{$net}} ({{$conf.IPAddress}}){{"\n"}}{{end}}' 2>/dev/null || echo "  (non trouvé)"
fi

if [ -n "$CADDY" ]; then
    echo ""
    echo "Caddy ($CADDY):"
    docker inspect "$CADDY" --format '{{range $net, $conf := .NetworkSettings.Networks}}{{$net}} ({{$conf.IPAddress}}){{"\n"}}{{end}}' 2>/dev/null || echo "  (non trouvé)"
fi
echo ""

# 3. Tester la connectivité
echo "3. TEST CONNECTIVITÉ"
echo "-------------------"

# Installer wget dans Caddy si nécessaire
echo "Test depuis Caddy vers backend:8000..."
if docker exec "$CADDY" wget -q -O- --timeout=3 http://backend:8000/healthz 2>/dev/null; then
    print_success "Caddy peut atteindre backend:8000"
elif docker exec "$CADDY" wget -q -O- --timeout=3 http://deploy-backend-1:8000/healthz 2>/dev/null; then
    print_warning "Caddy peut atteindre deploy-backend-1:8000 mais pas backend:8000"
    print_warning "Le problème: le nom 'backend' ne résout pas correctement"
else
    print_error "Caddy NE PEUT PAS atteindre le backend"
    echo ""
    echo "Tentative avec l'IP directe..."
    BACKEND_IP=$(docker inspect "$BACKEND_NEW" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null)
    if [ -n "$BACKEND_IP" ]; then
        echo "IP du backend: $BACKEND_IP"
        if docker exec "$CADDY" wget -q -O- --timeout=3 "http://$BACKEND_IP:8000/healthz" 2>/dev/null; then
            print_success "Caddy peut atteindre le backend par IP: $BACKEND_IP"
            print_warning "Le problème est la résolution DNS du nom 'backend'"
        else
            print_error "Même par IP, ça ne fonctionne pas"
        fi
    fi
fi
echo ""

# 4. Vérifier le Caddyfile
echo "4. CONFIGURATION CADDY"
echo "---------------------"
echo "Configuration actuelle du Caddyfile:"
docker exec "$CADDY" cat /etc/caddy/Caddyfile 2>/dev/null | grep -A 5 "webhook" || echo "  (non trouvé)"
echo ""

# 5. Vérifier les logs backend
echo "5. LOGS BACKEND (dernières 20 lignes)"
echo "-------------------------------------"
docker logs --tail=20 "$BACKEND_NEW" 2>&1
echo ""

# 6. Vérifier les logs Caddy
echo "6. LOGS CADDY (webhook)"
echo "----------------------"
docker logs --tail=30 "$CADDY" 2>&1 | grep -i webhook || echo "  (aucune mention de webhook)"
echo ""

# 7. Recommandations
echo "=========================================="
echo "RECOMMANDATIONS"
echo "=========================================="
echo ""

# Vérifier si les anciens conteneurs sont encore utilisés
OLD_BACKEND="whatsapp-inbox-backend-1"
if docker ps --format "{{.Names}}" | grep -q "$OLD_BACKEND"; then
    print_warning "Ancien conteneur backend trouvé: $OLD_BACKEND"
    echo "  → Il est peut-être encore utilisé par Caddy"
    echo "  → Vérifiez dans le Caddyfile quelle URL est utilisée"
fi

echo ""
echo "Actions possibles:"
echo "1. Vérifier que deploy-backend-1 et deploy-caddy-1 sont sur le même réseau"
echo "2. Vérifier le Caddyfile pour voir quelle URL est utilisée"
echo "3. Redémarrer les conteneurs pour forcer la résolution DNS"
echo "4. Arrêter les anciens conteneurs s'ils ne sont plus utilisés"

