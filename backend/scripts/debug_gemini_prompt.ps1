# Script PowerShell pour debugger le prompt Gemini
# Usage: .\scripts\debug_gemini_prompt.ps1 <conversation_id>

param(
    [Parameter(Mandatory=$true)]
    [string]$ConversationId
)

Write-Host "🔍 Exécution du script de debug Gemini..." -ForegroundColor Cyan
Write-Host ""

# Aller dans le répertoire backend
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPath = Split-Path -Parent $scriptPath
Set-Location $backendPath

# Exécuter le script Python
python scripts/debug_gemini_prompt.py $ConversationId

