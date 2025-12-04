"""
Script pour trouver automatiquement l'URL du backend en testant différentes possibilités
"""

from __future__ import annotations

import httpx
import sys
from pathlib import Path

# Ajouter le répertoire backend au PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

# URLs possibles à tester
POSSIBLE_BACKEND_URLS = [
    "https://whatsapp-inbox-backend.onrender.com",
    "https://whatsapp-inbox-backend-1.onrender.com",
    "https://whatsapp-inbox-backend-2.onrender.com",
    "https://whatsapp-inbox-backend-3.onrender.com",
    "https://whatsapp.lamaisonduchauffeurvtc.fr",  # Peut-être que le backend est sur le même domaine
    "https://api.whatsapp.lamaisonduchauffeurvtc.fr",  # Sous-domaine API
    "https://backend.whatsapp.lamaisonduchauffeurvtc.fr",  # Sous-domaine backend
]


def test_url(url: str) -> tuple[bool, str]:
    """Teste si une URL est le backend en vérifiant /healthz"""
    try:
        response = httpx.get(f"{url}/healthz", timeout=5.0, follow_redirects=True)
        if response.status_code == 200:
            return True, response.text
        return False, f"Status {response.status_code}"
    except httpx.RequestError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)


def test_webhook_endpoint(url: str) -> tuple[bool, str]:
    """Teste si l'endpoint webhook existe"""
    try:
        # Test avec un token invalide pour voir si l'endpoint existe
        response = httpx.get(
            f"{url}/webhook/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "test",
                "hub.challenge": "test"
            },
            timeout=5.0,
            follow_redirects=True
        )
        # Si on a 403, c'est que l'endpoint existe (token invalide)
        # Si on a 404, l'endpoint n'existe pas
        if response.status_code in [200, 403]:
            return True, f"Endpoint exists (status {response.status_code})"
        return False, f"Status {response.status_code}"
    except Exception as e:
        return False, str(e)


def main():
    print("="*80)
    print("RECHERCHE AUTOMATIQUE DE L'URL DU BACKEND")
    print("="*80)
    print()
    print("Test des URLs possibles...")
    print()
    
    found_backend = None
    
    for url in POSSIBLE_BACKEND_URLS:
        print(f"Test de: {url}")
        
        # Test 1: Health check
        health_ok, health_msg = test_url(url)
        if health_ok:
            print(f"  ✅ Health check OK: {health_msg[:100]}")
            
            # Test 2: Webhook endpoint
            webhook_ok, webhook_msg = test_webhook_endpoint(url)
            if webhook_ok:
                print(f"  ✅ Webhook endpoint trouvé: {webhook_msg}")
                found_backend = url
                break
            else:
                print(f"  ⚠️ Health OK mais webhook: {webhook_msg}")
        else:
            print(f"  ❌ Health check échoué: {health_msg[:100]}")
        print()
    
    print("="*80)
    if found_backend:
        print(f"✅ BACKEND TROUVÉ: {found_backend}")
        print("="*80)
        print()
        print("Endpoints disponibles:")
        print(f"  - Health: {found_backend}/healthz")
        print(f"  - Webhook: {found_backend}/webhook/whatsapp")
        print(f"  - Debug: {found_backend}/webhook/whatsapp/debug (POST)")
        print(f"  - Metrics: {found_backend}/metrics")
        print()
        print("Pour tester le webhook debug (POST):")
        print(f"  curl -X POST {found_backend}/webhook/whatsapp/debug \\")
        print("    -H 'Content-Type: application/json' \\")
        print("    -d '{\"field\":\"messages\",\"value\":{...}}'")
    else:
        print("❌ AUCUN BACKEND TROUVÉ")
        print("="*80)
        print()
        print("Le backend n'a pas été trouvé automatiquement.")
        print("Vérifiez manuellement dans Render Dashboard:")
        print("  1. https://dashboard.render.com")
        print("  2. Service 'whatsapp-inbox-backend'")
        print("  3. L'URL est affichée en haut de la page")
        print()
        print("Ou vérifiez la variable VITE_BACKEND_URL dans le frontend:")
        print("  Render Dashboard → whatsapp-inbox-frontend → Environment")
    
    print("="*80)


if __name__ == "__main__":
    main()

