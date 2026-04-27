"""
Script de diagnostic pour le stockage des médias
Vérifie étape par étape pourquoi le stockage ne fonctionne pas
"""
import asyncio
import sys
import os
from pathlib import Path

# Ajouter le répertoire parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.db import supabase, supabase_execute
from app.core.config import settings
from app.services.storage_service import MESSAGE_MEDIA_BUCKET
from starlette.concurrency import run_in_threadpool


async def check_config():
    """Vérifie la configuration"""
    print("=" * 60)
    print("1. Vérification de la configuration")
    print("=" * 60)
    
    if not settings.SUPABASE_URL:
        print("❌ SUPABASE_URL n'est pas configuré!")
        return False
    
    print(f"✅ SUPABASE_URL: {settings.SUPABASE_URL}")
    
    if not settings.SUPABASE_KEY:
        print("⚠️  SUPABASE_KEY n'est pas configuré (peut être normal si service_role)")
    else:
        print(f"✅ SUPABASE_KEY: {'*' * 20}")
    
    return True


async def check_bucket():
    """Vérifie que le bucket existe"""
    print("\n" + "=" * 60)
    print("2. Vérification du bucket")
    print("=" * 60)
    
    try:
        def _list_buckets():
            return supabase.storage.list_buckets()
        
        buckets = await run_in_threadpool(_list_buckets)
        
        if not buckets:
            print("❌ Impossible de lister les buckets (vérifiez les permissions)")
            return False
        
        # Les buckets peuvent être des objets ou des dicts
        bucket_names = []
        for b in buckets:
            if hasattr(b, 'name'):
                bucket_names.append(b.name)
            elif isinstance(b, dict):
                bucket_names.append(b.get("name"))
            else:
                bucket_names.append(str(b))
        
        print(f"✅ Buckets trouvés: {bucket_names}")
        
        if MESSAGE_MEDIA_BUCKET in bucket_names:
            print(f"✅ Bucket '{MESSAGE_MEDIA_BUCKET}' existe!")
            
            # Vérifier les détails du bucket
            bucket_info = None
            for b in buckets:
                name = b.name if hasattr(b, 'name') else (b.get("name") if isinstance(b, dict) else None)
                if name == MESSAGE_MEDIA_BUCKET:
                    bucket_info = b
                    break
            
            if bucket_info:
                if hasattr(bucket_info, 'public'):
                    print(f"   - Public: {bucket_info.public}")
                elif isinstance(bucket_info, dict):
                    print(f"   - Public: {bucket_info.get('public', 'N/A')}")
            
            return True
        else:
            print(f"❌ Bucket '{MESSAGE_MEDIA_BUCKET}' n'existe PAS!")
            print(f"   Buckets disponibles: {bucket_names}")
            print(f"\n   Pour créer le bucket:")
            print(f"   1. Allez dans Supabase Dashboard > Storage")
            print(f"   2. Créez un nouveau bucket nommé '{MESSAGE_MEDIA_BUCKET}'")
            print(f"   3. Activez 'Public bucket'")
            return False
            
    except Exception as e:
        print(f"❌ Erreur lors de la vérification du bucket: {e}")
        import traceback
        traceback.print_exc()
        return False


async def check_messages_with_media():
    """Vérifie les messages avec média dans la base"""
    print("\n" + "=" * 60)
    print("3. Vérification des messages avec média")
    print("=" * 60)
    
    try:
        query = (
            supabase.table("messages")
            .select("id, message_type, media_id, storage_url, timestamp, direction")
            .in_("message_type", ["image", "video", "audio", "voice", "document", "sticker"])
            .order("timestamp", desc=True)
            .limit(10)
        )
        
        result = await supabase_execute(query)
        messages = result.data or []
        
        if not messages:
            print("⚠️  Aucun message média trouvé dans la base de données")
            return []
        
        print(f"✅ {len(messages)} messages média trouvés (10 derniers):")
        print()
        
        for msg in messages:
            has_storage = "✅" if msg.get("storage_url") else "❌"
            print(f"  {has_storage} ID: {msg.get('id')[:8]}... | Type: {msg.get('message_type')} | "
                  f"Media ID: {msg.get('media_id', 'N/A')[:20] if msg.get('media_id') else 'N/A'}... | "
                  f"Storage: {'Oui' if msg.get('storage_url') else 'Non'} | "
                  f"Direction: {msg.get('direction')}")
        
        return messages
        
    except Exception as e:
        print(f"❌ Erreur lors de la vérification des messages: {e}")
        import traceback
        traceback.print_exc()
        return []


async def test_upload():
    """Teste un upload simple"""
    print("\n" + "=" * 60)
    print("4. Test d'upload")
    print("=" * 60)
    
    try:
        from app.services.storage_service import upload_message_media
        
        # Créer une petite image PNG de test (1x1 pixel)
        test_image_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82'
        test_message_id = "test-diagnostic-123"
        
        print(f"📤 Tentative d'upload d'un fichier de test...")
        print(f"   Message ID: {test_message_id}")
        print(f"   Taille: {len(test_image_data)} bytes")
        
        result = await upload_message_media(
            message_id=test_message_id,
            media_data=test_image_data,
            content_type="image/png",
            filename="test.png"
        )
        
        if result:
            print(f"✅ Upload réussi!")
            print(f"   URL: {result}")
            
            # Vérifier que le fichier est accessible
            import httpx
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(result, timeout=10.0)
                    if resp.status_code == 200:
                        print(f"✅ Fichier accessible via URL publique")
                    else:
                        print(f"⚠️  Fichier uploadé mais non accessible (status: {resp.status_code})")
            except Exception as e:
                print(f"⚠️  Erreur lors de la vérification de l'URL: {e}")
            
            return True
        else:
            print(f"❌ Upload échoué (retourné None)")
            return False
            
    except Exception as e:
        print(f"❌ Erreur lors du test d'upload: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    print("\n" + "=" * 60)
    print("DIAGNOSTIC DU STOCKAGE DES MÉDIAS")
    print("=" * 60)
    print()
    
    # 1. Configuration
    if not await check_config():
        print("\n❌ Configuration invalide. Arrêt du diagnostic.")
        return
    
    # 2. Bucket
    bucket_exists = await check_bucket()
    if not bucket_exists:
        print("\n❌ Le bucket n'existe pas. Créez-le d'abord.")
        return
    
    # 3. Messages
    messages = await check_messages_with_media()
    
    # 4. Test upload
    upload_works = await test_upload()
    
    # Résumé
    print("\n" + "=" * 60)
    print("RÉSUMÉ")
    print("=" * 60)
    print(f"Configuration: ✅")
    print(f"Bucket existe: {'✅' if bucket_exists else '❌'}")
    print(f"Messages média trouvés: {len(messages)}")
    print(f"Upload fonctionne: {'✅' if upload_works else '❌'}")
    
    if messages and not any(m.get("storage_url") for m in messages):
        print("\n⚠️  Aucun message n'a de storage_url.")
        print("   Cela signifie que le téléchargement automatique ne s'est pas exécuté.")
        print("   Vérifiez les logs du backend quand vous recevez un nouveau média.")
        print(f"\n   Pour tester manuellement, utilisez:")
        if messages:
            test_msg_id = messages[0].get("id")
            print(f"   POST /api/messages/test-storage/{test_msg_id}")
    
    print()


if __name__ == "__main__":
    asyncio.run(main())

