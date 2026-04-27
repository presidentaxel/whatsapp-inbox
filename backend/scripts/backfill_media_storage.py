"""
Script pour télécharger rétroactivement les médias existants dans Supabase Storage
Utile pour les messages qui n'ont pas encore été stockés
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.db import supabase_execute, supabase
from app.services.account_service import get_account_by_id
from app.services.message_service import _download_and_store_media_async
from app.services.conversation_service import get_conversation_by_id


async def backfill_media_storage(limit: int = 50):
    """
    Télécharge et stocke les médias des messages existants qui n'ont pas de storage_url
    """
    print("=" * 60)
    print("BACKFILL MEDIA STORAGE")
    print("=" * 60)
    print()
    
    # Trouver les messages avec média mais sans storage_url
    query = (
        supabase.table("messages")
        .select("id, message_type, media_id, conversation_id, media_mime_type, media_filename")
        .in_("message_type", ["image", "video", "audio", "voice", "document", "sticker"])
        .is_("storage_url", "null")
        .not_.is_("media_id", "null")
        .order("timestamp", desc=True)
        .limit(limit)
    )
    
    result = await supabase_execute(query)
    messages = result.data or []
    
    if not messages:
        print("✅ Aucun message à traiter (tous ont déjà un storage_url ou pas de media_id)")
        return
    
    print(f"📋 {len(messages)} messages à traiter")
    print()
    
    success_count = 0
    error_count = 0
    
    for i, msg in enumerate(messages, 1):
        msg_id = msg.get("id")
        media_id = msg.get("media_id")
        msg_type = msg.get("message_type")
        conv_id = msg.get("conversation_id")
        
        print(f"[{i}/{len(messages)}] Processing message {msg_id[:8]}... (type: {msg_type}, media_id: {media_id[:20] if media_id else 'N/A'}...)")
        
        try:
            # Récupérer la conversation pour obtenir l'account_id
            conversation = await get_conversation_by_id(conv_id)
            if not conversation:
                print(f"  ❌ Conversation not found: {conv_id}")
                error_count += 1
                continue
            
            account_id = conversation.get("account_id")
            if not account_id:
                print(f"  ❌ No account_id in conversation")
                error_count += 1
                continue
            
            # Récupérer l'account
            account = await get_account_by_id(account_id)
            if not account:
                print(f"  ❌ Account not found: {account_id}")
                error_count += 1
                continue
            
            # Télécharger et stocker (synchronement pour ce script)
            print(f"  📥 Downloading media from WhatsApp...")
            await _download_and_store_media_async(
                message_db_id=msg_id,
                media_id=media_id,
                account=account,
                mime_type=msg.get("media_mime_type"),
                filename=msg.get("media_filename")
            )
            
            # Attendre un peu pour que le stockage se termine (la fonction est async)
            await asyncio.sleep(1)
            
            # Vérifier que storage_url a été mis à jour
            check_result = await supabase_execute(
                supabase.table("messages")
                .select("storage_url")
                .eq("id", msg_id)
                .limit(1)
            )
            
            if check_result.data and check_result.data[0].get("storage_url"):
                storage_url = check_result.data[0].get("storage_url")
                print(f"  ✅ Storage URL: {storage_url[:80]}...")
                success_count += 1
            else:
                print(f"  ⚠️  Storage URL not set yet, waiting...")
                # Attendre un peu plus et réessayer (le téléchargement peut prendre du temps)
                await asyncio.sleep(3)
                check_result = await supabase_execute(
                    supabase.table("messages")
                    .select("storage_url")
                    .eq("id", msg_id)
                    .limit(1)
                )
                if check_result.data and check_result.data[0].get("storage_url"):
                    storage_url = check_result.data[0].get("storage_url")
                    print(f"  ✅ Storage URL set after wait: {storage_url[:80]}...")
                    success_count += 1
                else:
                    print(f"  ❌ Storage URL still not set after wait (media may be expired or download failed)")
                    error_count += 1
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            error_count += 1
        
        print()
    
    print("=" * 60)
    print("RÉSUMÉ")
    print("=" * 60)
    print(f"Messages traités: {len(messages)}")
    print(f"✅ Succès: {success_count}")
    print(f"❌ Erreurs: {error_count}")
    print()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Backfill media storage for existing messages")
    parser.add_argument("--limit", type=int, default=50, help="Nombre maximum de messages à traiter")
    args = parser.parse_args()
    
    asyncio.run(backfill_media_storage(limit=args.limit))

