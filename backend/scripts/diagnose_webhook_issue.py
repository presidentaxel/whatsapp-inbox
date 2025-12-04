"""
Script de diagnostic pour identifier pourquoi les messages ne sont plus reçus
"""
import asyncio
import json
import sys
from pathlib import Path

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.db import supabase, supabase_execute
from app.core.config import settings
from app.services.account_service import get_account_by_phone_number_id, get_all_accounts


async def check_accounts():
    """Vérifie tous les comptes dans la base de données"""
    print("=" * 60)
    print("📋 COMPTES DANS LA BASE DE DONNÉES")
    print("=" * 60)
    
    accounts = await get_all_accounts()
    
    if not accounts:
        print("❌ Aucun compte trouvé dans la base de données!")
        print("\n💡 Vérifiez que:")
        print("   1. Les variables d'environnement sont configurées (WHATSAPP_PHONE_ID, etc.)")
        print("   2. Le compte par défaut a été créé automatiquement")
        return
    
    print(f"\n✅ {len(accounts)} compte(s) trouvé(s):\n")
    
    for account in accounts:
        print(f"📱 Compte: {account.get('name', 'N/A')}")
        print(f"   ID: {account.get('id')}")
        print(f"   Slug: {account.get('slug')}")
        print(f"   Phone Number: {account.get('phone_number', 'N/A')}")
        print(f"   Phone Number ID: {account.get('phone_number_id', '❌ MANQUANT')}")
        print(f"   Is Active: {account.get('is_active', False)}")
        print()
    
    return accounts


async def check_webhook_structure():
    """Affiche la structure attendue d'un webhook"""
    print("=" * 60)
    print("📥 STRUCTURE ATTENDUE DU WEBHOOK")
    print("=" * 60)
    
    example_webhook = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "+33612345678",
                        "phone_number_id": "123456789012345"  # ← C'est ce qui est recherché
                    },
                    "contacts": [{
                        "wa_id": "33783614530",
                        "profile": {
                            "name": "John Doe"
                        }
                    }],
                    "messages": [{
                        "from": "33783614530",
                        "id": "wamid.xxx",
                        "timestamp": "1234567890",
                        "type": "text",
                        "text": {
                            "body": "Hello"
                        }
                    }]
                },
                "field": "messages"
            }]
        }]
    }
    
    print("\n📝 Exemple de webhook valide:\n")
    print(json.dumps(example_webhook, indent=2))
    print("\n💡 Le phone_number_id doit être dans: entry[].changes[].value.metadata.phone_number_id")
    print()


async def test_phone_number_id_lookup(phone_number_id: str = None):
    """Teste la recherche d'un compte par phone_number_id"""
    print("=" * 60)
    print("🔍 TEST DE RECHERCHE PAR PHONE_NUMBER_ID")
    print("=" * 60)
    
    if not phone_number_id:
        # Récupérer le premier phone_number_id de la base
        accounts = await get_all_accounts()
        if accounts and accounts[0].get("phone_number_id"):
            phone_number_id = accounts[0]["phone_number_id"]
            print(f"\n📱 Utilisation du phone_number_id du premier compte: {phone_number_id}")
        else:
            print("\n❌ Aucun phone_number_id disponible pour le test")
            print("   Fournissez un phone_number_id en argument ou configurez un compte")
            return
    
    print(f"\n🔍 Recherche du compte avec phone_number_id: {phone_number_id}")
    
    account = await get_account_by_phone_number_id(phone_number_id)
    
    if account:
        print(f"✅ Compte trouvé!")
        print(f"   ID: {account.get('id')}")
        print(f"   Name: {account.get('name')}")
        print(f"   Phone Number ID: {account.get('phone_number_id')}")
    else:
        print(f"❌ Aucun compte trouvé avec ce phone_number_id!")
        print("\n💡 Vérifiez que:")
        print("   1. Le phone_number_id dans la base correspond à celui du webhook")
        print("   2. Le compte est actif (is_active = true)")
        print("   3. Le phone_number_id n'a pas changé dans Meta Business")


async def check_env_vars():
    """Vérifie les variables d'environnement"""
    print("=" * 60)
    print("🔧 VARIABLES D'ENVIRONNEMENT")
    print("=" * 60)
    
    vars_to_check = [
        "WHATSAPP_PHONE_ID",
        "WHATSAPP_TOKEN",
        "WHATSAPP_VERIFY_TOKEN",
        "WHATSAPP_PHONE_NUMBER",
    ]
    
    print()
    for var in vars_to_check:
        value = getattr(settings, var, None)
        if value:
            # Masquer les tokens sensibles
            if "TOKEN" in var or "TOKEN" in var:
                display_value = f"{value[:10]}..." if len(value) > 10 else "***"
            else:
                display_value = value
            print(f"✅ {var}: {display_value}")
        else:
            print(f"❌ {var}: Non défini")
    
    print()


async def main():
    """Fonction principale"""
    print("\n" + "=" * 60)
    print("🔍 DIAGNOSTIC DU PROBLÈME DE RÉCEPTION DES MESSAGES")
    print("=" * 60 + "\n")
    
    # 1. Vérifier les variables d'environnement
    await check_env_vars()
    
    # 2. Vérifier les comptes dans la base
    accounts = await check_accounts()
    
    # 3. Tester la recherche par phone_number_id
    if accounts:
        phone_number_id = accounts[0].get("phone_number_id") if accounts else None
        await test_phone_number_id_lookup(phone_number_id)
    
    # 4. Afficher la structure attendue
    await check_webhook_structure()
    
    # 5. Recommandations
    print("=" * 60)
    print("💡 RECOMMANDATIONS")
    print("=" * 60)
    print("\n1. Vérifiez les logs du serveur pour voir les erreurs:")
    print("   - Cherchez les messages avec '❌ Unknown account for phone_number_id'")
    print("   - Vérifiez que le phone_number_id dans les logs correspond à celui en base")
    print()
    print("2. Vérifiez la configuration du webhook dans Meta:")
    print("   - Le webhook doit pointer vers: https://votre-domaine.com/webhook/whatsapp")
    print("   - Le verify_token doit correspondre")
    print()
    print("3. Testez le webhook manuellement:")
    print("   - Utilisez l'outil de test de Meta Business")
    print("   - Vérifiez que les webhooks arrivent bien (logs du serveur)")
    print()
    print("4. Si le phone_number_id a changé:")
    print("   - Mettez à jour le phone_number_id dans la table whatsapp_accounts")
    print("   - Ou recréez le compte avec le bon phone_number_id")
    print()


if __name__ == "__main__":
    asyncio.run(main())

