#!/bin/bash
# Script de diagnostic pour les webhooks sur serveur OVH

set -e

echo "=========================================="
echo "DIAGNOSTIC WEBHOOK - SERVEUR OVH"
echo "=========================================="
echo ""

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# 1. Vérifier Docker
echo "1. VÉRIFICATION DOCKER"
echo "----------------------"
if command -v docker &> /dev/null; then
    print_success "Docker est installé"
    docker --version
else
    print_error "Docker n'est pas installé"
    exit 1
fi

if command -v docker-compose &> /dev/null || docker compose version &> /dev/null; then
    print_success "Docker Compose est disponible"
else
    print_error "Docker Compose n'est pas disponible"
    exit 1
fi
echo ""

# 2. Vérifier les conteneurs
echo "2. ÉTAT DES CONTENEURS"
echo "----------------------"
cd "$(dirname "$0")" || exit

if [ -f "docker-compose.prod.yml" ]; then
    print_info "Fichier docker-compose.prod.yml trouvé"
    
    # Vérifier les conteneurs en cours d'exécution
    if docker compose -f docker-compose.prod.yml ps | grep -q "Up"; then
        print_success "Des conteneurs sont en cours d'exécution:"
        docker compose -f docker-compose.prod.yml ps
    else
        print_error "Aucun conteneur n'est en cours d'exécution"
        print_info "Démarrez les conteneurs avec: docker compose -f docker-compose.prod.yml up -d"
    fi
else
    print_error "Fichier docker-compose.prod.yml non trouvé"
fi
echo ""

# 3. Vérifier le backend
echo "3. VÉRIFICATION DU BACKEND"
echo "--------------------------"
BACKEND_CONTAINER=$(docker compose -f docker-compose.prod.yml ps -q backend 2>/dev/null || echo "")

if [ -n "$BACKEND_CONTAINER" ]; then
    print_success "Conteneur backend trouvé: $BACKEND_CONTAINER"
    
    # Vérifier si le backend répond
    if docker exec "$BACKEND_CONTAINER" curl -s http://localhost:8000/healthz > /dev/null 2>&1; then
        print_success "Le backend répond sur localhost:8000"
        RESPONSE=$(docker exec "$BACKEND_CONTAINER" curl -s http://localhost:8000/healthz)
        print_info "Réponse: $RESPONSE"
    else
        print_error "Le backend ne répond pas sur localhost:8000"
    fi
    
    # Vérifier les logs récents
    print_info "Dernières lignes des logs backend:"
    docker compose -f docker-compose.prod.yml logs --tail=10 backend
else
    print_error "Conteneur backend non trouvé"
    print_info "Vérifiez que le service backend est défini dans docker-compose.prod.yml"
fi
echo ""

# 4. Vérifier Caddy
echo "4. VÉRIFICATION CADDY"
echo "---------------------"
CADDY_CONTAINER=$(docker compose -f docker-compose.prod.yml ps -q caddy 2>/dev/null || echo "")

if [ -n "$CADDY_CONTAINER" ]; then
    print_success "Conteneur Caddy trouvé: $CADDY_CONTAINER"
    
    # Vérifier la configuration Caddy
    if docker exec "$CADDY_CONTAINER" caddy validate --config /etc/caddy/Caddyfile 2>&1; then
        print_success "Configuration Caddy valide"
    else
        print_error "Configuration Caddy invalide"
        print_info "Configuration actuelle:"
        docker exec "$CADDY_CONTAINER" cat /etc/caddy/Caddyfile
    fi
    
    # Vérifier les logs récents
    print_info "Dernières lignes des logs Caddy:"
    docker compose -f docker-compose.prod.yml logs --tail=10 caddy
else
    print_error "Conteneur Caddy non trouvé"
fi
echo ""

# 5. Vérifier le réseau Docker
echo "5. VÉRIFICATION RÉSEAU DOCKER"
echo "------------------------------"
NETWORK_NAME=$(docker compose -f docker-compose.prod.yml config 2>/dev/null | grep -A 5 "networks:" | grep -E "^\s+[a-zA-Z]" | head -1 | awk '{print $1}' | tr -d ':')

if [ -n "$NETWORK_NAME" ]; then
    print_info "Réseau Docker: $NETWORK_NAME"
    
    # Vérifier si les conteneurs sont sur le même réseau
    if [ -n "$BACKEND_CONTAINER" ] && [ -n "$CADDY_CONTAINER" ]; then
        BACKEND_NETWORK=$(docker inspect "$BACKEND_CONTAINER" --format '{{range $net, $conf := .NetworkSettings.Networks}}{{$net}}{{end}}' 2>/dev/null || echo "")
        CADDY_NETWORK=$(docker inspect "$CADDY_CONTAINER" --format '{{range $net, $conf := .NetworkSettings.Networks}}{{$net}}{{end}}' 2>/dev/null || echo "")
        
        if [ "$BACKEND_NETWORK" = "$CADDY_NETWORK" ]; then
            print_success "Backend et Caddy sont sur le même réseau: $BACKEND_NETWORK"
        else
            print_error "Backend et Caddy ne sont pas sur le même réseau!"
            print_info "Backend: $BACKEND_NETWORK"
            print_info "Caddy: $CADDY_NETWORK"
        fi
    fi
    
    # Tester la connectivité depuis Caddy vers Backend
    if [ -n "$CADDY_CONTAINER" ] && [ -n "$BACKEND_CONTAINER" ]; then
        print_info "Test de connectivité depuis Caddy vers Backend..."
        if docker exec "$CADDY_CONTAINER" wget -q --spider --timeout=2 http://backend:8000/healthz 2>&1; then
            print_success "Caddy peut atteindre le backend sur backend:8000"
        else
            print_error "Caddy NE PEUT PAS atteindre le backend sur backend:8000"
            print_info "Vérifiez:"
            print_info "  1. Que les deux conteneurs sont sur le même réseau Docker"
            print_info "  2. Que le backend écoute sur 0.0.0.0:8000 (pas seulement localhost)"
            print_info "  3. Que le nom 'backend' résout correctement dans le réseau Docker"
        fi
    fi
else
    print_warning "Réseau Docker non trouvé dans la configuration"
fi
echo ""

# 6. Tester l'endpoint webhook localement
echo "6. TEST DE L'ENDPOINT WEBHOOK"
echo "-----------------------------"
if [ -n "$BACKEND_CONTAINER" ]; then
    print_info "Test depuis l'hôte vers le backend (port exposé)..."
    
    # Trouver le port exposé
    EXPOSED_PORT=$(docker compose -f docker-compose.prod.yml ps backend 2>/dev/null | grep -oP '0.0.0.0:\K[0-9]+' | head -1 || echo "")
    
    if [ -n "$EXPOSED_PORT" ]; then
        print_info "Port exposé: $EXPOSED_PORT"
        if curl -s "http://localhost:$EXPOSED_PORT/healthz" > /dev/null 2>&1; then
            print_success "Le backend est accessible depuis l'hôte sur le port $EXPOSED_PORT"
        else
            print_error "Le backend n'est pas accessible depuis l'hôte sur le port $EXPOSED_PORT"
        fi
    else
        print_warning "Aucun port exposé trouvé pour le backend"
        print_info "Le backend n'est peut-être pas accessible depuis l'extérieur du réseau Docker"
    fi
fi
echo ""

# 7. Vérifier l'accessibilité externe
echo "7. VÉRIFICATION ACCESSIBILITÉ EXTERNE"
echo "-------------------------------------"
DOMAIN=$(grep -E "^DOMAIN=" .env 2>/dev/null | cut -d '=' -f2 || echo "")

if [ -n "$DOMAIN" ]; then
    print_info "Domaine configuré: $DOMAIN"
    
    # Tester l'endpoint webhook
    WEBHOOK_URL="https://$DOMAIN/webhook/whatsapp"
    print_info "Test de l'endpoint webhook: $WEBHOOK_URL"
    
    if curl -s -o /dev/null -w "%{http_code}" "$WEBHOOK_URL?hub.mode=subscribe&hub.verify_token=test&hub.challenge=test" | grep -q "403\|200"; then
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$WEBHOOK_URL?hub.mode=subscribe&hub.verify_token=test&hub.challenge=test")
        if [ "$HTTP_CODE" = "200" ]; then
            print_success "L'endpoint webhook est accessible (code: $HTTP_CODE)"
        else
            print_warning "L'endpoint webhook répond mais avec le code: $HTTP_CODE (normal si le token est incorrect)"
        fi
    else
        print_error "L'endpoint webhook n'est pas accessible"
        print_info "Vérifiez:"
        print_info "  1. Que le DNS pointe vers ce serveur"
        print_info "  2. Que les ports 80 et 443 sont ouverts dans le firewall"
        print_info "  3. Que Caddy est bien démarré et écoute sur ces ports"
    fi
else
    print_warning "Variable DOMAIN non trouvée dans .env"
fi
echo ""

# 8. Résumé et recommandations
echo "=========================================="
echo "RÉSUMÉ ET RECOMMANDATIONS"
echo "=========================================="
echo ""

if [ -z "$BACKEND_CONTAINER" ]; then
    print_error "PROBLÈME CRITIQUE: Le conteneur backend n'est pas démarré"
    print_info "Solution: docker compose -f docker-compose.prod.yml up -d backend"
    echo ""
fi

if [ -z "$CADDY_CONTAINER" ]; then
    print_error "PROBLÈME CRITIQUE: Le conteneur Caddy n'est pas démarré"
    print_info "Solution: docker compose -f docker-compose.prod.yml up -d caddy"
    echo ""
fi

print_info "Commandes utiles:"
echo "  - Voir tous les logs: docker compose -f docker-compose.prod.yml logs"
echo "  - Voir les logs backend: docker compose -f docker-compose.prod.yml logs backend"
echo "  - Voir les logs Caddy: docker compose -f docker-compose.prod.yml logs caddy"
echo "  - Redémarrer Caddy: docker compose -f docker-compose.prod.yml restart caddy"
echo "  - Redémarrer le backend: docker compose -f docker-compose.prod.yml restart backend"
echo "  - Voir la configuration Caddy: docker exec $CADDY_CONTAINER cat /etc/caddy/Caddyfile"
echo ""

