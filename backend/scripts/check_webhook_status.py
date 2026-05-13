"""
Script pour vérifier l'état des webhooks et des messages
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

# Ajouter le répertoire backend au PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

# Charger les variables d'environnement
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(ENV_PATH)

from app.core.db import supabase, supabase_execute


async def check_database_connection():
    """Vérifie la connexion à la base de données"""
    try:
        # Test simple de connexion
        result = await supabase_execute(
            supabase.table("whatsapp_accounts").select("id").limit(1)
        )
        return True, "Connexion OK"
    except Exception as e:
        return False, str(e)


async def get_message_stats():
    """Récupère les statistiques des messages"""
    try:
        # Compter les messages entrants
        incoming = await supabase_execute(
            supabase.table("messages")
            .select("id", count="exact")
            .eq("direction", "inbound")
        )
        incoming_count = incoming.count if hasattr(incoming, 'count') else len(incoming.data) if incoming.data else 0
        
        # Compter les messages sortants
        outgoing = await supabase_execute(
            supabase.table("messages")
            .select("id", count="exact")
            .eq("direction", "outbound")
        )
        outgoing_count = outgoing.count if hasattr(outgoing, 'count') else len(outgoing.data) if outgoing.data else 0
        
        # Messages des dernières 24h
        yesterday = datetime.now() - timedelta(days=1)
        recent = await supabase_execute(
            supabase.table("messages")
            .select("id", count="exact")
            .gte("timestamp", yesterday.isoformat())
        )
        recent_count = recent.count if hasattr(recent, 'count') else len(recent.data) if recent.data else 0
        
        return {
            "incoming": incoming_count,
            "outgoing": outgoing_count,
            "recent_24h": recent_count
        }
    except Exception as e:
        return {"error": str(e)}


async def get_all_messages(limit: int = 20):
    """Récupère tous les messages (entrants et sortants)"""
    try:
        result = await supabase_execute(
            supabase.table("messages")
            .select("id, direction, content_text, timestamp, wa_message_id, message_type, status")
            .order("timestamp", desc=True)
            .limit(limit)
        )
        return result.data if result.data else []
    except Exception as e:
        return None


async def get_accounts():
    """Récupère les comptes WhatsApp configurés"""
    try:
        result = await supabase_execute(
            supabase.table("whatsapp_accounts")
            .select("id, name, phone_number, phone_number_id, is_active")
        )
        return result.data if result.data else []
    except Exception as e:
        return None


async def main():
    print("="*80)
    print("DIAGNOSTIC WEBHOOK WHATSAPP")
    print("="*80)
    
    # Vérifier la connexion
    print("\n1. Vérification de la connexion à la base de données...")
    connected, message = await check_database_connection()
    if connected:
        print(f"   ✓ {message}")
    else:
        print(f"   ✗ Erreur: {message}")
        return
    
    # Vérifier les comptes
    print("\n2. Comptes WhatsApp configurés...")
    accounts = await get_accounts()
    if accounts:
        print(f"   ✓ {len(accounts)} compte(s) trouvé(s):")
        for acc in accounts:
            status = "✓ Actif" if acc.get("is_active") else "✗ Inactif"
            print(f"      - {acc.get('name')} ({acc.get('phone_number_id')}) {status}")
    else:
        print("   ⚠️ Aucun compte trouvé")
    
    # Statistiques des messages
    print("\n3. Statistiques des messages...")
    stats = await get_message_stats()
    if "error" in stats:
        print(f"   ✗ Erreur: {stats['error']}")
    else:
        print(f"   Messages entrants: {stats['incoming']}")
        print(f"   Messages sortants: {stats['outgoing']}")
        print(f"   Messages (24h): {stats['recent_24h']}")
    
    # Derniers messages
    print("\n4. Derniers messages reçus...")
    messages = await get_all_messages(10)
    if messages is None:
        print("   ✗ Erreur lors de la récupération des messages")
    elif not messages:
        print("   ⚠️ Aucun message dans la base de données")
        print("\n   Cela signifie qu'aucun webhook n'a encore été traité avec succès.")
        print("   Vérifiez:")
        print("   - Que le webhook est bien configuré dans Meta")
        print("   - Que le serveur reçoit bien les webhooks (logs)")
        print("   - Que les webhooks sont correctement traités")
    else:
        print(f"   ✓ {len(messages)} message(s) trouvé(s):")
        for idx, msg in enumerate(messages[:5], 1):
            direction = "📥 Entrant" if msg.get("direction") == "inbound" else "📤 Sortant"
            timestamp = msg.get("timestamp", "N/A")
            content = msg.get("content_text", "")[:50] if msg.get("content_text") else "(pas de contenu)"
            print(f"      {idx}. {direction} - {timestamp} - {content}...")
    
    print("\n" + "="*80)
    print("Pour voir plus de détails, utilisez:")
    print("  python scripts/view_recent_webhooks.py --limit 20")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
