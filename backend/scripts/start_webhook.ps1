Param(
    [switch]$ForceToken,
    [int]$Port = 8000,
    [string]$NgrokCommand = "ngrok"
)

$ErrorActionPreference = "Stop"

function Start-NgrokTunnel {
    Param([int]$Port, [string]$NgrokCommand)

    Write-Host "Starting ngrok tunnel on port $Port..."
    Start-Process -FilePath $NgrokCommand -ArgumentList "http $Port" -WindowStyle Minimized | Out-Null
    Start-Sleep -Seconds 3

    $retry = 0
    while ($retry -lt 10) {
        try {
            $resp = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2
            $httpsTunnel = $resp.tunnels | Where-Object { $_.proto -eq "https" }
            if ($httpsTunnel) {
                return $httpsTunnel.public_url
            }
        } catch {
            Start-Sleep -Seconds 1
            $retry++
        }
    }

    throw "Unable to retrieve ngrok public URL. Is ngrok running and accessible on port 4040?"
}

function Ensure-VerifyToken {
    Param([switch]$ForceToken)

    $python = "python"
    $scriptPath = Join-Path $PSScriptRoot "generate_verify_token.py"
    $args = @()
    if ($ForceToken) { $args += "--force" }

    $result = & $python $scriptPath @args
    if ($LASTEXITCODE -ne 0) {
        throw "Token generation script failed."
    }

    foreach ($line in ($result -split "`n")) {
        if ($line -match "^TOKEN=(.+)$") {
            return $Matches[1]
        }
    }

    throw "Could not read token value from script output."
}

$publicUrl = Start-NgrokTunnel -Port $Port -NgrokCommand $NgrokCommand
$tokenValue = Ensure-VerifyToken -ForceToken:$ForceToken

Write-Host ""
Write-Host "================ Ready to verify webhook ================"
Write-Host ("Webhook URL     : {0}/webhook/whatsapp" -f $publicUrl)
Write-Host ("Verify token    : {0}" -f $tokenValue)
Write-Host ""
Write-Host "1. Ouvre Meta > Webhooks > WhatsApp > Configurer."
Write-Host "2. Colle l'URL et le token ci-dessus, clique 'Vérifier et enregistrer'."
Write-Host "3. Utilise 'Envoyer un test' pour vérifier la réception."
Write-Host "=========================================================="

