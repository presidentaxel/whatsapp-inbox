"""
Script pour tester l'endpoint webhook en production
Vérifie que l'endpoint est accessible et répond correctement
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
import httpx


async def test_webhook_verification():
    """Teste l'endpoint de vérification du webhook"""
    print("=" * 60)
    print("TEST DE L'ENDPOINT WEBHOOK")
    print("=" * 60)
    print()
    
    # URL de production depuis l'image
    webhook_url = "https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp"
    
    if not settings.WHATSAPP_VERIFY_TOKEN:
        print("❌ WHATSAPP_VERIFY_TOKEN non configuré dans .env")
        print("   Configurez-le avant de tester")
        return
    
    print(f"✅ Verify token configuré: {settings.WHATSAPP_VERIFY_TOKEN[:20]}...")
    print(f"🌐 URL du webhook: {webhook_url}")
    print()
    
    # Test 1: Vérification GET (comme Meta le fait)
    print("📋 Test 1: Vérification GET (comme Meta)")
    print("-" * 60)
    
    test_challenge = "test_challenge_12345"
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": settings.WHATSAPP_VERIFY_TOKEN,
        "hub.challenge": test_challenge
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(webhook_url, params=params)
            
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            
            if response.status_code == 200:
                if response.text == test_challenge:
                    print("✅ Vérification réussie! L'endpoint répond correctement.")
                else:
                    print(f"⚠️  L'endpoint répond mais le challenge ne correspond pas")
                    print(f"   Attendu: {test_challenge}")
                    print(f"   Reçu: {response.text}")
            elif response.status_code == 403:
                print("❌ Erreur 403: Le token de vérification ne correspond pas")
                print("   Vérifiez que WHATSAPP_VERIFY_TOKEN dans .env correspond au token dans Meta")
            else:
                print(f"❌ Erreur {response.status_code}: {response.text}")
                
    except httpx.ConnectError:
        print("❌ Impossible de se connecter à l'URL")
        print("   Vérifiez que:")
        print("   1. Le domaine est accessible publiquement")
        print("   2. Le backend est démarré")
        print("   3. L'URL est correcte")
    except httpx.TimeoutException:
        print("❌ Timeout: L'endpoint ne répond pas dans les temps")
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    
    # Test 2: Vérifier que l'endpoint POST existe
    print("📋 Test 2: Vérification POST (réception de messages)")
    print("-" * 60)
    
    test_payload = {
        "object": "whatsapp_business_account",
        "entry": []
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                webhook_url,
                json=test_payload,
                headers={"Content-Type": "application/json"}
            )
            
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            
            if response.status_code == 200:
                print("✅ L'endpoint POST fonctionne!")
            else:
                print(f"⚠️  Status {response.status_code}: {response.text}")
                
    except Exception as e:
        print(f"❌ Erreur: {e}")


async def check_webhook_subscriptions():
    """Vérifie les abonnements webhook via l'API Meta"""
    print()
    print("=" * 60)
    print("VÉRIFICATION DES ABONNEMENTS WEBHOOK")
    print("=" * 60)
    print()
    
    if not settings.WHATSAPP_TOKEN:
        print("⚠️  WHATSAPP_TOKEN non configuré")
        print("   Impossible de vérifier les abonnements via l'API")
        return
    
    # Essayer avec le WABA ID si disponible
    waba_id = settings.WHATSAPP_BUSINESS_ACCOUNT_ID
    
    if not waba_id:
        print("⚠️  WHATSAPP_BUSINESS_ACCOUNT_ID non configuré")
        print("   Impossible de vérifier les abonnements via l'API")
        print()
        print("   Vérification manuelle nécessaire:")
        print("   1. Allez dans Meta for Developers > Votre App > Webhooks")
        print("   2. Vérifiez que le webhook est 'Actif' (cercle vert)")
        print("   3. Cliquez sur 'S'abonner aux champs'")
        print("   4. Vérifiez que 'messages' et 'message_status' sont cochés")
        return
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Récupérer les abonnements via le WABA ID
            url = f"https://graph.facebook.com/v19.0/{waba_id}/subscribed_apps"
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"}
            )
            
            if response.is_error:
                print(f"⚠️  Erreur API: {response.status_code} - {response.text}")
                print()
                print("   Vérification manuelle nécessaire:")
                print("   1. Allez dans Meta for Developers > Votre App > Webhooks")
                print("   2. Vérifiez que le webhook est 'Actif' (cercle vert)")
                print("   3. Cliquez sur 'S'abonner aux champs'")
                print("   4. Vérifiez que 'messages' et 'message_status' sont cochés")
                return
            
            data = response.json()
            apps = data.get("data", [])
            
            if not apps:
                print("⚠️  Aucun abonnement webhook trouvé!")
                print("   Vous devez vous abonner aux événements dans Meta")
                print()
                print("   Pour s'abonner:")
                print("   1. Allez dans Meta > Webhooks > WhatsApp")
                print("   2. Cliquez sur 'S'abonner aux champs'")
                print("   3. Cochez 'messages' et 'message_status'")
                print("   4. Cliquez sur 'Enregistrer'")
            else:
                print(f"✅ {len(apps)} abonnement(s) trouvé(s)")
                for app in apps:
                    print(f"   - App ID: {app.get('id')}")
                    
    except Exception as e:
        print(f"⚠️  Erreur lors de la vérification: {e}")
        print()
        print("   Vérification manuelle nécessaire:")
        print("   1. Allez dans Meta for Developers > Votre App > Webhooks")
        print("   2. Vérifiez que le webhook est 'Actif' (cercle vert)")
        print("   3. Cliquez sur 'S'abonner aux champs'")
        print("   4. Vérifiez que 'messages' et 'message_status' sont cochés")


if __name__ == "__main__":
    asyncio.run(test_webhook_verification())
    asyncio.run(check_webhook_subscriptions())

