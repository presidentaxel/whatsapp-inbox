"""
Script pour créer un compte de test avec le phone_number_id utilisé par Meta
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.db import supabase, supabase_execute
from app.core.config import settings

# Le phone_number_id utilisé par Meta dans les tests
META_TEST_PHONE_NUMBER_ID = "123456123"


async def create_test_account():
    """Crée un compte de test avec le phone_number_id de Meta"""
    print("=" * 80)
    print("CRÉATION D'UN COMPTE DE TEST POUR META")
    print("=" * 80)
    print()
    
    # Vérifier si le compte existe déjà
    existing = await supabase_execute(
        supabase.table("whatsapp_accounts")
        .select("*")
        .eq("phone_number_id", META_TEST_PHONE_NUMBER_ID)
        .limit(1)
    )
    
    if existing.data:
        print(f"✅ Un compte avec phone_number_id={META_TEST_PHONE_NUMBER_ID} existe déjà:")
        account = existing.data[0]
        print(f"   Nom: {account.get('name')}")
        print(f"   ID: {account.get('id')}")
        print(f"   Actif: {account.get('is_active')}")
        print()
        print("Pas besoin de créer un nouveau compte.")
        return account
    
    # Créer le compte de test
    print(f"📝 Création d'un compte de test avec phone_number_id={META_TEST_PHONE_NUMBER_ID}...")
    print()
    print("⚠️  NOTE: Ce compte est uniquement pour les tests Meta.")
    print("   Il utilisera les tokens de votre compte par défaut.")
    print()
    
    # Utiliser les tokens du compte par défaut
    verify_token = settings.WHATSAPP_VERIFY_TOKEN
    access_token = settings.WHATSAPP_TOKEN
    
    if not verify_token or not access_token:
        print("❌ Erreur: WHATSAPP_VERIFY_TOKEN ou WHATSAPP_TOKEN non configuré")
        return None
    
    account_data = {
        "name": "Compte Test Meta",
        "slug": "meta-test-account",
        "phone_number_id": META_TEST_PHONE_NUMBER_ID,
        "phone_number": "+1 (555) 123-4567",  # Numéro fictif
        "access_token": access_token,
        "verify_token": verify_token,
        "is_active": True,
    }
    
    result = await supabase_execute(
        supabase.table("whatsapp_accounts").insert(account_data)
    )
    
    if result.data:
        account = result.data[0]
        print(f"✅ Compte créé avec succès!")
        print(f"   Nom: {account.get('name')}")
        print(f"   ID: {account.get('id')}")
        print(f"   phone_number_id: {account.get('phone_number_id')}")
        print()
        print("Vous pouvez maintenant tester les webhooks depuis Meta!")
        return account
    else:
        print("❌ Erreur lors de la création du compte")
        return None


if __name__ == "__main__":
    asyncio.run(create_test_account())

