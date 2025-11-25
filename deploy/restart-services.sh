#!/bin/bash
# Script pour redémarrer les services avec la nouvelle configuration

echo "Arrêt des services..."
cd "$(dirname "$0")"
docker-compose -f docker-compose.prod.yml down

echo "Redémarrage des services..."
docker-compose -f docker-compose.prod.yml up -d

echo "Vérification du statut des services..."
docker-compose -f docker-compose.prod.yml ps

echo ""
echo "Grafana devrait maintenant être accessible via https://${DOMAIN}/grafana"
echo "Vérifiez les logs avec: docker-compose -f docker-compose.prod.yml logs caddy grafana"

