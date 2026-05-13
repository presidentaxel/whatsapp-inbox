"""
Script de test pour vérifier que le bucket message-media existe et fonctionne
"""
import asyncio
import sys
import os
from pathlib import Path

# Ajouter le répertoire parent au path pour importer les modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.db import supabase
from app.core.config import settings
from app.services.storage_service import upload_message_media, MESSAGE_MEDIA_BUCKET
from starlette.concurrency import run_in_threadpool


async def test_bucket_exists():
    """Vérifie si le bucket existe"""
    print(f"🔍 Checking if bucket '{MESSAGE_MEDIA_BUCKET}' exists...")
    print(f"📡 Supabase URL: {settings.SUPABASE_URL}")
    
    try:
        def _list_buckets():
            return supabase.storage.list_buckets()
        
        buckets = await run_in_threadpool(_list_buckets)
        
        if buckets:
            bucket_names = [b.get("name") for b in buckets]
            print(f"✅ Found {len(buckets)} buckets: {bucket_names}")
            
            if MESSAGE_MEDIA_BUCKET in bucket_names:
                print(f"✅ Bucket '{MESSAGE_MEDIA_BUCKET}' exists!")
                return True
            else:
                print(f"❌ Bucket '{MESSAGE_MEDIA_BUCKET}' NOT found!")
                print(f"   Available buckets: {bucket_names}")
                return False
        else:
            print("❌ No buckets found or error listing buckets")
            return False
            
    except Exception as e:
        print(f"❌ Error checking buckets: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_upload():
    """Teste l'upload d'un fichier de test"""
    print(f"\n🧪 Testing upload to bucket '{MESSAGE_MEDIA_BUCKET}'...")
    
    # Créer un fichier de test (image PNG 1x1 pixel)
    test_image_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82'
    test_message_id = "test-message-123"
    
    try:
        result = await upload_message_media(
            message_id=test_message_id,
            media_data=test_image_data,
            content_type="image/png",
            filename="test.png"
        )
        
        if result:
            print(f"✅ Upload successful!")
            print(f"   Storage URL: {result}")
            return True
        else:
            print(f"❌ Upload failed (returned None)")
            return False
            
    except Exception as e:
        print(f"❌ Upload error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    print("=" * 60)
    print("Media Storage Test Script")
    print("=" * 60)
    print()
    
    # Vérifier que SUPABASE_URL est configuré
    if not settings.SUPABASE_URL:
        print("❌ SUPABASE_URL not configured in environment variables!")
        return
    
    # Test 1: Vérifier que le bucket existe
    bucket_exists = await test_bucket_exists()
    
    if not bucket_exists:
        print("\n⚠️  Bucket does not exist. Please create it first:")
        print("   1. Go to Supabase Dashboard > Storage")
        print("   2. Create a new bucket named 'message-media'")
        print("   3. Make it PUBLIC")
        print("   4. Run this script again")
        return
    
    # Test 2: Tester l'upload
    await test_upload()
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

