"""
Script pour vérifier le statut du webhook WhatsApp
Vérifie si le webhook est configuré et accessible
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.core.http_client import get_http_client
async def check_webhook_subscriptions():
    """Vérifie les abonnements webhook dans Meta"""
    print("=" * 60)
    print("VÉRIFICATION DES WEBHOOKS WHATSAPP")
    print("=" * 60)
    print()
    
    if not settings.WHATSAPP_TOKEN or not settings.WHATSAPP_PHONE_ID:
        print("❌ WHATSAPP_TOKEN ou WHATSAPP_PHONE_ID non configuré")
        return
    
    print(f"✅ Token configuré: {settings.WHATSAPP_TOKEN[:20]}...")
    print(f"✅ Phone ID configuré: {settings.WHATSAPP_PHONE_ID}")
    print()
    
    try:
        # Récupérer les abonnements webhook
        print("🔍 Vérification des abonnements webhook...")
        client = await get_http_client()
        
        # Utiliser l'API Graph pour récupérer les webhooks
        url = f"https://graph.facebook.com/v19.0/{settings.WHATSAPP_PHONE_ID}/subscribed_apps"
        response = await client.get(
            url,
            headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"}
        )
        
        if response.is_error:
            print(f"❌ Erreur API: {response.status_code} - {response.text}")
            return
        
        data = response.json()
        apps = data.get("data", [])
        
        if not apps:
            print("⚠️  Aucun abonnement webhook trouvé!")
            print("   Le webhook n'est probablement pas configuré dans Meta.")
            print()
            print("   Pour configurer le webhook:")
            print("   1. Allez dans Meta Business Suite > Webhooks")
            print("   2. Configurez l'URL: https://votre-domaine/webhook/whatsapp")
            print("   3. Utilisez le verify_token depuis .env (WHATSAPP_VERIFY_TOKEN)")
            return
        
        print(f"✅ {len(apps)} abonnement(s) webhook trouvé(s):")
        for app in apps:
            print(f"   - App ID: {app.get('id')}")
        
        # Vérifier les champs webhook
        print()
        print("🔍 Vérification des champs webhook...")
        webhook_url = f"https://graph.facebook.com/v19.0/{settings.WHATSAPP_PHONE_ID}"
        response = await client.get(
            webhook_url,
            headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
            params={"fields": "webhook_uri"}
        )
        
        if response.is_success:
            webhook_data = response.json()
            webhook_uri = webhook_data.get("webhook_uri")
            if webhook_uri:
                print(f"✅ Webhook URI configuré: {webhook_uri}")
            else:
                print("⚠️  Webhook URI non configuré")
        else:
            print(f"⚠️  Impossible de récupérer les infos webhook: {response.status_code}")
        
    except Exception as e:
        print(f"❌ Erreur lors de la vérification: {e}")
        import traceback
        traceback.print_exc()


async def check_webhook_endpoint():
    """Vérifie que l'endpoint webhook est accessible"""
    print()
    print("=" * 60)
    print("VÉRIFICATION DE L'ENDPOINT WEBHOOK")
    print("=" * 60)
    print()
    
    # Vérifier le verify_token
    if settings.WHATSAPP_VERIFY_TOKEN:
        print(f"✅ Verify token configuré: {settings.WHATSAPP_VERIFY_TOKEN[:20]}...")
    else:
        print("⚠️  WHATSAPP_VERIFY_TOKEN non configuré")
    
    print()
    print("📋 Pour tester le webhook:")
    print("   1. Vérifiez que votre backend est accessible publiquement")
    print("   2. Utilisez ngrok en local: powershell scripts/start_webhook.ps1")
    print("   3. L'URL doit être: https://votre-url/webhook/whatsapp")
    print("   4. Testez avec: curl -X GET 'https://votre-url/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=VOTRE_TOKEN&hub.challenge=test'")


if __name__ == "__main__":
    asyncio.run(check_webhook_subscriptions())
    asyncio.run(check_webhook_endpoint())

