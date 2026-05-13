"""
Script pour tester la récupération d'une image de profil
Usage: python -m scripts.test_profile_picture <contact_id> <account_id>
"""
import asyncio
import sys
import os

# Ajouter le chemin du projet
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.account_service import get_account_by_id
from app.core.db import supabase, supabase_execute
from app.services import whatsapp_api_service


async def test_profile_picture(contact_id: str, account_id: str):
    """Teste la récupération de l'image de profil d'un contact"""
    
    print(f"🔍 Testing profile picture for contact: {contact_id}")
    print(f"📱 Using account: {account_id}\n")
    
    # 1. Récupérer le contact
    print("1️⃣ Fetching contact...")
    contact_res = await supabase_execute(
        supabase.table("contacts")
        .select("*")
        .eq("id", contact_id)
        .limit(1)
    )
    
    if not contact_res.data:
        print("❌ Contact not found!")
        return
    
    contact = contact_res.data[0]
    whatsapp_number = contact.get("whatsapp_number")
    current_picture = contact.get("profile_picture_url")
    
    print(f"   ✅ Contact found: {contact.get('display_name') or whatsapp_number}")
    print(f"   📞 WhatsApp number: {whatsapp_number}")
    print(f"   🖼️  Current profile picture: {current_picture or 'None'}\n")
    
    # 2. Récupérer le compte
    print("2️⃣ Fetching account...")
    account = await get_account_by_id(account_id)
    if not account:
        print("❌ Account not found!")
        return
    
    phone_number_id = account.get("phone_number_id")
    access_token = account.get("access_token")
    
    if not phone_number_id or not access_token:
        print("❌ Account not configured!")
        return
    
    print(f"   ✅ Account found: {account.get('name')}")
    print(f"   📱 Phone number ID: {phone_number_id}\n")
    
    # 3. Essayer de récupérer l'image de profil
    print("3️⃣ Fetching profile picture from WhatsApp API...")
    
    try:
        profile_picture_url = await whatsapp_api_service.get_contact_profile_picture(
            phone_number_id=phone_number_id,
            access_token=access_token,
            phone_number=whatsapp_number
        )
        
        if profile_picture_url:
            print(f"   ✅ Profile picture found!")
            print(f"   🖼️  URL: {profile_picture_url}\n")
            
            # 4. Mettre à jour dans la base de données
            print("4️⃣ Updating database...")
            await supabase_execute(
                supabase.table("contacts")
                .update({"profile_picture_url": profile_picture_url})
                .eq("id", contact_id)
            )
            print(f"   ✅ Database updated successfully!")
        else:
            print("   ⚠️  No profile picture available from WhatsApp API")
            print("   ℹ️  This is normal - WhatsApp may not provide profile pictures for all contacts")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m scripts.test_profile_picture <contact_id> <account_id>")
        print("\nExample:")
        print("  python -m scripts.test_profile_picture b00a5d98-c135-4ed2-a413-f4a4e56f2019 122fb91e-660a-461d-ae7b-d0c310e36873")
        sys.exit(1)
    
    contact_id = sys.argv[1]
    account_id = sys.argv[2]
    
    asyncio.run(test_profile_picture(contact_id, account_id))

