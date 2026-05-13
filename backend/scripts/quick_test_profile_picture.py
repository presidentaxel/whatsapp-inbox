"""
Script rapide pour tester la récupération d'images de profil
Trouve automatiquement un contact et un compte pour tester
Usage: python -m scripts.quick_test_profile_picture
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import supabase, supabase_execute
from app.services.account_service import get_all_accounts
from app.services.profile_picture_service import update_all_contacts_profile_pictures


async def quick_test():
    """Test rapide : met à jour les images de profil de quelques contacts"""
    
    print("🔍 Recherche d'un compte WhatsApp...")
    accounts = await get_all_accounts()
    
    if not accounts:
        print("❌ Aucun compte WhatsApp trouvé!")
        print("💡 Assurez-vous d'avoir configuré au moins un compte dans whatsapp_accounts")
        return
    
    account = accounts[0]
    account_id = account["id"]
    print(f"✅ Compte trouvé: {account.get('name')} (ID: {account_id})\n")
    
    print("🔍 Recherche de contacts...")
    contacts_res = await supabase_execute(
        supabase.table("contacts")
        .select("id, whatsapp_number, display_name, profile_picture_url")
        .limit(5)
    )
    
    if not contacts_res.data:
        print("❌ Aucun contact trouvé!")
        print("💡 Envoyez d'abord un message WhatsApp pour créer des contacts")
        return
    
    print(f"✅ {len(contacts_res.data)} contact(s) trouvé(s):\n")
    for contact in contacts_res.data:
        has_picture = "✅" if contact.get("profile_picture_url") else "❌"
        print(f"   {has_picture} {contact.get('display_name') or contact.get('whatsapp_number')} - {contact.get('whatsapp_number')}")
    
    print("\n🚀 Démarrage de la mise à jour des images de profil...")
    print("   (Limite: 5 contacts pour le test)\n")
    
    await update_all_contacts_profile_pictures(account_id, limit=5)
    
    print("⏳ Attente de 10 secondes pour que les mises à jour se terminent...")
    await asyncio.sleep(10)
    
    print("\n🔍 Vérification des résultats...")
    contacts_res = await supabase_execute(
        supabase.table("contacts")
        .select("id, whatsapp_number, display_name, profile_picture_url")
        .limit(5)
    )
    
    print("\n📊 Résultats:\n")
    for contact in contacts_res.data:
        has_picture = "✅" if contact.get("profile_picture_url") else "❌"
        picture_url = contact.get("profile_picture_url", "Aucune")
        if picture_url and len(picture_url) > 60:
            picture_url = picture_url[:60] + "..."
        print(f"   {has_picture} {contact.get('display_name') or contact.get('whatsapp_number')}")
        print(f"      Image: {picture_url}\n")
    
    print("✅ Test terminé!")
    print("\n💡 Note: WhatsApp Graph API a des limitations.")
    print("   Certaines images peuvent ne pas être disponibles selon les permissions.")


if __name__ == "__main__":
    asyncio.run(quick_test())



































