"""
Script pour vérifier si les webhooks sont bien reçus par le backend
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.db import supabase_execute, supabase
from app.core.config import settings


async def check_recent_webhooks():
    """Vérifie les messages récents dans la base pour voir si les webhooks arrivent"""
    print("=" * 60)
    print("VÉRIFICATION DE LA RÉCEPTION DES WEBHOOKS")
    print("=" * 60)
    print()
    
    # Vérifier les messages reçus dans les dernières 24h
    yesterday = datetime.utcnow() - timedelta(days=1)
    
    result = await supabase_execute(
        supabase.table("messages")
        .select("id, direction, message_type, timestamp, conversation_id")
        .eq("direction", "inbound")
        .gte("timestamp", yesterday.isoformat())
        .order("timestamp", desc=True)
        .limit(20)
    )
    
    messages = result.data or []
    
    print(f"📨 Messages entrants reçus dans les dernières 24h: {len(messages)}")
    print()
    
    if messages:
        print("Derniers messages reçus:")
        for msg in messages[:10]:
            timestamp = msg.get("timestamp", "")
            msg_type = msg.get("message_type", "text")
            print(f"  - {timestamp} | Type: {msg_type} | ID: {msg.get('id')}")
    else:
        print("⚠️  AUCUN message reçu dans les dernières 24h")
        print()
        print("Cela signifie que les webhooks ne sont PAS reçus par le backend.")
        print()
        print("Vérifications à faire:")
        print("1. Vérifiez dans Meta Business Suite que le webhook est 'Actif' (cercle vert)")
        print("2. Vérifiez que les champs 'messages' et 'message_status' sont bien cochés")
        print("3. Vérifiez que l'URL du webhook est correcte:")
        print(f"   https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp")
        print("4. Testez en envoyant un message depuis WhatsApp")
        print("5. Vérifiez les logs du backend pour voir si des POST arrivent")
    
    print()
    
    # Vérifier les conversations récentes
    try:
        result = await supabase_execute(
            supabase.table("conversations")
            .select("id, last_message_at, unread_count")
            .gte("last_message_at", yesterday.isoformat())
            .order("last_message_at", desc=True)
            .limit(10)
        )
        
        conversations = result.data or []
        
        print(f"💬 Conversations mises à jour dans les dernières 24h: {len(conversations)}")
        if conversations:
            print("Dernières conversations:")
            for conv in conversations[:5]:
                last_msg = conv.get("last_message_at", "")
                unread = conv.get("unread_count", 0)
                conv_id = conv.get("id", "N/A")
                print(f"  - ID: {conv_id} | Dernier message: {last_msg} | Non lus: {unread}")
    except Exception as e:
        print(f"⚠️  Erreur lors de la vérification des conversations: {e}")
    
    print()


async def check_webhook_config():
    """Vérifie la configuration du webhook"""
    print("=" * 60)
    print("CONFIGURATION DU WEBHOOK")
    print("=" * 60)
    print()
    
    print(f"🌐 URL du webhook: https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp")
    print(f"🔑 Verify token: {settings.WHATSAPP_VERIFY_TOKEN[:20] + '...' if settings.WHATSAPP_VERIFY_TOKEN else 'NON CONFIGURÉ'}")
    print()
    
    print("📋 Vérifications à faire dans Meta Business Suite:")
    print("1. Allez dans: Meta for Developers > Votre App > Webhooks > WhatsApp")
    print("2. Vérifiez que le statut est 'Actif' (cercle vert)")
    print("3. Cliquez sur 'Modifier' ou 'Gérer'")
    print("4. Vérifiez que les champs suivants sont cochés:")
    print("   ✅ messages")
    print("   ✅ message_status")
    print("5. Cliquez sur 'Enregistrer'")
    print()
    
    print("🧪 Test manuel:")
    print("1. Envoyez un message depuis WhatsApp vers votre numéro business")
    print("2. Attendez 2-3 secondes")
    print("3. Relancez ce script pour voir si le message apparaît")
    print()


if __name__ == "__main__":
    asyncio.run(check_recent_webhooks())
    asyncio.run(check_webhook_config())

