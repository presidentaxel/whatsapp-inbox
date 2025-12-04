"""
Script pour tester le backend en production et vérifier son état
"""

from __future__ import annotations

import httpx
import sys
from pathlib import Path

# Ajouter le répertoire backend au PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

# IMPORTANT: Remplacez cette URL par l'URL réelle du backend trouvée dans Render Dashboard
# L'URL du backend est différente de l'URL du frontend
# Exemple: https://whatsapp-inbox-backend-xxxx.onrender.com
PRODUCTION_URL = "https://whatsapp.lamaisonduchauffeurvtc.fr"  # ⚠️ À MODIFIER


def test_health_check():
    """Teste l'endpoint de health check"""
    print("="*80)
    print("TEST 1: Health Check")
    print("="*80)
    
    try:
        response = httpx.get(f"{PRODUCTION_URL}/healthz", timeout=10.0)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Backend est en ligne et fonctionne")
            return True
        else:
            print(f"⚠️ Backend répond mais avec un status {response.status_code}")
            return False
    except httpx.RequestError as e:
        print(f"❌ Erreur de connexion: {e}")
        print("   Le backend n'est peut-être pas accessible")
        return False


def test_webhook_verification():
    """Teste l'endpoint de vérification du webhook"""
    print("\n" + "="*80)
    print("TEST 2: Webhook Verification (GET)")
    print("="*80)
    
    # Lire le token depuis le .env local
    from dotenv import load_dotenv
    import os
    
    env_path = ROOT_DIR / ".env"
    load_dotenv(env_path)
    token = os.getenv("WHATSAPP_VERIFY_TOKEN")
    
    if not token:
        print("⚠️ Token non trouvé dans .env local")
        print("   Utilisez un token de test")
        token = "test_token"
    
    challenge = "production_test_12345"
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": token,
        "hub.challenge": challenge
    }
    
    try:
        response = httpx.get(
            f"{PRODUCTION_URL}/webhook/whatsapp",
            params=params,
            timeout=10.0
        )
        
        print(f"URL: {PRODUCTION_URL}/webhook/whatsapp")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200 and response.text == challenge:
            print("✅ Vérification du webhook fonctionne")
            return True
        else:
            print("⚠️ Vérification échouée")
            print(f"   Attendu: status 200 avec challenge '{challenge}'")
            print(f"   Reçu: status {response.status_code} avec '{response.text}'")
            return False
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return False


def test_webhook_reception():
    """Teste l'endpoint de réception du webhook"""
    print("\n" + "="*80)
    print("TEST 3: Webhook Reception (POST)")
    print("="*80)
    
    # Format simplifié pour test
    payload = {
        "field": "messages",
        "value": {
            "messaging_product": "whatsapp",
            "metadata": {
                "display_phone_number": "16505551111",
                "phone_number_id": "833058836557484"  # Compte TEST
            },
            "contacts": [
                {
                    "profile": {"name": "test user"},
                    "wa_id": "16315551181"
                }
            ],
            "messages": [
                {
                    "from": "16315551181",
                    "id": "PROD_TEST_123",
                    "timestamp": "1504902988",
                    "type": "text",
                    "text": {"body": "test from production script"}
                }
            ]
        }
    }
    
    try:
        response = httpx.post(
            f"{PRODUCTION_URL}/webhook/whatsapp",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10.0
        )
        
        print(f"URL: {PRODUCTION_URL}/webhook/whatsapp")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Réception du webhook fonctionne")
            print("   Vérifiez les logs dans Render pour voir le traitement")
            return True
        else:
            print(f"⚠️ Réception échouée: status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return False


def test_metrics():
    """Teste l'endpoint de métriques Prometheus"""
    print("\n" + "="*80)
    print("TEST 4: Prometheus Metrics")
    print("="*80)
    
    try:
        response = httpx.get(f"{PRODUCTION_URL}/metrics", timeout=10.0)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            lines = response.text.split('\n')
            print(f"✅ Métriques disponibles ({len(lines)} lignes)")
            print("   Premières lignes:")
            for line in lines[:10]:
                if line.strip():
                    print(f"   {line}")
            return True
        else:
            print(f"⚠️ Métriques non disponibles: status {response.status_code}")
            return False
    except Exception as e:
        print(f"⚠️ Métriques non disponibles: {e}")
        return False


def main():
    print("="*80)
    print("TEST DU BACKEND EN PRODUCTION")
    print("="*80)
    print(f"URL: {PRODUCTION_URL}\n")
    
    results = {
        "Health Check": test_health_check(),
        "Webhook Verification": test_webhook_verification(),
        "Webhook Reception": test_webhook_reception(),
        "Metrics": test_metrics(),
    }
    
    print("\n" + "="*80)
    print("RÉSUMÉ")
    print("="*80)
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name}: {status}")
    
    print("\n" + "="*80)
    print("PROCHAINES ÉTAPES")
    print("="*80)
    print("1. Vérifiez les logs dans Render Dashboard → Logs")
    print("2. Si des tests échouent, vérifiez les variables d'environnement")
    print("3. Redémarrez le service si nécessaire")
    print("="*80)


if __name__ == "__main__":
    main()

