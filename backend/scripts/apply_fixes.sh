#!/bin/bash

# Script d'application automatique des fixes pour les erreurs 5xx
# Usage: bash backend/scripts/apply_fixes.sh [--phase1|--phase2|--all]

set -e

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BACKEND_DIR"

echo -e "${BLUE}╔════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Application des fixes - Erreurs 5xx        ║${NC}"
echo -e "${BLUE}╔════════════════════════════════════════════════╗${NC}"
echo ""

# Fonction pour demander confirmation
confirm() {
    read -p "$1 (y/n) " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]]
}

# Vérifier que nous sommes dans le bon dossier
if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}❌ Erreur: Le fichier requirements.txt n'existe pas.${NC}"
    echo -e "${RED}   Assurez-vous d'être dans le dossier backend/${NC}"
    exit 1
fi

# Phase 1: Fixes urgents
apply_phase1() {
    echo -e "${YELLOW}📦 Phase 1: Fixes urgents${NC}"
    echo ""
    
    # Vérifier les nouveaux modules
    echo "1. Vérification des modules créés..."
    
    required_files=(
        "app/core/http_client.py"
        "app/core/retry.py"
        "app/core/circuit_breaker.py"
        "app/core/cache.py"
        "app/api/routes_health.py"
        "app/services/bot_service_improved.py"
    )
    
    missing_files=0
    for file in "${required_files[@]}"; do
        if [ -f "$file" ]; then
            echo -e "   ${GREEN}✓${NC} $file"
        else
            echo -e "   ${RED}✗${NC} $file ${RED}(manquant)${NC}"
            missing_files=$((missing_files + 1))
        fi
    done
    
    if [ $missing_files -gt 0 ]; then
        echo -e "${RED}❌ Il manque $missing_files fichier(s). Arrêt.${NC}"
        exit 1
    fi
    
    echo ""
    echo "2. Installation des dépendances..."
    pip install -q tenacity>=8.0.0 cachetools>=5.3.0
    echo -e "   ${GREEN}✓${NC} tenacity et cachetools installés"
    
    echo ""
    echo "3. Activation de bot_service amélioré..."
    
    if [ -f "app/services/bot_service.py" ]; then
        if confirm "   Voulez-vous sauvegarder l'ancien bot_service.py ?"; then
            cp app/services/bot_service.py app/services/bot_service_old.py
            echo -e "   ${GREEN}✓${NC} Ancien fichier sauvegardé"
        fi
    fi
    
    if confirm "   Activer bot_service_improved.py ?"; then
        cp app/services/bot_service_improved.py app/services/bot_service.py
        echo -e "   ${GREEN}✓${NC} bot_service.py remplacé"
    else
        echo -e "   ${YELLOW}⊘${NC} Sauté"
    fi
    
    echo ""
    echo -e "${GREEN}✅ Phase 1 terminée !${NC}"
    echo ""
}

# Phase 2: Améliorations importantes
apply_phase2() {
    echo -e "${YELLOW}🔧 Phase 2: Améliorations importantes${NC}"
    echo ""
    
    echo "Cette phase nécessite des modifications manuelles:"
    echo ""
    echo "1. Ajouter timeout sur Supabase (db.py)"
    echo "2. Améliorer message_service.py"
    echo "3. Améliorer auth.py"
    echo ""
    echo "Voir GUIDE_IMPLEMENTATION.md pour les instructions détaillées."
    echo ""
    
    if confirm "Ouvrir le guide maintenant ?"; then
        if command -v xdg-open &> /dev/null; then
            xdg-open ../GUIDE_IMPLEMENTATION.md &
        elif command -v open &> /dev/null; then
            open ../GUIDE_IMPLEMENTATION.md &
        else
            echo "   Ouvrez manuellement: backend/GUIDE_IMPLEMENTATION.md"
        fi
    fi
    
    echo ""
}

# Tests
run_tests() {
    echo -e "${YELLOW}🧪 Tests${NC}"
    echo ""
    
    echo "1. Test d'import des nouveaux modules..."
    python3 -c "
from app.core.http_client import get_http_client
from app.core.retry import retry_on_network_error
from app.core.circuit_breaker import gemini_circuit_breaker
from app.core.cache import get_cache
print('✓ Tous les imports fonctionnent')
" && echo -e "   ${GREEN}✓${NC} Imports OK" || echo -e "   ${RED}✗${NC} Erreur d'import"
    
    echo ""
    echo "2. Test du health check (nécessite que l'app tourne)..."
    
    if command -v curl &> /dev/null; then
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            echo -e "   ${GREEN}✓${NC} Health check répond"
            curl -s http://localhost:8000/health | python3 -m json.tool
        else
            echo -e "   ${YELLOW}⊘${NC} L'app n'est pas démarrée (normal si pas encore redémarrée)"
        fi
    else
        echo -e "   ${YELLOW}⊘${NC} curl non disponible"
    fi
    
    echo ""
}

# Afficher le statut
show_status() {
    echo -e "${BLUE}📊 Statut de l'implémentation${NC}"
    echo ""
    
    # Vérifier les fichiers
    echo "Modules créés:"
    [ -f "app/core/http_client.py" ] && echo -e "  ${GREEN}✓${NC} http_client.py" || echo -e "  ${RED}✗${NC} http_client.py"
    [ -f "app/core/retry.py" ] && echo -e "  ${GREEN}✓${NC} retry.py" || echo -e "  ${RED}✗${NC} retry.py"
    [ -f "app/core/circuit_breaker.py" ] && echo -e "  ${GREEN}✓${NC} circuit_breaker.py" || echo -e "  ${RED}✗${NC} circuit_breaker.py"
    [ -f "app/core/cache.py" ] && echo -e "  ${GREEN}✓${NC} cache.py" || echo -e "  ${RED}✗${NC} cache.py"
    [ -f "app/api/routes_health.py" ] && echo -e "  ${GREEN}✓${NC} routes_health.py" || echo -e "  ${RED}✗${NC} routes_health.py"
    
    echo ""
    echo "Services:"
    [ -f "app/services/bot_service_improved.py" ] && echo -e "  ${GREEN}✓${NC} bot_service_improved.py créé" || echo -e "  ${RED}✗${NC} bot_service_improved.py manquant"
    
    # Vérifier si bot_service.py utilise la nouvelle version
    if [ -f "app/services/bot_service.py" ]; then
        if grep -q "Circuit breaker pour Gemini API" app/services/bot_service.py; then
            echo -e "  ${GREEN}✓${NC} bot_service.py (version améliorée active)"
        else
            echo -e "  ${YELLOW}⊘${NC} bot_service.py (ancienne version)"
        fi
    fi
    
    [ -f "app/services/bot_service_old.py" ] && echo -e "  ${GREEN}✓${NC} bot_service_old.py (backup)" || echo -e "  ${YELLOW}⊘${NC} Pas de backup"
    
    echo ""
    echo "Dépendances:"
    pip show tenacity > /dev/null 2>&1 && echo -e "  ${GREEN}✓${NC} tenacity" || echo -e "  ${RED}✗${NC} tenacity"
    pip show cachetools > /dev/null 2>&1 && echo -e "  ${GREEN}✓${NC} cachetools" || echo -e "  ${RED}✗${NC} cachetools"
    
    echo ""
}

# Rollback
rollback() {
    echo -e "${YELLOW}↶ Rollback${NC}"
    echo ""
    
    if [ ! -f "app/services/bot_service_old.py" ]; then
        echo -e "${RED}❌ Pas de backup trouvé (bot_service_old.py)${NC}"
        exit 1
    fi
    
    if confirm "Restaurer l'ancien bot_service.py ?"; then
        cp app/services/bot_service_old.py app/services/bot_service.py
        echo -e "${GREEN}✓${NC} Ancien bot_service.py restauré"
        echo ""
        echo "Redémarrez l'application:"
        echo "  docker-compose restart backend"
    else
        echo "Annulé."
    fi
    
    echo ""
}

# Menu principal
case "${1:-}" in
    --phase1)
        apply_phase1
        run_tests
        ;;
    --phase2)
        apply_phase2
        ;;
    --all)
        apply_phase1
        echo ""
        apply_phase2
        echo ""
        run_tests
        ;;
    --test)
        run_tests
        ;;
    --status)
        show_status
        ;;
    --rollback)
        rollback
        ;;
    --help|-h)
        echo "Usage: $0 [OPTION]"
        echo ""
        echo "Options:"
        echo "  --phase1      Appliquer les fixes urgents (15 min)"
        echo "  --phase2      Afficher les instructions pour Phase 2"
        echo "  --all         Appliquer Phase 1 et afficher Phase 2"
        echo "  --test        Tester les modules et health check"
        echo "  --status      Afficher le statut de l'implémentation"
        echo "  --rollback    Restaurer l'ancien bot_service.py"
        echo "  --help        Afficher cette aide"
        echo ""
        exit 0
        ;;
    *)
        echo "Mode interactif"
        echo ""
        
        PS3="Choisissez une action: "
        options=("Phase 1: Fixes urgents" "Phase 2: Améliorations" "Tests" "Statut" "Rollback" "Quitter")
        select opt in "${options[@]}"
        do
            case $opt in
                "Phase 1: Fixes urgents")
                    apply_phase1
                    run_tests
                    break
                    ;;
                "Phase 2: Améliorations")
                    apply_phase2
                    break
                    ;;
                "Tests")
                    run_tests
                    break
                    ;;
                "Statut")
                    show_status
                    break
                    ;;
                "Rollback")
                    rollback
                    break
                    ;;
                "Quitter")
                    break
                    ;;
                *) echo "Option invalide";;
            esac
        done
        ;;
esac

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Terminé !${NC}"
echo ""
echo "Prochaines étapes:"
echo "  1. Redémarrer l'application: docker-compose restart backend"
echo "  2. Vérifier les logs: docker-compose logs -f backend"
echo "  3. Tester le health check: curl http://localhost:8000/health"
echo "  4. Surveiller Grafana pour voir l'amélioration"
echo ""
echo "Documentation:"
echo "  - RESUME_SOLUTIONS.md         Résumé visuel"
echo "  - GUIDE_IMPLEMENTATION.md     Guide détaillé"
echo "  - ANALYSE_ERREURS_5XX.md      Analyse technique"
echo ""

