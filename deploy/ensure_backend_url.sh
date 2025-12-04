#!/bin/bash
# Script pour s'assurer que BACKEND_URL est toujours défini
# À exécuter avant chaque déploiement

ENV_FILE=".env"
[ ! -f "$ENV_FILE" ] && ENV_FILE="../.env"

if [ -f "$ENV_FILE" ]; then
    if ! grep -q "^BACKEND_URL=" "$ENV_FILE"; then
        echo "BACKEND_URL=backend:8000" >> "$ENV_FILE"
        echo "✅ BACKEND_URL ajouté"
    else
        # S'assurer que la valeur est correcte pour OVH
        sed -i 's|^BACKEND_URL=.*|BACKEND_URL=backend:8000|' "$ENV_FILE"
        echo "✅ BACKEND_URL vérifié"
    fi
else
    echo "BACKEND_URL=backend:8000" > "$ENV_FILE"
    echo "✅ .env créé avec BACKEND_URL"
fi

