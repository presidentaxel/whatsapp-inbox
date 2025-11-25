# Script pour créer le fichier .env dans le dossier deploy
# Ce script extrait le domaine depuis VITE_BACKEND_URL si disponible

param(
    [string]$Domain = "",
    [string]$Email = ""
)

$envFile = Join-Path $PSScriptRoot ".env"

if (Test-Path $envFile) {
    Write-Host "Le fichier .env existe déjà." -ForegroundColor Yellow
    $response = Read-Host "Voulez-vous le remplacer ? (o/N)"
    if ($response -ne "o" -and $response -ne "O") {
        Write-Host "Annulé." -ForegroundColor Red
        exit 0
    }
}

# Essayer d'extraire le domaine depuis le fichier .env du frontend
if ([string]::IsNullOrWhiteSpace($Domain)) {
    $frontendEnv = Join-Path $PSScriptRoot "..\frontend\.env"
    if (Test-Path $frontendEnv) {
        $content = Get-Content $frontendEnv -Raw
        if ($content -match "VITE_BACKEND_URL=https?://([^/]+)") {
            $Domain = $matches[1]
            Write-Host "Domaine détecté depuis frontend/.env : $Domain" -ForegroundColor Green
        }
    }
}

# Si toujours pas de domaine, demander à l'utilisateur
if ([string]::IsNullOrWhiteSpace($Domain)) {
    $Domain = Read-Host "Entrez votre domaine (ex: whatsapp.lamaisonduchauffeurvtc.fr)"
}

# Demander l'email si non fourni
if ([string]::IsNullOrWhiteSpace($Email)) {
    $Email = Read-Host "Entrez votre adresse email pour Let's Encrypt"
}

# Créer le fichier .env
@"
# Variables d'environnement pour docker-compose.prod.yml
# Généré automatiquement par setup-env.ps1

# Domaine de votre application (sans https://)
DOMAIN=$Domain

# Email pour les certificats SSL Let's Encrypt (Caddy)
EMAIL=$Email
"@ | Out-File -FilePath $envFile -Encoding UTF8

Write-Host ""
Write-Host "Fichier .env créé avec succès dans deploy/.env" -ForegroundColor Green
Write-Host ""
Write-Host "Contenu :" -ForegroundColor Cyan
Write-Host "  DOMAIN=$Domain"
Write-Host "  EMAIL=$Email"
Write-Host ""
Write-Host "Vous pouvez maintenant redémarrer les services avec :" -ForegroundColor Yellow
Write-Host "  docker-compose -f docker-compose.prod.yml down" -ForegroundColor White
Write-Host "  docker-compose -f docker-compose.prod.yml up -d" -ForegroundColor White

