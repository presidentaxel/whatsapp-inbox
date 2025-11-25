# Script PowerShell pour redémarrer les services avec la nouvelle configuration

Write-Host "Arrêt des services..." -ForegroundColor Yellow
Push-Location $PSScriptRoot

docker-compose -f docker-compose.prod.yml down

Write-Host "Redémarrage des services..." -ForegroundColor Yellow
docker-compose -f docker-compose.prod.yml up -d

Write-Host "Vérification du statut des services..." -ForegroundColor Yellow
docker-compose -f docker-compose.prod.yml ps

Write-Host ""
Write-Host "Grafana devrait maintenant être accessible via https://`$env:DOMAIN/grafana" -ForegroundColor Green
Write-Host "Vérifiez les logs avec: docker-compose -f docker-compose.prod.yml logs caddy grafana" -ForegroundColor Cyan

Pop-Location

