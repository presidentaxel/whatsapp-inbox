"""
Script pour activer les webhooks WhatsApp automatiquement
Utilise l'API Meta pour s'abonner aux événements
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.core.db import supabase_execute, supabase
from app.services import whatsapp_api_service


async def activate_webhooks_for_all_accounts():
    """Active les webhooks pour tous les comptes WhatsApp"""
    print("=" * 60)
    print("ACTIVATION DES WEBHOOKS WHATSAPP")
    print("=" * 60)
    print()
    
    if not settings.WHATSAPP_TOKEN:
        print("❌ WHATSAPP_TOKEN non configuré")
        return
    
    # Récupérer tous les comptes
    result = await supabase_execute(
        supabase.table("whatsapp_accounts").select("*")
    )
    
    accounts = result.data or []
    
    if not accounts:
        print("⚠️  Aucun compte WhatsApp trouvé dans la base")
        print("   Utilisation de la configuration par défaut depuis .env")
        
        waba_id = settings.WHATSAPP_BUSINESS_ACCOUNT_ID
        if not waba_id:
            print("❌ WHATSAPP_BUSINESS_ACCOUNT_ID non configuré")
            print("   Configurez-le dans votre .env pour activer les webhooks")
            return
        
        print(f"✅ WABA ID trouvé: {waba_id}")
        print(f"🌐 Webhook URL: https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp")
        print()
        
        try:
            result = await whatsapp_api_service.subscribe_to_webhooks(
                waba_id=waba_id,
                access_token=settings.WHATSAPP_TOKEN
            )
            print("✅ Webhooks activés avec succès!")
            print(f"   Résultat: {result}")
        except Exception as e:
            print(f"❌ Erreur lors de l'activation: {e}")
            import traceback
            traceback.print_exc()
        
        return
    
    print(f"📋 {len(accounts)} compte(s) trouvé(s)")
    print()
    
    for account in accounts:
        account_id = account.get("id")
        account_name = account.get("name", "Sans nom")
        waba_id = account.get("waba_id") or settings.WHATSAPP_BUSINESS_ACCOUNT_ID
        access_token = account.get("access_token") or settings.WHATSAPP_TOKEN
        
        print(f"📱 Compte: {account_name} ({account_id})")
        
        if not waba_id:
            print(f"   ⚠️  WABA ID non configuré, utilisation de la valeur par défaut")
            waba_id = settings.WHATSAPP_BUSINESS_ACCOUNT_ID
        
        if not waba_id:
            print(f"   ❌ WABA ID non disponible, skip")
            continue
        
        if not access_token:
            print(f"   ❌ Access token non disponible, skip")
            continue
        
        print(f"   🔍 WABA ID: {waba_id}")
        print(f"   🌐 Webhook URL: https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp")
        
        try:
            result = await whatsapp_api_service.subscribe_to_webhooks(
                waba_id=waba_id,
                access_token=access_token
            )
            print(f"   ✅ Webhooks activés avec succès!")
            print(f"   📊 Résultat: {result}")
        except Exception as e:
            print(f"   ❌ Erreur: {e}")
        
        print()


if __name__ == "__main__":
    asyncio.run(activate_webhooks_for_all_accounts())

