#!/bin/bash
# Script pour trouver le projet et lancer le diagnostic

echo "Recherche du projet WhatsApp Inbox..."
echo ""

# Chercher dans les emplacements courants
SEARCH_PATHS=(
    "$HOME"
    "$HOME/projects"
    "$HOME/apps"
    "/opt"
    "/var/www"
    "/home/ubuntu"
    "/root"
)

FOUND=false

for path in "${SEARCH_PATHS[@]}"; do
    if [ -d "$path/whatsapp-inbox" ]; then
        echo "✅ Projet trouvé dans: $path/whatsapp-inbox"
        cd "$path/whatsapp-inbox" || exit
        FOUND=true
        break
    fi
done

# Si pas trouvé, chercher récursivement (limité à 2 niveaux)
if [ "$FOUND" = false ]; then
    echo "Recherche dans $HOME..."
    FOUND_PATH=$(find "$HOME" -maxdepth 3 -type d -name "whatsapp-inbox" 2>/dev/null | head -1)
    if [ -n "$FOUND_PATH" ]; then
        echo "✅ Projet trouvé dans: $FOUND_PATH"
        cd "$FOUND_PATH" || exit
        FOUND=true
    fi
fi

# Si toujours pas trouvé, chercher le dossier deploy
if [ "$FOUND" = false ]; then
    echo "Recherche du dossier 'deploy'..."
    FOUND_PATH=$(find "$HOME" -maxdepth 4 -type d -name "deploy" 2>/dev/null | head -1)
    if [ -n "$FOUND_PATH" ]; then
        echo "✅ Dossier deploy trouvé dans: $FOUND_PATH"
        cd "$(dirname "$FOUND_PATH")" || exit
        FOUND=true
    fi
fi

if [ "$FOUND" = false ]; then
    echo "❌ Projet non trouvé automatiquement"
    echo ""
    echo "Où se trouve votre projet ?"
    echo "  - Dans quel dossier avez-vous cloné le repo GitHub ?"
    echo "  - Ou où avez-vous déployé l'application ?"
    echo ""
    echo "Vous pouvez aussi lancer manuellement :"
    echo "  cd /chemin/vers/votre/projet"
    echo "  cd deploy"
    echo "  ./diagnose_ovh_webhook.sh"
    exit 1
fi

echo ""
echo "Répertoire actuel: $(pwd)"
echo ""

# Vérifier que le dossier deploy existe
if [ ! -d "deploy" ]; then
    echo "❌ Dossier 'deploy' non trouvé dans $(pwd)"
    echo ""
    echo "Structure du répertoire actuel:"
    ls -la
    exit 1
fi

echo "✅ Dossier deploy trouvé"
echo ""
echo "Lancement du diagnostic..."
echo ""

cd deploy || exit

if [ -f "diagnose_ovh_webhook.sh" ]; then
    chmod +x diagnose_ovh_webhook.sh
    ./diagnose_ovh_webhook.sh
else
    echo "❌ Script de diagnostic non trouvé"
    echo ""
    echo "Fichiers dans deploy/:"
    ls -la
    echo ""
    echo "Le script doit être créé. Vérifiez que vous avez bien fait git pull."
fi

