"""
Script pour uploader manuellement une image de profil
Usage: python -m scripts.upload_profile_picture <contact_id> <path_to_image>
"""
import asyncio
import sys
import os
from pathlib import Path

# Ajouter le chemin du projet
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import supabase, supabase_execute
from app.services.storage_service import upload_profile_picture


async def upload_manual_profile_picture(contact_id: str, image_path: str):
    """Upload une image de profil manuellement"""
    
    print(f"📤 Uploading profile picture for contact: {contact_id}")
    print(f"🖼️  Image path: {image_path}\n")
    
    # 1. Vérifier que le contact existe
    print("1️⃣ Checking contact...")
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
    print(f"   ✅ Contact found: {contact.get('display_name') or contact.get('whatsapp_number')}\n")
    
    # 2. Lire le fichier image
    print("2️⃣ Reading image file...")
    image_path_obj = Path(image_path)
    
    if not image_path_obj.exists():
        print(f"❌ Image file not found: {image_path}")
        return
    
    # Détecter le content-type
    extension = image_path_obj.suffix.lower()
    content_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.webp': 'image/webp',
        '.gif': 'image/gif'
    }
    content_type = content_types.get(extension, 'image/jpeg')
    
    with open(image_path_obj, 'rb') as f:
        image_data = f.read()
    
    file_size_mb = len(image_data) / (1024 * 1024)
    print(f"   ✅ Image loaded: {file_size_mb:.2f} MB")
    print(f"   📋 Content type: {content_type}\n")
    
    if file_size_mb > 5:
        print("⚠️  Warning: Image is larger than 5MB, may fail to upload")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            return
    
    # 3. Upload dans Supabase Storage
    print("3️⃣ Uploading to Supabase Storage...")
    try:
        # Utiliser async_upload=False pour attendre le résultat (script synchrone)
        stored_url = await upload_profile_picture(
            contact_id=contact_id,
            image_data=image_data,
            content_type=content_type,
            async_upload=False  # Attendre le résultat pour ce script
        )
        
        if stored_url:
            print(f"   ✅ Upload successful!")
            print(f"   🔗 URL: {stored_url}\n")
            
            # 4. Mettre à jour dans la base de données
            print("4️⃣ Updating database...")
            await supabase_execute(
                supabase.table("contacts")
                .update({"profile_picture_url": stored_url})
                .eq("id", contact_id)
            )
            print(f"   ✅ Database updated successfully!")
            print(f"\n🎉 Profile picture uploaded and saved!")
        else:
            print("   ❌ Upload failed!")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m scripts.upload_profile_picture <contact_id> <path_to_image>")
        print("\nExample:")
        print("  python -m scripts.upload_profile_picture b00a5d98-c135-4ed2-a413-f4a4e56f2019 C:\\Users\\louis\\Pictures\\profile.jpg")
        print("\nSupported formats: JPG, PNG, WEBP, GIF")
        sys.exit(1)
    
    contact_id = sys.argv[1]
    image_path = sys.argv[2]
    
    asyncio.run(upload_manual_profile_picture(contact_id, image_path))

